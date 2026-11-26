---
status: accepted
date: 2026-11-23
decision-makers: project author
---

# Score plausibility by category and frequency: names vary, known words do not

Supersedes ADR-0009. Refined by ADR-0013: a variant is known as `name`, `word` or neither, and a name heard as ordinary words gets its own prior of 0.5.

## Context and Problem Statement

The supervisor's task asks: "Wie bewerten wir Werte die gleich klingen aber dennoch falsch sind: Philip vs. Fillipp (realistisch) oder Pferd vs. Fert (unrealistisch)?" The hint given is: "Häufigkeit sowie bei Namen sind Werte eher plausibel".

The previous ranking (ADR-0009) added a bonus whenever a variant existed in names-dataset. Because "Fert" exists there as a surname, *Pferd → Fert* scored −0.50, higher than *Philip → Fillip* at −0.17. That is the opposite of the expected answer.

The TTS–STT pipeline (Hak, 2026) names the same gap in its section 8.6, "Missing Semantic Knowledge": it ranks candidates only by acoustic similarity.

## Decision Drivers

* Reproduce the two reference judgements: Philip→Fillipp is realistic, Pferd→Fert is unrealistic.
* Use the frequency information that is already in the DB.
* Be explainable: one formula with a few named constants.

## Considered Options

* Keep ADR-0009: a log-probability score plus an attestation bonus. This ranks Fert too high.
* A learned classifier. There is no labelled data, and its decisions could not be explained.
* **A product of three explicit factors**, with the attestation check depending on the category.

## Decision Outcome

We chose the **product of three factors**. Each factor lies in [0, 1] (`src/plausibility.py`):

```
plausibility = prior(kind, variant known?, frequency of original)
             × typicality   (only if the spelling is unknown)
             × similarity   (1 for same sound, PanPhon otherwise)
```

* **kind**: `name` if the original is used as a first name, last name, city or country, otherwise `word`.
* **variant known**, decided per kind:
  * names: the spelling exists in names-dataset or among the name or place entries;
  * words: the spelling is in the word list of that language, or its wordfreq Zipf value is ≥ 3.0.

  "Fert" is a surname but not a German word, so it does **not** count as known for *Pferd*.
* **prior**:

  | case | prior |
  |---|---|
  | name, known spelling (Phillip) | 1.0 |
  | name, unknown spelling (Fillipp) | 0.6 |
  | word misheard as another real word (Pferd→fährt) | 0.7 |
  | word, non-word misspelling (Pferd→Fert) | 0.02–0.10, lower for more frequent words |

* **typicality**: the geometric mean of P(letters | sound) over the changed letter groups. It is computed by `variants.explain_variant`, a DP that works for any string, including STT outputs.
  * Using the mean means several typical changes are not punished more than one unusual change.
  * Letters seen for the sound only at another position get half that probability. For example, English never has a final "pp".
  * Extra silent letters are allowed (the second "p").
  * A known spelling gets typicality 1, because it is simply written as that name or word.

Results with the full DB:

| original → variant | expected | plausibility |
|---|---|---|
| Philip → Phillip | realistic | 1.00 |
| Stephen → Steven | realistic | 1.00 |
| Meyer → Meier | realistic | 1.00 |
| Philip → Fillipp | realistic | ≈ 0.08 |
| Pferd → fährt | real-word mishearing | ≈ 0.57 |
| Pferd → Fert | unrealistic | ≈ 0.02 |
| house → hause | unrealistic | ≈ 0.00 |

### Consequences

* Good: both reference cases come out in the expected order. Fillipp is about 4× more plausible than Fert. Averaged over all stored variants, name variants score 3–6× higher than word variants (en: 0.33 vs. 0.05).
* Good: the same function can score candidates produced by the TTS–STT pipeline, not only our own variants.
* Bad: the constants (0.6, 0.7, 0.02–0.10, Zipf 3.0) are set by hand to match the two reference cases and common sense. They are not fitted to data. When labelled pipeline output or survey ratings exist, they should be fitted.
* Bad: the absolute value of an unknown name spelling is low (Fillipp ≈ 0.08). The scale is meaningful for *ranking*, not as a probability.
* The `variants` table changed: `attested_name` and `attested_entry` were replaced by `kind`, `known_as`, `logp`, `n_changes` and `plausibility`. `db.connect` drops an old-layout `variants` table automatically, since it is derived data.

### Confirmation

* `tests/test_plausibility.py` encodes the reference cases and the category-aware known-spelling check.
* The step-2 report prints a "reference examples" table per language, along with the mean plausibility for names and for words.

## More Information

* Hak (2026), *Implementing Phonetic Mistakes with a TTS-STT-Pipeline*, project module, Data Engineering chair, section 8.6.
