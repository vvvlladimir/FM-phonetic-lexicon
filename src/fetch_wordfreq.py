"""Common words + Zipf frequency from the `wordfreq` package (data bundled, no download)."""
from __future__ import annotations

import logging

from .normalize import clean, dedupe

log = logging.getLogger(__name__)
SOURCE = "wordfreq"


def load(langs: list[str], top_n: int) -> list[dict]:
    from wordfreq import top_n_list, zipf_frequency

    records: list[dict] = []
    for lang in langs:
        # Over-fetch so that we still have top_n words after filtering.
        candidates = top_n_list(lang, top_n * 2)
        kept: list[dict] = []
        seen: set[str] = set()
        for w in candidates:
            text = clean(w, lang, "word")
            if not text or text in seen:
                continue
            seen.add(text)
            kept.append({"text": text, "lang": lang, "category": "word",
                         "origin_country": None,
                         "frequency": zipf_frequency(w, lang), "source": SOURCE})
            if len(kept) >= top_n:
                break
        if len(kept) < top_n:
            log.warning("[wordfreq] %s: only %d valid words (wanted %d)", lang, len(kept), top_n)
        log.info("[wordfreq] %s: %d words (from %d candidates)", lang, len(kept), len(candidates))
        records += kept
    return dedupe(records, higher_is_better=True)
