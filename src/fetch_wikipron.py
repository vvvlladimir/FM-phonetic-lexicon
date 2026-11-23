"""WikiPron reference pronunciations (scraped from Wiktionary, CC BY-SA) -> reference_pron.

Used only to cross-check eSpeak output; never mixed into `entries`.
"""
from __future__ import annotations

import logging
import re
import sqlite3

from . import config
from .download import download
from .normalize import normalize

log = logging.getLogger(__name__)

# Characters stripped for comparison with eSpeak (which we run without stress).
_COMPACT = re.compile(r"[\sˈˌ.‿]")


def compact(ipa: str) -> str:
    return _COMPACT.sub("", normalize(ipa))


def load_into(conn: sqlite3.Connection, langs: list[str]) -> None:
    for lang in langs:
        fname = config.WIKIPRON_FILES.get(lang)
        if not fname:
            log.warning("[wikipron] no file configured for %s", lang)
            continue
        path = download(config.WIKIPRON_BASE_URL + fname, config.WIKIPRON_DIR / fname)
        rows = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                parts = line.rstrip("\n").split("\t")
                if len(parts) < 2:
                    continue
                word, ipa = normalize(parts[0]), normalize(parts[1])
                rows.append((word, lang, ipa, compact(ipa), fname))
        with conn:
            conn.executemany(
                "INSERT OR IGNORE INTO reference_pron (word, lang, ipa, ipa_compact, source_file) "
                "VALUES (?, ?, ?, ?, ?)", rows)
        log.info("[wikipron] %s: %d rows from %s", lang, len(rows), fname)
