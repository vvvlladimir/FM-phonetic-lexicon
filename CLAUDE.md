# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

This is a research project at Universität Augsburg, Data Engineering chair. It builds a multilingual knowledge base for generating realistic *phonetic* spelling mistakes (e.g. Philip → Fillip, Pferd → Fert). It covers 10 languages: en, de, fr, es, it, pt, nl, ru, pl, tr.

The project has two pipeline steps. Both write into one SQLite file, `data/lexicon.db`:

1. `src.build_db`: collects names, places and words, then computes their IPA.
2. `src.build_variants`: aligns letters to sounds, builds sound→spelling tables, then generates and verifies spelling variants.

Every method decision has a MADR record in `docs/decisions/` (index: `docs/decisions/README.md`). When you change a method, add a new ADR or update the existing one, and keep the numbers in the ADRs current. Code comments refer to these ADRs by number.

## Commands

Requirements: Python 3.12 venv in `.venv` (created with `uv`) and eSpeak NG 1.52 from Homebrew. The libespeak path is detected in `config.espeak_library()`; you can override it with `PHONEMIZER_ESPEAK_LIBRARY`.

```bash
uv pip install -p .venv -r requirements.txt

.venv/bin/python -m src.build_db --langs en            # step 1, one language (~20 s after downloads)
.venv/bin/python -m src.build_db --wikipron            # step 1, all languages + WikiPron cross-check
.venv/bin/python -m src.build_db --skip-ingest         # only fill missing IPA + print report
.venv/bin/python -W ignore -m src.build_variants --langs de --top-n 200 --report-path /tmp/r.txt   # quick step-2 check
.venv/bin/python -W ignore -m src.build_variants       # step 2, all languages (~8 min); report -> data/report_variants.txt

.venv/bin/python -W ignore -m pytest -q
.venv/bin/python -W ignore -m pytest -q tests/test_g2p.py::test_ru_unstressed_vowels
```

Use `-W ignore` because panphon emits SyntaxWarnings on import. There is no linter configured.

## Architecture: things that span several files

- **IPA cache and idempotency (step 1).** `db.UPSERT` never touches `ipa`. `ipa.fill_ipa` only phonemizes rows with `ipa IS NULL`, in batches, committing after each batch.
  - `ipa = ''` means eSpeak returned nothing. Those rows are reported and never retried.
  - Rows are never deleted from `entries`.
  - The step-2 tables (`g2p_alignment`, `sound_spelling`, `variants`) are derived data. They are deleted and rebuilt for each language you pass.
- **One eSpeak backend per language.** Always phonemize in large lists through `ipa.make_espeak_phonemizer(lang)`; never call it once per word. Settings: `with_stress=False`, `language_switch="remove-flags"`. Russian also uses a `with_stress=True` instance to find the stressed vowel.
- **Script filter (`normalize.is_valid` + `config.LANG_SCRIPT`).** `ru` text must be Cyrillic and all other languages Latin. Otherwise eSpeak switches voice (Latin "Moscow" under `ru` gets read by the English voice).
  - `normalize()` also maps typographic apostrophes and hyphens to ASCII.
  - Country→language mapping lives in `config.COUNTRY_TO_LANG`.
- **Letter↔sound alignment (`espeak_trace.py`, `g2p.py`).** It parses `espeak-ng -X` rule traces, run in batches of 2000 words through one process; on desync the batch is halved and retried. Parser rules:
  - Highest-scoring rule per block wins.
  - Ignore the `Unpronouncable?` pass.
  - Follow later `Translate` blocks only while the letters covered so far are a proper prefix of the word, because eSpeak re-translates stems.
  - The final phoneme line may start with a digit.

  A "sound" is the eSpeak *final* phoneme substring aligned by `align_to_final`, not the raw rule output (ADR-0005). Words taken from eSpeak's exception dictionary fall back to `Table.viterbi_align`.

  Sounds are eSpeak mnemonics (`S`, `aI`, `pF`), not IPA. `phonetic.sound_to_ipa` gets approximate IPA by speaking `[[a<s>a]]`; spoken alone, voiced consonants get devoiced.
- **Variant pipeline (`variants.generate` → `build_variants.run_lang`).** Beam search over `Table` probabilities per (sound, position B/M/E). Change kinds:
  - `respell`, `silent` (only letters silent in at least half their occurrences);
  - `near` (PanPhon neighbour sounds, max 1 per variant);
  - `deaccent`.

  Each candidate is re-phonemized and classified:
  - identical IPA → `homophone`; for ru, `phonetic.ru_equivalent` (unstressed о/а and е/и/я rule) also counts;
  - PanPhon similarity ≥ `config.NEAR_THRESHOLD` (0.80) → `near`;
  - anything else is dropped.

  Ranking is by score, plus a bonus if the spelling exists in names-dataset or in `entries`. Only single-token entries are processed.
- **Languages are fully separate.** Tables, generation and comparison are per language. Nothing compares across languages or scripts (e.g. Philipp vs Филипп).

## Data and constraints

- `data/` (raw downloads, DBs, logs) is git-ignored. Full DB is ~540 MB, reproduced by the scripts.
- Downloads go to `data/raw/` and are skipped if present. On network failure, fail loudly with the manual-download path (`download.DownloadError`); never skip silently or invent data.
- Sources and licenses are in `SOURCES.md`. names-dataset comes from the 2021 Facebook leak; GeoNames is CC BY 4.0. Keep that file current when adding a source.
- Loading names-dataset takes ~3 GB RAM and ~10 s; `fetch_names.all_spellings()` builds a ~1.7M-entry set.
