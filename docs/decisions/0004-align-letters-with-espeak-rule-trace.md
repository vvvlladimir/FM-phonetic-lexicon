---
status: accepted
date: 2026-11-23
decision-makers: project author
---

# Align letters to sounds with eSpeak's own rule trace (`espeak-ng -X`), Viterbi as fallback

## Context and Problem Statement

To generate spelling mistakes such as *Philip → Fillipp*, we must know which letters produce which sound (ph→/f/, i→/ɪ/, …). Letters and sounds are not 1:1: "ph", "igh" and "sch" are single sounds, and "x" is two. Pronunciation dictionaries do not contain this alignment, so it has to be computed.

## Decision Drivers

* The alignment must agree with the IPA we already store, which comes from eSpeak (ADR-0002).
* It must work for all 10 languages without training data per language.
* Tools that are hard to build on macOS or Linux laptops should be avoided.

## Considered Options

* **eSpeak rule trace.** `espeak-ng -X` prints, for each position in the word, the spelling rule that won (e.g. `_) ph ( [f]`). We parse it and keep the highest-scoring rule per letter group.
* **m2m-aligner** (Jiampojamarn et al., 2007). It uses EM many-to-many alignment and was used for G2P and name transliteration. It is written in C++, and people report build problems on macOS.
* **Phonetisaurus.** Its EM alignment is followed by a WFST G2P model. It needs OpenFST.
* **A neural model** (e.g. PolyIPA, 2024). This is too heavy for an alignment-only task.

## Decision Outcome

We chose the **eSpeak rule trace**. For words eSpeak takes whole from its exception dictionary, there is no per-letter trace, e.g. "Stephen". For those we use a **Viterbi alignment** whose scores are learned from the words that were aligned by rules. It is a one-step version of m2m's EM.

Implementation details found while prototyping:

* Words are run in batches of 2000 clauses through one eSpeak process. If the output cannot be split 1:1 into words, the batch is halved and retried.
* Only rule lines after `Translate` count. The `Unpronouncable?` pre-pass is ignored.
* eSpeak re-translates stems (e.g. `aachen` and then `aach`). Further `Translate` blocks are used only while the letters covered so far are a proper prefix, as in compounds (`hand` + `schuh`).
* The final phoneme line can start with a digit (`3r'Est` for *arrest*), so rule lines are detected by their format, not by a leading digit.
* Language-switch flags `(en)` are removed from phoneme strings.

### Consequences

* Good: the alignment is exactly the one eSpeak used. Share of single-token texts aligned by rules:

  | en | de | fr | es | it | pt | nl | ru | pl | tr |
  |---|---|---|---|---|---|---|---|---|---|
  | 82% | 91% | 92% | 97% | 96% | 84% | 93% | 91% | 99% | 97% |

  The rest is aligned by Viterbi. Fewer than 1% of texts fail.
* Good: no extra dependencies, and fast: about 44k words per language in about 20 s.
* Bad: the trace format is not a documented API and may change between eSpeak versions. We pin 1.52 and keep parser tests (`tests/test_g2p.py`).
* Bad: dictionary words such as Stephen are aligned less reliably. Viterbi gives `p→v, h→∅`, which happens to work: *Steven* is found. For other words the split can be odd, for example `ephe→iːvə` before the per-letter penalty was added.

### Confirmation

The step-2 report prints the share of words aligned by rules and by Viterbi per language. Parser edge cases are covered by unit tests.

## More Information

* Jiampojamarn, Kondrak & Sherif (2007), *Applying Many-to-Many Alignments and HMMs to Letter-to-Phoneme Conversion*, NAACL.
* Novak, Minematsu & Hirose (2016), *Phonetisaurus*, Natural Language Engineering.
* The prototype results are kept in [../results/prototype_report.txt](../results/prototype_report.txt).
