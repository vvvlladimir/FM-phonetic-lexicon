---
status: accepted
date: 2026-11-23
decision-makers: project author
---

# Measure "sounds similar" with PanPhon feature distance; find similar sounds in two buckets

## Context and Problem Statement

An exact IPA match rejects realistic hearing errors. *pferd → pfert* differs only in vowel length, and *Pferd → Fert* drops one sound. We need a graded similarity, both to keep "near" variants and to decide which sounds count as neighbours when generating them.

## Considered Options

* Plain Levenshtein on IPA characters: /p/→/b/ costs the same as /p/→/a/.
* **PanPhon** (Mortensen et al., 2016). Each IPA segment is a vector of 21+ articulatory features. A substitution costs the share of differing features, so p~b costs 0.04 and m~n 0.13. Insertion or deletion costs 1.
* ALINE or other phonetic aligners, or human confusion matrices (see ADR-0011).

## Decision Outcome

We chose **PanPhon 0.22**:

* `similarity = 1 − feature_edit_distance / max_len` on the full-word IPA. A variant is `near` if the similarity is ≥ 0.80 (`config.NEAR_THRESHOLD`).
  * We first used 0.90. That excluded *Pferd → Fert*: dropping one of five sounds gives a similarity of exactly 0.80. 0.80 allows one dropped sound in a five-sound word, or a few feature changes.
* **Neighbour sounds**, used to generate `near` variants, come from two buckets:
  * *substitution*: same length, both vowels or both consonants, PanPhon distance ≤ 0.3 (p~b, s~z, e~ɛ, m~n);
  * *simplification*: one sound dropped (pf→f, ts→s, aɪ→a).

  The second bucket is needed because PanPhon charges a full 1.0 for a deletion. Without it, *pf* would get neighbours like *kv* instead of *f*, and *Pferd → Fert* would never be generated.
* When several eSpeak mnemonics have the same IPA, e.g. `f` and an alignment fragment `:f`, only the most frequent one is used as a neighbour. Otherwise the rare fragment, which has hardly any spellings, was picked, and *Pferd→Fert* was still missing.
* The IPA of an eSpeak sound mnemonic is obtained by speaking it between two vowels (`[[aba]]`) and cutting the vowels off. Spoken alone, German and Russian voiced consonants are devoiced (b→p), which made b and p look identical.

### Consequences

* Good: a graded and linguistically motivated score, which the next step can reuse to evaluate mistakes.
* Bad: the threshold 0.80 is a judgement call. Similarity is normalised by word length, so one changed consonant is "near" in long words and may be "far" in short ones.
* Bad: the IPA shown for a single sound is context-dependent. In en-us, /t/ between vowels is spoken as a flap, so `t` is displayed as /ɾ/. This affects the report display and neighbour search, not the full-word verification.
* Bad: PanPhon models articulation, not perception. What listeners actually confuse in noise is a different question (ADR-0011).

## More Information

Mortensen et al. (2016), *PanPhon: A Resource for Mapping IPA Segments to Articulatory Feature Vectors*, COLING.
