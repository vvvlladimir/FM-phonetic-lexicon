"""String normalization and validity filters shared by all sources."""
from __future__ import annotations

import re
import unicodedata

from . import config

_WS = re.compile(r"\s+")
# Punctuation allowed inside names/places ("O'Brien", "Saint-Denis", "Van Dijk").
NAME_PUNCT = set(" -'")
# Typographic variants mapped to ASCII so "People’s" and "People's" dedupe.
_PUNCT_MAP = str.maketrans({"’": "'", "‘": "'", "ʼ": "'", "‐": "-", "‑": "-", "–": "-"})


def normalize(text: str) -> str:
    """Unicode NFC, unify apostrophes/hyphens, trim, collapse internal whitespace."""
    text = unicodedata.normalize("NFC", text).translate(_PUNCT_MAP)
    return _WS.sub(" ", text).strip()


def _script_ok(text: str, lang: str) -> bool:
    script = config.LANG_SCRIPT.get(lang, "LATIN")
    for ch in text:
        if ch.isalpha() and not unicodedata.name(ch, "").startswith(script):
            return False
    return True


def is_valid(text: str, lang: str, category: str) -> bool:
    """Reject digits, disallowed punctuation, too short, or wrong script."""
    if len(text) < 2 or any(ch.isdigit() for ch in text):
        return False
    allowed = set() if category == "word" else NAME_PUNCT
    for ch in text:
        if not (ch.isalpha() or ch in allowed or unicodedata.category(ch).startswith("M")):
            return False
    if not any(ch.isalpha() for ch in text):
        return False
    return _script_ok(text, lang)


def clean(text: str, lang: str, category: str) -> str | None:
    """Normalize and validate; return None if the text should be dropped."""
    t = normalize(text)
    return t if is_valid(t, lang, category) else None


def dedupe(records: list[dict], higher_is_better: bool) -> list[dict]:
    """Keep one record per (text, lang, category): the most frequent one."""
    best: dict[tuple, dict] = {}
    for r in records:
        key = (r["text"], r["lang"], r["category"])
        cur = best.get(key)
        if cur is None:
            best[key] = r
            continue
        f, cf = r["frequency"], cur["frequency"]
        if (f > cf) if higher_is_better else (f < cf):
            best[key] = r
    return list(best.values())
