---
status: superseded by ADR-0012
date: 2026-11-23
decision-makers: project author
---

# Use real spellings (names-dataset, entries) as a ranking bonus, not as a filter

> **Superseded by [ADR-0012](0012-score-plausibility-by-category-and-frequency.md).** The bonus was not category-aware. "Fert" exists as a surname, so *Pferd → Fert* ranked high, although the supervisor's reference case calls it unrealistic.

## Context and Problem Statement

Some generated variants sound right but nobody writes them, e.g. *Филипб*, *Wójciig*, *Huijggens*. We need a signal for "people really write this".

## Considered Options

* **No realism signal**: only the change probabilities.
* **Hard filter**: keep only spellings that exist in a corpus.
* **Bonus**: add +2 to the log score if the variant exists in names-dataset (about 1.7M first and last name spellings by real people, typos included) or among the entries of the same language.
* **Real misspelling corpora** (Birkbeck for English, the GitHub Typo Corpus with 350k edits in 15+ languages), used to evaluate.

## Decision Outcome

We chose the **bonus**. A check on prototype variants:

* found in names-dataset: Jakson, Wujcik, Jovanni, Gonsalves, Rousso, Filipp, Phillip;
* not found: Wójciig, Huijggens, Филипб, Jacsan, Philyp.

A hard filter would also remove *Fillipp*, the supervisor's own example, which is not in names-dataset. The columns `attested_name` and `attested_entry` are stored, so a later step can still filter.

### Consequences

* Good: realistic variants rise to the top, and invented ones remain available.
* Bad: attestation works for names, much less for common words. Words fall back to the probability score alone.
* Open: the typo corpora are not yet used. They are a good candidate for evaluating the realism of word variants.

## More Information

* GitHub Typo Corpus: Hagiwara & Mita (2020), LREC.
* Birkbeck spelling error corpus (Mitton), Oxford Text Archive.
