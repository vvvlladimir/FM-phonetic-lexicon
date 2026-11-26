"""How plausible is it that someone writes `variant` instead of `original`?  (ADR-0012)

    plausibility = prior(category, variant known?, original frequency)
                   x typicality(spelling changes)
                   x similarity(sound)

* prior: names have many legitimate spellings, so a name variant is plausible,
  especially if that spelling exists (Philip -> Phillip).  A common *word* is
  spelled correctly by almost everyone; a misspelling is plausible only if the
  result is another real word (a mishearing, Pferd -> fährt), otherwise it is
  implausible, the more so the more frequent the word (Pferd -> Fert).
* typicality: geometric mean of P(new letters | sound) over the changed letter
  groups, so three typical changes (Philip -> Fillipp) are not punished more
  than one atypical change.  Only for unknown spellings: a real name or word is
  simply written as that name/word (typicality = 1).
* similarity: 1 for same sound, PanPhon similarity otherwise.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from . import config

NAME_CATEGORIES = {"first_name", "last_name", "city", "country"}


def kind_of(categories) -> str:
    """'name' if the text is used as a person/place name in the DB, else 'word'."""
    return "name" if NAME_CATEGORIES & set(categories) else "word"


def typicality(logp: float, n_changes: int) -> float:
    """exp(mean log-probability per changed letter group), in (0, 1]."""
    if n_changes <= 0:
        return 1.0
    return math.exp(max(logp, -20.0) / n_changes)


def prior(kind: str, variant_known: bool, orig_freq_norm: float) -> float:
    if kind == "name":
        return config.PRIOR_NAME_KNOWN if variant_known else config.PRIOR_NAME_UNKNOWN
    if variant_known:
        return config.PRIOR_WORD_KNOWN
    # non-word misspelling of a known word: rarer words are a bit more plausible
    f = min(max(orig_freq_norm, 0.0), 1.0)
    return config.PRIOR_WORD_UNKNOWN_MIN + (config.PRIOR_WORD_UNKNOWN_MAX - config.PRIOR_WORD_UNKNOWN_MIN) * (1 - f)


def plausibility(kind: str, variant_known: bool, orig_freq_norm: float,
                 logp: float, n_changes: int, similarity: float) -> float:
    """A known spelling (real name / real word) is written as such, so how unusual
    the letter changes are does not matter for it; typicality only applies to
    spellings nobody uses yet."""
    t = 1.0 if variant_known else typicality(logp, n_changes)
    return prior(kind, variant_known, orig_freq_norm) * t * similarity


@dataclass
class KnownSpellings:
    """Which spellings exist, per kind (category-aware, see ADR-0012)."""
    names: set[str]                    # names-dataset + all name/place entries (casefolded)
    words: dict[str, set[str]]         # lang -> word entries (casefolded)

    def is_known(self, variant: str, kind: str, lang: str) -> bool:
        v = variant.casefold()
        if kind == "name":
            return v in self.names
        if v in self.words.get(lang, set()):
            return True
        from wordfreq import zipf_frequency
        return zipf_frequency(v, lang) >= config.WORD_KNOWN_ZIPF


def load_known(conn, names_dataset_spellings: set[str]) -> KnownSpellings:
    names = set(names_dataset_spellings)
    words: dict[str, set[str]] = {}
    for text, lang, cat in conn.execute("SELECT text, lang, category FROM entries"):
        if cat in NAME_CATEGORIES:
            names.add(text.casefold())
        else:
            words.setdefault(lang, set()).add(text.casefold())
    return KnownSpellings(names, words)
