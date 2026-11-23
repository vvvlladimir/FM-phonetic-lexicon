---
status: accepted
date: 2026-11-23
decision-makers: project author
---

# Russian: decide "same sound" with an unstressed-vowel rule instead of eSpeak's stress guess

## Context and Problem Statement

In Russian, unstressed «о/а» merge (akanye), and so do unstressed «е/и/я» (ikanye). *малоко* therefore sounds like *молоко* to a listener. eSpeak knows the stress of real words from its dictionary, but it guesses the stress of a new spelling such as *малоко*. It puts the stress on the wrong syllable, reduces the wrong vowels, and the exact IPA comparison fails. In the prototype, Russian had the lowest score: 18% of top-10 variants verified, against 50–78% for most languages.

## Considered Options

* **Mark stress in the text** (combining acute, *малоко́*). Tested: eSpeak honoured it in the middle of a word but not on the last vowel, so it is unreliable.
* **A stress model** (silero-stress, RUAccent/stressonnx) to stress the variant. This needs PyTorch or ONNX and still compares through eSpeak.
* **A rule**: compare consonants via eSpeak, and compare vowel *letters* directly. The stressed vowel must be identical. Unstressed о↔а and е↔и↔я may be swapped. The stressed position is taken from eSpeak's reading of the *original* word (`with_stress=True`), which comes from its dictionary.

## Decision Outcome

We chose the **rule** (`phonetic.ru_equivalent`). A Russian variant counts as `homophone` if its IPA is identical **or** the rule holds.

### Consequences

* Good: no new heavy dependency, and the rule encodes a well-known feature of Russian pronunciation.
* Bad: it relies on eSpeak's stress for the original. If eSpeak stresses a rare name wrongly, the rule allows the wrong vowel swaps.
* Bad: it covers only the two main reduction classes. Rarer effects, such as «е/э» after hard consonants, are not covered.
* If needed later, silero-stress (about 4M word forms) can replace eSpeak's stress for the original word without changing the rule.

### Confirmation

`tests/test_g2p.py::test_ru_unstressed_vowels`: молоко/малоко is accepted. Changing the stressed vowel, changing a vowel outside the classes, or changing a consonant is rejected.

## More Information

* silero-stress: <https://github.com/snakers4/silero-stress>
* RUAccent (COLING 2025): <https://aclanthology.org/2025.coling-main.444>
