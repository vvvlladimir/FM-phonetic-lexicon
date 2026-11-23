"""Step 2: letter<->sound alignment, sound->spelling tables and spelling variants.

    python -m src.build_variants --langs en
    python -m src.build_variants                    # all 10 languages
    python -m src.build_variants --top-n 500 --report-path data/report_variants.txt

Needs the DB from step 1 (src.build_db). Tables g2p_alignment, sound_spelling and
variants are derived data: they are rebuilt for every language you pass.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sqlite3
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor

from tqdm import tqdm

from . import config, db
from .espeak_trace import trace_words
from .fetch_names import all_spellings
from .g2p import Table, build_alignments
from .ipa import make_espeak_phonemizer
from .phonetic import (_similarity_pair, ru_equivalent, sound_neighbours, sound_to_ipa,
                       stressed_vowel_index)
from .report import _table
from .variants import generate

log = logging.getLogger("build_variants")
SINGLE_TOKEN = re.compile(r"^[^\W\d_]+$")
SHOWCASE = {
    "en": ["Philip", "Catherine", "Stephen", "Jackson", "Thompson"],
    "de": ["Philipp", "Meyer", "Pferd", "Schmidt", "Katharina"],
    "fr": ["Philippe", "Thierry", "Rousseau", "Bordeaux", "Mathieu"],
    "es": ["Felipe", "Javier", "Vázquez", "Guillermo", "Sevilla"],
    "it": ["Filippo", "Giovanni", "Chiara", "Napoli", "Ghirardelli"],
    "pt": ["Filipe", "Gonçalves", "João", "Conceição", "Lisboa"],
    "nl": ["Philip", "Sjoerd", "Huijgens", "Gerrit", "Utrecht"],
    "ru": ["Филипп", "Наталья", "Алексей", "молоко", "Ольга"],
    "pl": ["Filip", "Grzegorz", "Wójcik", "Krzysztof", "Łódź"],
    "tr": ["Filiz", "Şahin", "Yılmaz", "Gökhan", "Çağlar"],
}


def load_texts(conn, lang) -> dict[str, dict]:
    """Single-token entries with IPA: {text: {ipa, cats: {category: freq_norm}}}."""
    texts: dict[str, dict] = {}
    for text, cat, fn, ipa in conn.execute(
            "SELECT text, category, frequency_norm, ipa FROM entries "
            "WHERE lang = ? AND ipa IS NOT NULL AND ipa != ''", (lang,)):
        if SINGLE_TOKEN.match(text):
            d = texts.setdefault(text, {"ipa": ipa, "cats": {}})
            d["cats"][cat] = fn or 0.0
    return texts


def pick_originals(texts, aligned, top_n, lang) -> list[str]:
    by_cat = defaultdict(list)
    for w, d in texts.items():
        for c, fn in d["cats"].items():
            by_cat[c].append((fn, w))
    chosen = {w for c in by_cat for _, w in sorted(by_cat[c], reverse=True)[:top_n]}
    fold = {w.casefold(): w for w in texts}
    for w in SHOWCASE.get(lang, []):
        w = w if w in texts else fold.get(w.casefold())
        if w:
            chosen.add(w)
    return sorted(w for w in chosen if w in aligned)


def known_pairs(texts) -> dict[str, set[str]]:
    """Real spelling pairs from step 1: same IPA, different spelling."""
    by_ipa = defaultdict(list)
    for t, d in texts.items():
        by_ipa[d["ipa"]].append(t)
    pairs = defaultdict(set)
    for group in by_ipa.values():
        if 2 <= len(group) <= 20:
            for a in group:
                for b in group:
                    if a.casefold() != b.casefold():
                        pairs[a].add(b.casefold())
    return pairs


def run_lang(conn, lang, args, names_set, pool) -> dict:
    t0 = time.time()
    voice = config.ESPEAK_VOICES[lang]
    texts = load_texts(conn, lang)
    log.info("[%s] %d single-token texts; tracing eSpeak rules", lang, len(texts))
    traces = trace_words(sorted(texts), voice)
    aligned, table, align_stats = build_alignments(traces)

    # only reasonably frequent sounds: the rest are rare alignment fragments
    sound_ipa = sound_to_ipa(sorted(table.sounds(min_count=20)), voice)
    neighbours = sound_neighbours(sound_ipa, config.NEIGHBOUR_MAX_DIST, freq=table.sound_counts())
    log.info("[%s] %d sounds (>= 20 uses) with IPA, aligned: %s", lang, len(sound_ipa), dict(align_stats))

    with conn:
        conn.execute("DELETE FROM g2p_alignment WHERE lang = ?", (lang,))
        conn.execute("DELETE FROM sound_spelling WHERE lang = ?", (lang,))
        conn.executemany("INSERT INTO g2p_alignment VALUES (?, ?, ?, ?)",
                         [(w, lang, m, json.dumps(p, ensure_ascii=False)) for w, (m, p) in aligned.items()])
        conn.executemany("INSERT INTO sound_spelling VALUES (?, ?, ?, ?, ?, ?, ?)",
                         [(lang, s, sound_ipa.get(s, ""), pos, g, c, p) for s, pos, g, c, p in table.rows()])

    originals = pick_originals(texts, aligned, args.top_n, lang)
    log.info("[%s] generating variants for %d originals", lang, len(originals))
    cands = {w: generate(w, aligned[w][1], table, neighbours, k=args.candidates,
                         max_changes=config.VARIANT_MAX_CHANGES) for w in originals}

    flat = sorted({c.text for cs in cands.values() for c in cs})
    phonemize = make_espeak_phonemizer(lang)
    ipa_of = dict(zip(flat, phonemize(flat))) if flat else {}
    stress_idx = {}
    if lang == "ru":
        stressed = make_espeak_phonemizer(lang, with_stress=True)(originals)
        stress_idx = {w: stressed_vowel_index(s) for w, s in zip(originals, stressed)}

    def is_homophone(w, v):
        if ipa_of[v] == texts[w]["ipa"]:
            return True
        return lang == "ru" and ru_equivalent(w, v, texts[w]["ipa"], ipa_of[v], stress_idx.get(w, 0))

    homo = {(w, c.text) for w, cs in cands.items() for c in cs if is_homophone(w, c.text)}
    todo = sorted({(texts[w]["ipa"], ipa_of[c.text]) for w, cs in cands.items() for c in cs
                   if (w, c.text) not in homo})
    sims = dict(zip(todo, tqdm(pool.map(_similarity_pair, todo, chunksize=500),
                               total=len(todo), desc=f"similarity {lang}", unit="pair")))

    entry_set = {w.casefold() for w in texts}
    rows, metrics, stored = [], Counter(), defaultdict(list)
    pairs = known_pairs(texts)
    for w, cs in cands.items():
        orig_ipa = texts[w]["ipa"]
        scored = {"homophone": [], "near": []}
        for c in cs:
            v_ipa = ipa_of[c.text]
            if (w, c.text) in homo:
                match, sim = "homophone", 1.0
            else:
                sim = sims[(orig_ipa, v_ipa)]
                if sim < config.NEAR_THRESHOLD:
                    continue
                match = "near"
            att_name = c.text.casefold() in names_set
            att_entry = c.text.casefold() in entry_set
            score = c.score + config.ATTESTED_BONUS * (att_name or att_entry)
            scored[match].append((score, c, sim, att_name, att_entry, v_ipa))
        metrics["originals"] += 1
        metrics["candidates"] += len(cs)
        metrics["cand_homophone"] += sum((w, c.text) in homo for c in cs)
        for match, lst in scored.items():
            # most typical change first (similarity is only the entry threshold); sorting
            # "near" by similarity would push out sound drops like Pferd -> Fert (0.8)
            lst.sort(key=lambda x: -x[0])
            keep = lst[:args.keep]
            metrics[f"has_{match}"] += bool(keep)
            for score, c, sim, an, ae, v_ipa in keep:
                rows.append((w, lang, c.text, ",".join(c.kinds), match, round(sim, 4),
                             round(score, 4), int(an), int(ae), v_ipa))
                stored[w].append((match, c.text, ",".join(c.kinds), round(sim, 3), an or ae))
                metrics[f"stored_{match}"] += 1
                metrics[f"attested_{match}"] += an or ae
                for k in c.kinds:
                    metrics[f"kind_{match}_{k}"] += 1
        if w in pairs:
            gen = {c.text.casefold() for c in cs}
            metrics["pair_total"] += len(pairs[w])
            metrics["pair_found"] += len(pairs[w] & gen)

    with conn:
        conn.execute("DELETE FROM variants WHERE lang = ?", (lang,))
        conn.executemany("INSERT INTO variants (text, lang, variant, kinds, match, similarity, score, "
                         "attested_name, attested_entry, ipa) VALUES (?,?,?,?,?,?,?,?,?,?)", rows)
    log.info("[%s] stored %d variants in %.0f s", lang, len(rows), time.time() - t0)
    return {"align": align_stats, "n_texts": len(texts), "metrics": metrics, "stored": stored,
            "table": table, "sound_ipa": sound_ipa, "aligned": aligned, "texts": texts}


def pct(a, b):
    return f"{100 * a / b:.0f}%" if b else "-"


def table_excerpt(table: Table, sound_ipa, n_sounds=4, n_graph=6):
    merged = defaultdict(Counter)
    for (s, _), c in table.by_sound.items():
        if s:
            merged[s].update(c)
    rich = sorted(merged.items(), key=lambda kv: -len([g for g, k in kv[1].items() if k >= 5]))
    out = []
    for s, c in rich[:n_sounds]:
        total = sum(c.values())
        out.append((f"/{sound_ipa.get(s, '?')}/ ({s})",
                    ", ".join(f"{g} {100 * k / total:.0f}%" for g, k in c.most_common(n_graph))))
    return out


def format_report(results: dict) -> str:
    summary, body = [], []
    p = body.append
    for lang, r in results.items():
        m, a, n = r["metrics"], r["align"], r["n_texts"]
        summary.append((lang, n, pct(a["rules"], n), pct(a["viterbi"], n), m["originals"],
                        pct(m["has_homophone"], m["originals"]), pct(m["has_near"], m["originals"]),
                        pct(m["cand_homophone"], m["candidates"]),
                        pct(m["attested_homophone"] + m["attested_near"],
                            m["stored_homophone"] + m["stored_near"]),
                        pct(m["pair_found"], m["pair_total"])))
        p(f"\n################ {lang} ################")
        kinds = sorted({k[len('kind_'):] for k in m if k.startswith("kind_")})
        p("stored variants by kind: " + ", ".join(f"{k}={m['kind_' + k]}" for k in kinds))
        p("\nsounds with the most spellings:")
        p(_table(table_excerpt(r["table"], r["sound_ipa"]), ["sound", "spellings (share)"]))
        fold = {w.casefold(): w for w in r["stored"]}
        for w in SHOWCASE.get(lang, []):
            w2 = w if w in r["aligned"] else fold.get(w.casefold(), w)
            if w2 not in r["aligned"]:
                p(f"\n{w}: not in DB")
                continue
            al = " ".join(f"{g}→{r['sound_ipa'].get(s, s) if s else '∅'}" for g, s in r["aligned"][w2][1])
            p(f"\n{w2}  /{r['texts'][w2]['ipa']}/   {al}")
            vs = r["stored"].get(w2, [])
            star = lambda att: "*" if att else ""
            hom = [f"{v}{star(att)}" for mt, v, _, _, att in vs if mt == "homophone"][:10]
            near = [f"{v}{star(att)} ({k}, {s:.2f})" for mt, v, k, s, att in vs if mt == "near"][:5]
            p(f"   same sound : {', '.join(hom) or '-'}")
            p(f"   similar    : {', '.join(near) or '-'}")
    head = ["lang", "texts", "aligned by rules", "by viterbi", "originals", "≥1 same-sound variant",
            "≥1 similar variant", "candidates that sound same", "stored that are real spellings",
            "known pairs found"]
    return ("=== Step 2: spelling variants ===\n"
            "(* = spelling exists in names-dataset or entries; similar = PanPhon similarity "
            f">= {config.NEAR_THRESHOLD})\n\n" + _table(summary, head) + "\n" + "\n".join(body))


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--langs", nargs="+", default=config.LANGS, choices=config.LANGS)
    ap.add_argument("--db-path", default=str(config.DEFAULT_DB_PATH))
    ap.add_argument("--top-n", type=int, default=config.VARIANT_TOP_N, help="originals per (lang, category)")
    ap.add_argument("--candidates", type=int, default=config.VARIANT_CANDIDATES)
    ap.add_argument("--keep", type=int, default=config.VARIANT_KEEP)
    ap.add_argument("--report-path", default=str(config.DATA_DIR / "report_variants.txt"))
    return ap.parse_args(argv)


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    args = parse_args(argv)
    conn = db.connect(args.db_path)
    if not conn.execute("SELECT 1 FROM entries WHERE ipa IS NOT NULL LIMIT 1").fetchone():
        log.error("no entries with IPA in %s - run `python -m src.build_db` first", args.db_path)
        return 2
    log.info("loading names-dataset spellings (for the 'real spelling' check)")
    names_set = all_spellings()
    results = {}
    with ProcessPoolExecutor(max_workers=os.cpu_count()) as pool:
        for lang in args.langs:
            results[lang] = run_lang(conn, lang, args, names_set, pool)
    text = format_report(results)
    print(text)
    with open(args.report_path, "w", encoding="utf-8") as f:
        f.write(text + "\n")
    log.info("report written to %s", args.report_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
