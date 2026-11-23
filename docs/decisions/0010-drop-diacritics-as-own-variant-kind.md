---
status: accepted
date: 2026-11-23
decision-makers: project author
---

# Treat dropped diacritics as a separate variant kind (all languages, central for Turkish)

## Context and Problem Statement

Turkish spelling is almost 1:1 with sound. In the prototype only 7% of Turkish originals got any same-sound variant, which is a property of the language and not a bug. The typical Turkish mistake is losing diacritics instead: ş→s, ı→i, ğ→g, ç→c. This happens with ASCII keyboards, and it is so common that "deasciifier" tools exist to restore them. The same mistake occurs in other languages: Vázquez→Vazquez, Łódź→Lodz, Müller→Muller.

## Considered Options

* Ignore it: Turkish stays nearly empty.
* A Turkish-only rule list.
* **A generic `deaccent` kind**: drop all diacritics, or drop one at a time, for every Latin-script language. There are special cases for letters without a Unicode decomposition: ı→i, ł→l, ß→ss, ø→o. Cyrillic letters are not touched (й stays й).

## Decision Outcome

We chose the **generic `deaccent` kind**. Variants are verified like all others:

* sometimes the sound stays the same: Spanish *Vázquez→Vazquez* is a homophone in eSpeak;
* sometimes it changes slightly: Turkish *Şahin→Sahin* becomes a `near` variant.

### Consequences

* Good: covers the main real-world Turkish mistake and similar mistakes in de, pl, es, pt, fr.
* Bad: these are typing or keyboard mistakes rather than mistakes made by hearing. The `kinds` column lets later steps include or exclude them.

## More Information

Turkish deasciifiers: <https://github.com/meacer/deasciifier>, <https://github.com/StarlangSoftware/TurkishDeasciifier>.
