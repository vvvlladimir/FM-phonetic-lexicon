"""IPA transcription with eSpeak NG via phonemizer, cached in the DB.

Cache rule: an (text, lang) whose `ipa` is not NULL is never phonemized again.
`ipa = ''` marks texts for which eSpeak returned nothing (reported, not retried).
"""
from __future__ import annotations

import logging
import sqlite3
from typing import Callable

from tqdm import tqdm

from . import config

log = logging.getLogger(__name__)

PhonemizeFn = Callable[[list[str]], list[str]]


def make_espeak_phonemizer(lang: str, with_stress: bool = False) -> PhonemizeFn:
    """Create ONE eSpeak backend for `lang` and return a batch phonemize function."""
    from phonemizer.backend import EspeakBackend
    from phonemizer.backend.espeak.wrapper import EspeakWrapper
    from phonemizer.separator import Separator

    lib = config.espeak_library()
    if lib:
        EspeakWrapper.set_library(lib)
    # phonemizer warns about every language switch / word-count mismatch; silence it
    quiet = logging.getLogger("phonemizer")
    quiet.setLevel(logging.ERROR)
    backend = EspeakBackend(
        config.ESPEAK_VOICES[lang],
        preserve_punctuation=False,
        with_stress=with_stress,
        language_switch="remove-flags",
        logger=quiet,
    )
    sep = Separator(phone="", syllable="", word=" ")

    def phonemize(texts: list[str]) -> list[str]:
        out = backend.phonemize(texts, separator=sep, strip=True, njobs=1)
        if len(out) != len(texts):  # should not happen; never misalign the cache
            raise RuntimeError(f"phonemizer returned {len(out)} lines for {len(texts)} inputs")
        return [o.strip() for o in out]

    return phonemize


def reuse_cached(conn: sqlite3.Connection, lang: str) -> int:
    """Copy IPA from another row with the same (text, lang), e.g. word 'paris' <- city."""
    with conn:
        cur = conn.execute(
            """UPDATE entries SET ipa = (
                   SELECT e2.ipa FROM entries e2
                   WHERE e2.lang = entries.lang AND e2.text = entries.text
                     AND e2.ipa IS NOT NULL LIMIT 1)
               WHERE lang = ? AND ipa IS NULL
                 AND EXISTS (SELECT 1 FROM entries e2
                             WHERE e2.lang = entries.lang AND e2.text = entries.text
                               AND e2.ipa IS NOT NULL)""",
            (lang,),
        )
    return cur.rowcount


def fill_ipa(
    conn: sqlite3.Connection,
    lang: str,
    phonemizer_factory: Callable[[str], PhonemizeFn] = make_espeak_phonemizer,
    batch_size: int = config.IPA_BATCH_SIZE,
) -> dict:
    """Phonemize every (text, lang) still lacking IPA. Commits after each batch."""
    reused = reuse_cached(conn, lang)
    todo = [r[0] for r in conn.execute(
        "SELECT DISTINCT text FROM entries WHERE lang = ? AND ipa IS NULL ORDER BY text",
        (lang,),
    )]
    stats = {"reused": reused, "phonemized": 0, "empty": 0}
    if not todo:
        log.info("[ipa %s] nothing to do (reused %d from cache)", lang, reused)
        return stats

    phonemize = phonemizer_factory(lang)  # backend created once per language
    for i in tqdm(range(0, len(todo), batch_size), desc=f"IPA {lang}", unit="batch"):
        chunk = todo[i : i + batch_size]
        ipas = phonemize(chunk)
        with conn:
            conn.executemany(
                "UPDATE entries SET ipa = ? WHERE lang = ? AND text = ? AND ipa IS NULL",
                [(ipa, lang, t) for t, ipa in zip(chunk, ipas)],
            )
        stats["phonemized"] += len(chunk)
        stats["empty"] += sum(1 for x in ipas if not x)
    log.info("[ipa %s] phonemized=%d empty=%d reused=%d",
             lang, stats["phonemized"], stats["empty"], reused)
    return stats
