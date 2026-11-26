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


def _known_as(known_as, kind: str) -> str | None:
    """Accept the old bool form: True = known as the original's own kind."""
    if known_as is True:
        return kind
    return known_as or None


def prior(kind: str, known_as, orig_freq_norm: float) -> float:
    """known_as: 'name' | 'word' | None (see KnownSpellings.known_as)."""
    known_as = _known_as(known_as, kind)
    if kind == "name":
        if known_as == "name":
            return config.PRIOR_NAME_KNOWN
        if known_as == "word":
            return config.PRIOR_NAME_AS_WORD
        return config.PRIOR_NAME_UNKNOWN
    if known_as == "word":
        return config.PRIOR_WORD_KNOWN
    # non-word misspelling of a known word: rarer words are a bit more plausible
    f = min(max(orig_freq_norm, 0.0), 1.0)
    return config.PRIOR_WORD_UNKNOWN_MIN + (config.PRIOR_WORD_UNKNOWN_MAX - config.PRIOR_WORD_UNKNOWN_MIN) * (1 - f)


def plausibility(kind: str, known_as, orig_freq_norm: float,
                 logp: float, n_changes: int, similarity: float) -> float:
    """A known spelling (real name / real word) is written as such, so how unusual
    the letter changes are does not matter for it; typicality only applies to
    spellings nobody uses yet."""
    known_as = _known_as(known_as, kind)
    if kind == "word" and known_as == "name":
        known_as = None  # a surname is not a German word: Pferd -> Fert stays unknown
    t = 1.0 if known_as else typicality(logp, n_changes)
    return prior(kind, known_as, orig_freq_norm) * t * similarity


@dataclass
class KnownSpellings:
    """Which spellings exist (category-aware, see ADR-0012 and ADR-0013).

    curated_names: our own name/place entries (top names per country, GeoNames).
    dataset_names: every spelling in names-dataset; it also contains many ordinary
                   words people typed as names ("Filling", "up"), so a dataset name
                   that is a common word in the language counts as a *word*, not a name.
    """
    curated_names: set[str]
    dataset_names: set[str]
    words: dict[str, set[str]]         # lang -> word entries (casefolded)

    def known_as(self, variant: str, kind: str, lang: str) -> str | None:
        v = variant.casefold().strip()
        if not v:
            return None
        is_words = all(self._is_word(t, lang) for t in v.split())
        if kind == "name":
            if v in self.curated_names or (v in self.dataset_names and not is_words):
                return "name"
            return "word" if is_words else None
        return "word" if is_words else None

    def is_known(self, variant: str, kind: str, lang: str) -> bool:
        """Known as the same kind as the original."""
        return self.known_as(variant, kind, lang) == kind

    def _is_word(self, t: str, lang: str) -> bool:
        if t in self.words.get(lang, set()):
            return True
        from wordfreq import zipf_frequency
        return zipf_frequency(t, lang) >= config.WORD_KNOWN_ZIPF


def load_known(conn, names_dataset_spellings: set[str]) -> KnownSpellings:
    curated: set[str] = set()
    words: dict[str, set[str]] = {}
    for text, lang, cat in conn.execute("SELECT text, lang, category FROM entries"):
        if cat in NAME_CATEGORIES:
            curated.add(text.casefold())
        else:
            words.setdefault(lang, set()).add(text.casefold())
    return KnownSpellings(curated, set(names_dataset_spellings), words)
