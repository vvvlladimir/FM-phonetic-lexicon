---
status: accepted
date: 2026-11-23
decision-makers: project author
---

# Generate variants by beam search over a sound→spelling probability table, then verify with eSpeak

## Context and Problem Statement

Given an aligned word, we need plausible alternative spellings. Some should sound the same (*Philip → Filip*), and some should sound slightly different (*Pferd → Fert*). The candidates should be ranked by how typical the change is.

## Considered Options

* A **count table plus beam search** (noisy-channel style). P(letters | sound, position) is counted from all aligned words of a language, and letter groups are replaced while the product of probabilities is kept.
* A **neural phoneme-to-grapheme model** (e.g. PolyIPA, 2024; Bi-Phone-style generative model). This needs training data and a GPU, and it is hard to explain in a report.
* **Hand-written rules per language.** This does not scale to 10 languages.

## Decision Outcome

We chose the **count table plus beam search**. This is the approach of Bhagat & Hovy (2007) and of Google patent US11893349B2: a "phoneme→letter density" model plus a "phoneme→phoneme error" model.

* **Table**: `sound_spelling(lang, sound, position B/M/E, letters, count, prob)`. Silent letters are the sound `''`.
* **Change kinds**:
  * `respell`: other letters for the same sound (ph→f);
  * `silent`: drop, swap or append silent letters (Philippe→Philipe, French -s/-t/-e). Only letters that are silent in at least half of their occurrences at that position are used. Without this filter, alignment noise made German final "n" a "silent letter" (*pferd→pferdn*).
  * `near`: letters of a similar sound (ADR-0007), at most one per variant;
  * `deaccent`: drop diacritics (ADR-0010).
* **Score** (`logp`): the sum of log P(new letters | sound, position) over the changed groups, −2 per `near` change. Ranking uses `plausibility` (ADR-0012), which superseded the attestation bonus of ADR-0009. There are at most 3 changes per variant, the beam is 300, and 40 candidates are generated per original.
* **Verification**: every candidate is re-phonemized with eSpeak.
  * Identical IPA → `match = homophone`. Russian is the exception, see ADR-0008.
  * PanPhon similarity ≥ 0.80 → `match = near`.
  * Everything else is discarded.
* **Storage**: up to 20 homophones and 20 near variants per original, both ranked by plausibility (ADR-0012).
  * Similarity is only the entry threshold. Ranking near variants by similarity would push out the most interesting ones, the dropped sounds: *Pferd→Fert* has similarity 0.80, while *pferd→pfert* has 0.98.

### Consequences

* Good: fully explainable. Every variant lists its change kinds and score, and every probability can be traced to counts.
* Good: language-independent. One code path serves all 10 languages.
* Bad: positions are only B/M/E. Wider context (e.g. "c" before "e/i") is not modelled in generation, but eSpeak verification removes the wrong results.
* Bad: only single-token entries are processed ("New York" is skipped for now).

### Confirmation

The step-2 report prints coverage, the share of candidates that verify, attested shares, and recall of real spelling pairs from step 1 (pairs with identical IPA in `entries`) per language.

## More Information

* Bhagat & Hovy (2007), *Phonetic Models for Generating Spelling Variants*, IJCAI.
* US11893349B2, *Systems and methods for generating locale-specific phonetic spelling variations*.
* The Nigerian Pidgin orthographic variation paper (arXiv 2404.18264) also filters candidates by pronunciation distance.
