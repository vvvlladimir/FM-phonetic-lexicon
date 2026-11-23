"""Validation report printed at the end of build_db."""
from __future__ import annotations

import sqlite3
import unicodedata


def _table(rows: list[tuple], headers: list[str]) -> str:
    rows = [tuple("" if v is None else (f"{v:.3f}" if isinstance(v, float) else str(v))
                  for v in r) for r in rows]
    widths = [max(len(h), *(len(r[i]) for r in rows)) if rows else len(h)
              for i, h in enumerate(headers)]
    line = lambda r: "  ".join(v.ljust(w) for v, w in zip(r, widths))
    return "\n".join([line(headers), line(["-" * w for w in widths])] + [line(r) for r in rows])


def counts(conn, langs):
    q = f"""SELECT lang, category, source, COUNT(*), SUM(ipa IS NOT NULL AND ipa != '')
            FROM entries WHERE lang IN ({','.join('?' * len(langs))})
            GROUP BY lang, category, source ORDER BY lang, category"""
    return conn.execute(q, langs).fetchall()


def samples(conn, langs, category, k=10, seed=42):
    # deterministic "random" sample: order by a hash of id and seed
    q = f"""SELECT lang, text, origin_country, frequency, frequency_norm, ipa FROM entries
            WHERE category = ? AND lang IN ({','.join('?' * len(langs))})
            ORDER BY (id * 2654435761 + ?) % 4294967296 LIMIT ?"""
    return conn.execute(q, [category, *langs, seed, k]).fetchall()


def homophones(conn, lang, k=20):
    """Pairs with identical IPA but different spelling (case-only differences ignored)."""
    conn.create_function("fold", 1, lambda s: s.casefold(), deterministic=True)
    # one row per unordered spelling pair (best-scoring category combination)
    q = """SELECT MIN(a.text, b.text) AS t1, MAX(a.text, b.text) AS t2,
                  GROUP_CONCAT(a.category || ',' || b.category) AS cats, a.ipa,
                  MAX(MIN(a.frequency_norm, b.frequency_norm)) AS score
           FROM entries a JOIN entries b
             ON a.lang = b.lang AND a.ipa = b.ipa AND a.id < b.id
           WHERE a.lang = ? AND a.ipa != '' AND fold(a.text) != fold(b.text)
           GROUP BY t1, t2 ORDER BY score DESC LIMIT ?"""
    rows = conn.execute(q, (lang, k)).fetchall()
    # categories column: the set of categories either spelling occurs in
    return [(t1, t2, ",".join(sorted(set(cats.split(",")))), ipa_, score)
            for t1, t2, cats, ipa_, score in rows]


def homophone_count(conn, lang):
    conn.create_function("fold", 1, lambda s: s.casefold(), deterministic=True)
    q = """SELECT COUNT(DISTINCT MIN(a.text, b.text) || '|' || MAX(a.text, b.text))
           FROM entries a JOIN entries b
             ON a.lang = b.lang AND a.ipa = b.ipa AND a.id < b.id
           WHERE a.lang = ? AND a.ipa != '' AND fold(a.text) != fold(b.text)"""
    return conn.execute(q, (lang,)).fetchone()[0]


def failures(conn, langs):
    q = f"""SELECT lang, category, text, ipa FROM entries
            WHERE (ipa IS NULL OR ipa = '') AND lang IN ({','.join('?' * len(langs))})
            ORDER BY lang, category, text"""
    return conn.execute(q, langs).fetchall()


def loose(ipa: str) -> str:
    """Drop length marks, tie bars and all combining diacritics (e.g. non-syllabic)."""
    return "".join(ch for ch in unicodedata.normalize("NFD", ipa)
                   if ch not in "ːˑ" and not unicodedata.category(ch).startswith("M"))


def wikipron_compare(conn, lang, k=10):
    """Compare eSpeak IPA with all WikiPron variants of the same spelling.

    Returns (n_texts, n_exact, n_loose, top-k most frequent word mismatches).
    """
    q = """SELECT e.text, e.ipa, e.category, e.frequency, r.ipa_compact
           FROM entries e JOIN reference_pron r ON r.lang = e.lang AND r.word = e.text
           WHERE e.lang = ? AND e.ipa != ''"""
    by_text: dict[str, dict] = {}
    for text, ipa, cat, freq, ref in conn.execute(q, (lang,)):
        d = by_text.setdefault(text, {"ipa": ipa, "refs": set(), "word_freq": None})
        d["refs"].add(ref)
        if cat == "word":
            d["word_freq"] = freq
    exact = loose_n = 0
    mismatches = []
    for text, d in by_text.items():
        if d["ipa"] in d["refs"]:
            exact += 1
        if loose(d["ipa"]) in {loose(r) for r in d["refs"]}:
            loose_n += 1
        elif d["word_freq"] is not None:
            mismatches.append((d["word_freq"], text, d["ipa"], " | ".join(sorted(d["refs"]))))
    mismatches.sort(reverse=True)
    return len(by_text), exact, loose_n, [m[1:] for m in mismatches[:k]]


def print_report(conn: sqlite3.Connection, langs: list[str], max_failures: int = 50) -> str:
    out: list[str] = []
    p = out.append

    p("\n=== 1. Row counts per (lang, category, source) ===")
    p(_table(counts(conn, langs), ["lang", "category", "source", "rows", "with_ipa"]))

    p("\n=== 2. Random samples (10 per category) ===")
    for cat in ("first_name", "last_name", "city", "country", "word"):
        rows = samples(conn, langs, cat)
        if rows:
            p(f"\n-- {cat}")
            p(_table(rows, ["lang", "text", "origin", "freq", "freq_norm", "ipa"]))

    p("\n=== 3. Homophone check: same IPA, different spelling (top 20 by frequency) ===")
    for lang in langs:
        rows = homophones(conn, lang)
        p(f"\n-- {lang}: {homophone_count(conn, lang)} distinct spelling pairs total")
        p(_table(rows, ["text_a", "text_b", "categories", "ipa", "min_freq_norm"]))

    p("\n=== 4. Empty / failed eSpeak output ===")
    fails = failures(conn, langs)
    p(f"{len(fails)} entries without IPA" +
      (f" (showing first {max_failures})" if len(fails) > max_failures else ""))
    if fails:
        p(_table(fails[:max_failures], ["lang", "category", "text", "ipa"]))

    if conn.execute("SELECT 1 FROM reference_pron LIMIT 1").fetchone():
        p("\n=== 5. WikiPron cross-check (eSpeak vs WikiPron, stress/spaces removed) ===")
        for lang in langs:
            total, exact, loose_n, mism = wikipron_compare(conn, lang)
            if total:
                p(f"\n-- {lang}: {total} distinct texts also in WikiPron; "
                  f"exact match {exact} ({100 * exact / total:.1f}%), "
                  f"loose match (no length/diacritics) {loose_n} ({100 * loose_n / total:.1f}%)")
                p("most frequent words without loose match:")
                p(_table(mism, ["word", "espeak", "wikipron variants (compact)"]))

    text = "\n".join(out)
    print(text)
    return text
