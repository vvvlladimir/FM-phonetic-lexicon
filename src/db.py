"""SQLite schema and write helpers."""
from __future__ import annotations

import math
import sqlite3
from pathlib import Path

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS entries (
  id INTEGER PRIMARY KEY,
  text TEXT NOT NULL,
  lang TEXT NOT NULL,              -- language the text is pronounced in
  category TEXT NOT NULL,          -- first_name | last_name | city | country | word
  origin_country TEXT,             -- ISO alpha-2, NULL for plain words
  frequency REAL,                  -- source-specific raw value
  frequency_norm REAL,             -- 0..1 within (lang, category)
  source TEXT NOT NULL,            -- names-dataset | geonames | wordfreq
  ipa TEXT,                        -- NULL = not computed yet, '' = eSpeak gave nothing
  UNIQUE(text, lang, category)
);
CREATE INDEX IF NOT EXISTS idx_entries_ipa  ON entries(lang, ipa);
CREATE INDEX IF NOT EXISTS idx_entries_text ON entries(lang, text);
CREATE INDEX IF NOT EXISTS idx_entries_cat  ON entries(category, origin_country);

CREATE TABLE IF NOT EXISTS reference_pron (
  id INTEGER PRIMARY KEY,
  word TEXT NOT NULL,
  lang TEXT NOT NULL,
  ipa TEXT NOT NULL,               -- as in WikiPron (space-separated segments)
  ipa_compact TEXT NOT NULL,       -- spaces, stress and syllable marks removed
  source_file TEXT NOT NULL,
  UNIQUE(word, lang, ipa)
);
CREATE INDEX IF NOT EXISTS idx_ref_word ON reference_pron(lang, word);

-- Step 2: letter <-> sound alignment (docs/decisions/0004, 0005)
CREATE TABLE IF NOT EXISTS g2p_alignment (
  text TEXT NOT NULL,
  lang TEXT NOT NULL,
  method TEXT NOT NULL,            -- rules (eSpeak -X trace) | viterbi (eSpeak dictionary word)
  pairs TEXT NOT NULL,             -- JSON [[letters, sound], ...], sound = eSpeak mnemonic
  PRIMARY KEY (text, lang)
);

CREATE TABLE IF NOT EXISTS sound_spelling (
  lang TEXT NOT NULL,
  sound TEXT NOT NULL,             -- eSpeak mnemonic, '' = silent letters
  sound_ipa TEXT,                  -- approximate IPA of the sound
  position TEXT NOT NULL,          -- B (word start) | M | E (word end)
  letters TEXT NOT NULL,
  count INTEGER NOT NULL,
  prob REAL NOT NULL,              -- P(letters | sound, position)
  PRIMARY KEY (lang, sound, position, letters)
);

CREATE TABLE IF NOT EXISTS variants (
  id INTEGER PRIMARY KEY,
  text TEXT NOT NULL,              -- original (as in entries.text)
  lang TEXT NOT NULL,
  variant TEXT NOT NULL,
  kinds TEXT NOT NULL,             -- comma list: respell, silent, near, deaccent
  match TEXT NOT NULL,             -- homophone | near
  similarity REAL NOT NULL,        -- 1 - PanPhon feature distance (1 = same sound)
  score REAL NOT NULL,             -- log-probability of the spelling changes (+ bonus)
  attested_name INTEGER NOT NULL,  -- variant spelling exists in names-dataset
  attested_entry INTEGER NOT NULL, -- variant exists in entries (same lang)
  ipa TEXT NOT NULL,
  UNIQUE (text, lang, variant)
);
CREATE INDEX IF NOT EXISTS idx_variants_text ON variants(lang, text);
"""

UPSERT = """
INSERT INTO entries (text, lang, category, origin_country, frequency, source)
VALUES (:text, :lang, :category, :origin_country, :frequency, :source)
ON CONFLICT(text, lang, category) DO UPDATE SET
  origin_country = excluded.origin_country,
  frequency      = excluded.frequency,
  source         = excluded.source
"""  # note: ipa is never touched by an upsert -> cache survives re-runs


def connect(path: Path | str) -> sqlite3.Connection:
    if str(path) != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.executescript(SCHEMA)
    return conn


def upsert_entries(conn: sqlite3.Connection, records: list[dict]) -> int:
    with conn:
        conn.executemany(UPSERT, records)
    return len(records)


def update_frequency_norm(conn: sqlite3.Connection) -> None:
    """Recompute frequency_norm in 0..1 (1 = most frequent) per (lang, category)."""
    groups = conn.execute(
        "SELECT lang, category, MIN(frequency), MAX(frequency) FROM entries "
        "WHERE frequency IS NOT NULL GROUP BY lang, category"
    ).fetchall()
    conn.create_function("log1p", 1, lambda x: math.log1p(max(x, 0)) if x is not None else None)
    with conn:
        for lang, cat, lo, hi in groups:
            scale = config.FREQ_SCALE[cat]
            if scale == "log":
                expr, lo, hi = "log1p(frequency)", math.log1p(max(lo, 0)), math.log1p(max(hi, 0))
            else:
                expr = "frequency"
            span = hi - lo
            if span == 0:
                norm = "1.0"
            elif scale == "rank":
                norm = f"1.0 - ({expr} - {lo}) / {span}"
            else:
                norm = f"({expr} - {lo}) / {span}"
            conn.execute(
                f"UPDATE entries SET frequency_norm = {norm} "
                "WHERE lang = ? AND category = ? AND frequency IS NOT NULL",
                (lang, cat),
            )
