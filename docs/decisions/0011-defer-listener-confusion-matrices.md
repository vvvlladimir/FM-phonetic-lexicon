---
status: proposed
date: 2026-11-23
decision-makers: project author
---

# (Deferred) Weight sound changes by human listener confusion data

## Context and Problem Statement

The project's pipeline simulates mishearing (TTS→noise→STT). PanPhon (ADR-0007) measures articulatory similarity, but what listeners actually confuse in noise is an empirical question. For example, voicing confusions are asymmetric (Phatak, Lovitt & Allen, 2008).

## Considered Options

* **Do nothing**: rely on PanPhon.
* **Use published confusion matrices**:
  * Miller & Nicely (1955): 16 English consonants in noise;
  * Phatak & Allen (2007);
  * Weber & Cutler (2003): all American English phonemes, with native vs. non-native listeners.

  Their probabilities would replace the fixed −2 `near` penalty.
* **Learn confusions from the project's own TTS→noise→STT pipeline**: count which phonemes turn into which.
* **Bi-Phone** (Gupta et al., ACL 2023): mine L1→L2 phoneme confusions, e.g. how Germans mishear English.

## Decision Outcome

**Deferred.** The published matrices exist only as tables in papers, mostly for English. Typing them in is manual work that needs care, and we do not invent data. The most promising option is learning from the project's own pipeline output, because it matches the real use case and covers all 10 languages. It needs the pipeline's output data.

### Consequences

* For now, `near` variants are ranked by PanPhon similarity and spelling probability only.
* The code is prepared: replacing `NEAR_PENALTY` in `src/variants.py` with a per-sound-pair log-probability would be enough.

## More Information

* Miller & Nicely (1955), *An analysis of perceptual confusions among some English consonants*, JASA: <https://jontalle.web.engr.illinois.edu/uploads/537.F18/Papers/MillerNicely55.pdf>
* Phatak & Allen (2007), *Consonant and vowel confusions in speech-weighted noise*: <https://jontalle.web.engr.illinois.edu/Public/Allen-pdf/PhatakAllen07.pdf>
* Weber & Cutler, American English phoneme confusions: <https://pure.mpg.de/pubman/item/item_57575_2/component/file_57576/weber_2003_consonant.pdf>
* Gupta et al. (2023), *Bi-Phone: Modeling Inter Language Phonetic Influences in Text*, ACL.
