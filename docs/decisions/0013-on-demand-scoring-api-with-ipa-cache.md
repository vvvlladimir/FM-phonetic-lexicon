---
status: accepted
date: 2026-11-26
decision-makers: project author
---

# Offer an on-demand scoring API (`src/lexicon.py`) with an IPA cache in the DB

## Context and Problem Statement

The TTS–STT pipeline (Hak, 2026) produces many noisy transcriptions per input and picks one only by acoustic similarity (Whisper embeddings). Its section 8.6 names the missing piece: "Missing Semantic Knowledge". This knowledge base should supply that piece. That needs three things:

* **One call** that scores any (original, candidate) pair. The pipeline's candidates are arbitrary STT output, not the variants we generated.
* **IPA for strings we have never seen**, as the supervisor's task states: "Ad hoc nutzen von Phonemizer + eSpeak NG und Ergebnis in DB speichern".
* **Speed**: dozens of candidates per entry.

## Considered Options

* Ask the pipeline to query the `variants` table only. This misses most STT outputs, because they are not among our generated variants.
* A web service (HTTP). That is extra infrastructure, while both projects are Python.
* **A Python class over the same SQLite file**, plus a small CLI.

## Decision Outcome

We chose **`Lexicon`** in `src/lexicon.py`, with `score`, `score_many`, `rerank` and `ipa`, plus `python -m src.lexicon LANG ORIGINAL VARIANT...`.

* **IPA lookup order**: `entries` → `ipa_cache` → eSpeak. Missing texts are phonemized in one batch and written to the new table `ipa_cache`. The DB grows with use, and a repeated call never runs eSpeak again.
* **Unknown originals** (e.g. "Hak") are traced with `espeak-ng -X` on the fly (ADR-0004) and stored in `g2p_alignment`.
* **Per-language data** (the sound→spelling table and neighbour sounds) is rebuilt from `sound_spelling` once and kept in memory.
* **Known names**: names-dataset spellings are stored once in the new table `known_names`, written by `build_variants`. This way the API starts in about 4 s instead of loading names-dataset (3 GB RAM).
* **Pipeline text classes**: `config.TEXTCLASS_TO_KIND` maps `NAME`→name and `NATURAL_TEXT`→word. `NUMBER` is not scored.
* **`rerank(original, [(text, own_score), …], weight=w)`** sorts by `plausibility**w × own_score`. The pipeline can thus keep its acoustic ranking and add ours: `w = 0` uses its score only, `w = 1` weighs both equally. Candidates identical to the original are dropped, as in the pipeline.
* **Multi-word STT output** ("pill up") is supported. It counts as known if every word is known, and spaces are ignored for typicality.

### Change to ADR-0012 found while testing

names-dataset contains many ordinary words typed as names ("Filling", "pill", "up"). Philip → "pill up" therefore scored 0.96 as a "real name". `KnownSpellings.known_as` now returns `name`, `word` or `None`:

* A spelling counts as a *name* if it is in our curated name or place entries, or in names-dataset **and** not a common word of the language (Zipf < 3).
* A name heard as ordinary word(s) gets a new prior, `PRIOR_NAME_AS_WORD = 0.5`.

Results with the full DB:

| original → candidate | known as | plausibility |
|---|---|---|
| Philip → Phillip / Fillip | name | 1.00 |
| Philip → "pill up" | word | 0.48 |
| Philip → Filling | word | 0.47 |
| Philip → Fillipp | — | 0.085 |
| Pferd → fährt | word | 0.57 |
| Pferd → Fert | — | 0.018 |
| Hak → Haag, Haack (de) | name | 1.00 |

### Consequences

* Good: the pipeline can filter or rerank its candidates with one call. Speed: about 4 s start-up; 100 new candidates take 0.85 s, and 0.23 s when cached.
* Good: the DB accumulates IPA for real-world mistakes, which can later serve as evaluation data.
* Bad: the API writes to the DB (`ipa_cache`, `g2p_alignment`). Use one `Lexicon` per process. SQLite WAL allows concurrent readers, but not several writers.
* Open question for the supervisor: an unknown *spelling* of a name (Fillipp, 0.085) currently ranks below the name heard as real words ("pill up", 0.48). For STT mistakes that order is defensible. For typed spelling mistakes it may not be. The constants are in `config.py`.

### Confirmation

`tests/test_lexicon.py` runs on a hand-made DB with a fake phonemizer. It covers the reference cases, cache hits (no second eSpeak call), rerank ordering and weighting, the text-class mapping, and that names-dataset junk counts as words.
