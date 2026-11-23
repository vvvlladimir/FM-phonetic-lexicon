---
status: accepted
date: 2026-11-23
decision-makers: project author
---

# Store the lexicon and derived tables in one SQLite file with an idempotent pipeline

## Context and Problem Statement

The knowledge base has the following parts:

* entries: about 420k names, places and words with their IPA;
* reference pronunciations from WikiPron;
* step-2 tables: letter–sound alignments, sound→spelling statistics and generated variants.

It has to run on a laptop on the CPU only, survive crashes, and be easy to query from the existing TTS→noise→STT pipeline.

## Decision Drivers

* Building it must be resumable and safe to re-run.
* There must be no server to set up.
* Ad-hoc analysis should be possible in SQL, e.g. finding homophone pairs with a self-join.

## Considered Options

* One SQLite file.
* CSV or Parquet files per source.
* PostgreSQL.

## Decision Outcome

We chose **one SQLite file** (`data/lexicon.db`, WAL mode).

* `entries` has `UNIQUE(text, lang, category)` and is filled with upserts.
* An upsert never touches `ipa`, so the IPA cache survives re-runs.
* IPA is computed only where `ipa IS NULL`, in batches with one commit each, so a crash loses at most one batch.
* `ipa = ''` marks texts for which eSpeak produced no output. They are reported and not retried.
* The step-2 tables (`g2p_alignment`, `sound_spelling`, `variants`) are derived data. They are deleted and rebuilt per language.

### Consequences

* Good: re-running after a crash or with more languages costs nothing extra. Verified: a full re-run phonemized 0 texts.
* Good: one file is easy to hand over and to query from Python or the `sqlite3` CLI.
* Bad: the file is about 540 MB: about 280 MB after step 1, mostly WikiPron, and about 1.7M stored variants after step 2. It is too large for git, so it stays git-ignored and is reproduced with the scripts.
* Bad: rows are never deleted from `entries`. Lowering `--top-n` leaves the old rows in place.

### Confirmation

`tests/test_db.py` checks the UNIQUE and NOT NULL constraints and that an upsert keeps the IPA. `tests/test_ipa.py` checks the cache, resuming after a crash, and that empty output is not retried.
