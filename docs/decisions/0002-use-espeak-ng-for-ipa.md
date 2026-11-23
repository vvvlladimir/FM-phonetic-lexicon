---
status: accepted
date: 2026-11-23
decision-makers: project author
---

# Generate IPA with eSpeak NG (via phonemizer); WikiPron only as a cross-check

## Context and Problem Statement

Every entry needs a phonetic transcription in 10 languages. Many entries are names and foreign place names, which have no human transcription.

## Decision Drivers

* Coverage: every string needs IPA, including rare surnames.
* One consistent system for all 10 languages, so that "same IPA" means the same thing everywhere.
* It must be fast on the CPU.
* Step 2 must be able to re-pronounce *new* spellings the same way, to check generated variants.

## Considered Options

* eSpeak NG, a rule-based system, via `phonemizer` with one backend per language and batched calls.
* WikiPron, human transcriptions from Wiktionary.
* Neural G2P models (e.g. CharsiuG2P) and Epitran.

## Decision Outcome

We chose **eSpeak NG 1.52** with `with_stress=False`, `preserve_punctuation=False` and `language_switch=remove-flags`. Voices: en-us, de, fr-fr, es, it, pt, nl, ru, pl, tr.

WikiPron goes into a separate table, `reference_pron`, and is used only to cross-check eSpeak.

### Consequences

* Good: it covers 100% of entries except one. The French word "ent" gives empty output, which is linguistically correct because it is a silent verb ending.
* Good: about 48k texts per language are phonemized in about 1 s.
* Good: the same engine checks generated variants in step 2, so "same IPA" is consistent.
* Bad: eSpeak is a rule system, not ground truth. Exact agreement with WikiPron ranges from 3% (ru) to 82% (fr). Most mismatches are differences in notation:
  * Russian WikiPron has only narrow transcription;
  * German WikiPron marks the glottal stop /ʔ/;
  * en-us eSpeak gives some British vowels (/wɜː/ for "were").
* Bad: eSpeak guesses stress for unknown words. This matters for Russian; see ADR-0008.

### Confirmation

The step-1 report, section 5, prints the eSpeak vs. WikiPron agreement per language with example mismatches.

## More Information

* Bernard & Titeux (2021), phonemizer, JOSS 6(68).
* Lee et al. (2020), WikiPron, LREC.
