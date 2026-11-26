"""On-demand API: score how plausible a (phonetic) mistake is.  (ADR-0013)

Meant to be called by the TTS-STT pipeline (or anyone) with arbitrary strings:

    from src.lexicon import Lexicon
    lex = Lexicon()                                   # data/lexicon.db
    lex.score("Philip", "Fillipp", "en").plausibility  # 0.085  (realistic)
    lex.score("Pferd", "Fert", "de").plausibility      # 0.018  (unrealistic)
    lex.rerank("Hak", [("Haag", 0.97), ("hack", 0.95)], "de", textclass="NAME")

CLI:
    python -m src.lexicon de Pferd Fert fährt Ferd
    python -m src.lexicon en Philip Fillipp Phillip --kind name

What happens for a call (per language everything is loaded once and kept in memory):
  1. IPA of original and variants: entries -> ipa_cache -> eSpeak (batch), new IPA
     is written to ipa_cache, so the next call is instant.
  2. Letter<->sound alignment of the original: g2p_alignment, else traced on the fly
     with `espeak-ng -X` (as in step 2) and stored.
  3. similarity (PanPhon, or 1.0 for same sound / Russian vowel rule),
     known spelling (category-aware), typicality (explain_variant), prior -> plausibility.
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import sqlite3
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from . import config, db
from .espeak_trace import trace_words
from .g2p import Table, align_to_final
from .ipa import make_espeak_phonemizer
from .normalize import normalize
from .phonetic import ru_equivalent, similarity, sound_neighbours, stressed_vowel_index
from .plausibility import KnownSpellings, kind_of, load_known, plausibility
from .variants import explain_variant

log = logging.getLogger(__name__)


@dataclass
class Score:
    original: str
    variant: str
    lang: str
    kind: str                 # name | word
    plausibility: float       # 0..1, higher = more realistic mistake (ADR-0012)
    similarity: float         # 1 = same sound (PanPhon otherwise)
    same_sound: bool
    known_as: str | None      # 'name' | 'word' | None: the variant is a real name / real word
    logp: float               # spelling-change log-probability (explain_variant)
    n_changes: int
    ipa_original: str
    ipa_variant: str
    extra: float | None = None  # caller's own score, passed through by rerank()

    def as_dict(self) -> dict:
        return asdict(self)


class _LangModel:
    """Per-language data loaded once: spelling table, neighbour sounds, word frequencies."""

    def __init__(self, conn: sqlite3.Connection, lang: str):
        rows = conn.execute("SELECT sound, position, letters, count FROM sound_spelling "
                            "WHERE lang = ?", (lang,)).fetchall()
        if not rows:
            raise RuntimeError(f"no sound_spelling rows for '{lang}' - run "
                               f"`python -m src.build_variants --langs {lang}` first")
        self.table = Table.from_rows(rows)
        sound_ipa = dict(conn.execute("SELECT DISTINCT sound, sound_ipa FROM sound_spelling "
                                      "WHERE lang = ? AND sound_ipa != ''", (lang,)))
        self.neighbours = sound_neighbours(sound_ipa, config.NEIGHBOUR_MAX_DIST,
                                           freq=self.table.sound_counts())
        lo, hi = conn.execute("SELECT MIN(frequency), MAX(frequency) FROM entries "
                              "WHERE lang = ? AND category = 'word'", (lang,)).fetchone()
        self.zipf_range = (lo or 0.0, hi or 1.0)


class Lexicon:
    def __init__(self, db_path: str | Path = config.DEFAULT_DB_PATH, phonemizer_factory=None):
        self.conn = db.connect(db_path)
        self._phonemizer_factory = phonemizer_factory or make_espeak_phonemizer
        self._phonemizers: dict[tuple[str, bool], object] = {}
        self._models: dict[str, _LangModel] = {}
        self._known: KnownSpellings | None = None

    # --- loading -------------------------------------------------------------
    def _model(self, lang: str) -> _LangModel:
        if lang not in config.ESPEAK_VOICES:
            raise ValueError(f"unsupported language '{lang}', use one of {config.LANGS}")
        if lang not in self._models:
            self._models[lang] = _LangModel(self.conn, lang)
        return self._models[lang]

    def _phonemize(self, texts: list[str], lang: str, with_stress: bool = False) -> list[str]:
        key = (lang, with_stress)
        if key not in self._phonemizers:  # one eSpeak backend per language (expensive)
            self._phonemizers[key] = (self._phonemizer_factory(lang, with_stress=with_stress)
                                      if with_stress else self._phonemizer_factory(lang))
        return self._phonemizers[key](texts)

    @property
    def known(self) -> KnownSpellings:
        if self._known is None:
            names = {r[0] for r in self.conn.execute("SELECT spelling FROM known_names")}
            if not names:
                log.warning("known_names is empty (run src.build_variants); loading names-dataset")
                from .fetch_names import all_spellings
                names = all_spellings()
            self._known = load_known(self.conn, names)
        return self._known

    # --- IPA with cache ------------------------------------------------------
    def ipa(self, texts: list[str], lang: str) -> list[str]:
        """IPA for any texts: entries -> ipa_cache -> eSpeak (stored in ipa_cache)."""
        texts = [normalize(t) for t in texts]
        found: dict[str, str] = {}
        uniq = sorted(set(texts))
        for i in range(0, len(uniq), 500):
            chunk = uniq[i:i + 500]
            q = ",".join("?" * len(chunk))
            for t, ipa in self.conn.execute(
                    f"SELECT text, ipa FROM entries WHERE lang = ? AND text IN ({q}) "
                    f"AND ipa IS NOT NULL", [lang, *chunk]):
                found.setdefault(t, ipa)
            for t, ipa in self.conn.execute(
                    f"SELECT text, ipa FROM ipa_cache WHERE lang = ? AND text IN ({q})", [lang, *chunk]):
                found.setdefault(t, ipa)
        missing = [t for t in uniq if t not in found]
        if missing:
            new = self._phonemize(missing, lang)
            with self.conn:
                self.conn.executemany("INSERT OR REPLACE INTO ipa_cache VALUES (?, ?, ?)",
                                      [(t, lang, i) for t, i in zip(missing, new)])
            found.update(zip(missing, new))
        return [found[t] for t in texts]

    # --- original word info ----------------------------------------------------
    def _alignment(self, word: str, lang: str) -> list[tuple[str, str]]:
        row = self.conn.execute("SELECT pairs FROM g2p_alignment WHERE text = ? AND lang = ?",
                                (word, lang)).fetchone()
        if row:
            return [tuple(p) for p in json.loads(row[0])]
        # not aligned yet: trace with eSpeak now (same method as step 2) and store
        model = self._model(lang)
        t = trace_words([word], config.ESPEAK_VOICES[lang])[0]
        pairs, method = None, "rules"
        if t.rules_ok:
            segs = align_to_final(t.chunks, t.final)
            if segs is not None:
                pairs = list(zip([g for g, _ in t.chunks], segs))
        if pairs is None and t.final:
            pairs, method = model.table.viterbi_align(word, t.final), "viterbi"
        if not pairs:
            pairs, method = [(c, "") for c in word.lower()], "none"   # cannot explain sounds
        with self.conn:
            self.conn.execute("INSERT OR REPLACE INTO g2p_alignment VALUES (?, ?, ?, ?)",
                              (word, lang, method, json.dumps(pairs, ensure_ascii=False)))
        return pairs

    def _kind_and_freq(self, word: str, lang: str, kind: str | None) -> tuple[str, float]:
        cats = dict(self.conn.execute(
            "SELECT category, frequency_norm FROM entries WHERE lang = ? AND text = ?", (lang, word)))
        if not cats:  # case-insensitive fallback ("Pferd" vs entry "pferd")
            cats = dict(self.conn.execute(
                "SELECT category, frequency_norm FROM entries WHERE lang = ? AND text = ? COLLATE NOCASE",
                (lang, word)))
        if kind is None:
            if cats:
                kind = kind_of(cats)
            else:
                kind = "name" if self.known.known_as(word, "name", lang) == "name" else "word"
        if "word" in cats:
            freq = cats["word"] or 0.0
        else:  # word not in our top-N list: place its Zipf value on the list's scale
            from wordfreq import zipf_frequency
            lo, hi = self._model(lang).zipf_range
            z = zipf_frequency(word, lang)
            freq = min(max((z - lo) / (hi - lo), 0.0), 1.0) if hi > lo else 0.0
        return kind, freq

    # --- public API ------------------------------------------------------------
    def score_many(self, original: str, variants: list[str], lang: str,
                   kind: str | None = None, textclass: str | None = None) -> list[Score]:
        """Score many variants of one original in one batch (one eSpeak call)."""
        if textclass is not None:
            kind = config.TEXTCLASS_TO_KIND.get(textclass, kind)
        original = normalize(original)
        variants = [normalize(v) for v in variants]
        model = self._model(lang)
        # use the DB spelling if the original exists with different case
        row = self.conn.execute("SELECT text FROM g2p_alignment WHERE lang = ? AND text = ? "
                                "COLLATE NOCASE", (lang, original)).fetchone()
        key = original if row is None or row[0] == original else row[0]
        pairs = self._alignment(key, lang)
        kind, freq = self._kind_and_freq(key, lang, kind)
        ipas = self.ipa([original, *variants], lang)
        o_ipa, v_ipas = ipas[0], ipas[1:]
        stress_idx = 0
        if lang == "ru":
            stress_idx = stressed_vowel_index(self._phonemize([original], lang, with_stress=True)[0])

        out = []
        for v, v_ipa in zip(variants, v_ipas):
            same = v_ipa == o_ipa or (lang == "ru" and ru_equivalent(original, v, o_ipa, v_ipa, stress_idx))
            sim = 1.0 if same else similarity(o_ipa, v_ipa)
            if v.casefold() == original.casefold():
                lp, ch = 0.0, 0
            else:
                lp, ch = explain_variant(v.replace(" ", ""), pairs, model.table, model.neighbours)
            known_as = self.known.known_as(v, kind, lang)
            pl = plausibility(kind, known_as, freq, lp, ch, sim)
            out.append(Score(original, v, lang, kind, round(pl, 4), round(sim, 4), same,
                             known_as, round(lp, 3), ch, o_ipa, v_ipa))
        return out

    def score(self, original: str, variant: str, lang: str, kind: str | None = None,
              textclass: str | None = None) -> Score:
        return self.score_many(original, [variant], lang, kind, textclass)[0]

    def rerank(self, original: str, candidates, lang: str, kind: str | None = None,
               textclass: str | None = None, weight: float = 1.0) -> list[Score]:
        """Sort candidates by plausibility.

        `candidates`: list of strings, or (text, own_score) pairs, e.g. the pipeline's
        Whisper-embedding cosine similarity. With weight w the sort key is
        plausibility**w * own_score (w=0: own score only, w=1: both equally).
        Candidates identical to the original are dropped.
        """
        items = [(c, None) if isinstance(c, str) else (c[0], c[1]) for c in candidates]
        items = [(t, s) for t, s in items if normalize(t).casefold() != normalize(original).casefold()]
        scores = self.score_many(original, [t for t, _ in items], lang, kind, textclass)
        for sc, (_, own) in zip(scores, items):
            sc.extra = own

        def key(sc: Score) -> float:
            own = sc.extra if sc.extra is not None else 1.0
            return math.pow(max(sc.plausibility, 1e-9), weight) * own

        return sorted(scores, key=key, reverse=True)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Score phonetic mistakes: ORIGINAL VARIANT [VARIANT ...]")
    ap.add_argument("lang", choices=config.LANGS)
    ap.add_argument("original")
    ap.add_argument("variants", nargs="+")
    ap.add_argument("--kind", choices=["name", "word"])
    ap.add_argument("--db-path", default=str(config.DEFAULT_DB_PATH))
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.WARNING)
    lex = Lexicon(a.db_path)
    scores = lex.rerank(a.original, a.variants, a.lang, kind=a.kind)
    if a.json:
        print(json.dumps([s.as_dict() for s in scores], ensure_ascii=False, indent=1))
        return 0
    from .report import _table
    print(_table([(s.variant, s.kind, round(s.plausibility, 3), round(s.similarity, 2), s.same_sound,
                   s.known_as or "-", s.n_changes, s.ipa_original, s.ipa_variant) for s in scores],
                 ["variant", "kind", "plausibility", "similarity", "same sound", "known as",
                  "changes", "ipa original", "ipa variant"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
