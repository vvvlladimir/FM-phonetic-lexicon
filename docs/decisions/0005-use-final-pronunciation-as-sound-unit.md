---
status: accepted
date: 2026-11-23
decision-makers: project author
---

# Use eSpeak's final pronunciation (not the raw rule output) as the "sound" of a letter group

## Context and Problem Statement

After applying spelling rules, eSpeak changes sounds depending on context. For example, Russian unstressed «о» becomes [ʌ]: the rule gives `о→o`, but *молоко* is finally `mVlVko`. The sound→spelling table could use either the rule output or the final pronunciation aligned back to the letters.

## Considered Options

* **rule**: the sound is the phonemes of the winning spelling rule.
* **final**: the eSpeak final phoneme string is split over the letter groups by a small edit-distance DP (`align_to_final`). In that DP, vowel↔vowel edits are cheap, and a vowel cannot be absorbed by a consonant-only group.

## Decision Outcome

We chose **final**. In the prototype (4000 originals per language) it was better or equal in 9 of 10 languages on "at least one same-sound variant in the top 10". The difference is clearest where pronunciation diverges from spelling rules:

| lang | rule | final |
|---|---|---|
| ru | 28% | 52% |
| nl | 79% | 84% |
| pt | 89% | 91% |
| it | 63% | 68% |

Polish had a higher precision with the rule level (P@10 71% vs. 58%) but the same coverage. We accept that.

### Consequences

* Good: the table describes what a listener hears, which is what mistakes are about.
* Bad: the DP is heuristic and works on eSpeak mnemonic characters, not on segmented phonemes. Occasional misalignments are possible, e.g. a vowel assigned to a neighbouring group.

### Confirmation

`tests/test_g2p.py::test_align_to_final_handles_vowel_reduction`. Prototype metrics are in [../results/prototype_report.txt](../results/prototype_report.txt).
