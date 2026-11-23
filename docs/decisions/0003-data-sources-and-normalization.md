---
status: accepted
date: 2026-11-23
decision-makers: project author
---

# Data sources, scope and normalization rules

## Context and Problem Statement

We need names, places and common words with an origin country and a frequency for 10 languages. The sources differ in script, quality and licensing, and their strings need cleaning before IPA makes sense.

## Considered Options and Decision Outcome

| Topic | Decision | Rejected alternative and reason |
|---|---|---|
| Person names | `names-dataset` (MIT): top 5000 first and last names per country, using the dataset's per-country rank (both genders) | Official name statistics exist only for some countries and use different formats. The Facebook-leak origin is documented in SOURCES.md. |
| Places | GeoNames `cities15000` (feature class P) + `alternateNamesV2` + `countryInfo` (CC BY 4.0), all ~34k cities worldwide | Restricting to our 10 countries would lose e.g. "Munich" (en) or "Monaco di Baviera" (it). |
| City name language | Main name → language of the city's country, only if that country is mapped. Alternate names → their GeoNames language tag. Historic and colloquial names are skipped. | Using the main name for every country would give it a language nobody pronounces it in. |
| Words | `wordfreq` top 20,000 per language, Zipf frequency; no digits, punctuation or length < 2 | — |
| Country → language | Config dict `COUNTRY_TO_LANG` (US, GB→en, DE, AT→de, …) | — |
| Normalization | NFC; typographic apostrophes and hyphens → ASCII; whitespace collapsed; dedupe on (text, lang, category), keeping the most frequent record | Without the apostrophe mapping, "People’s" and "People's" were two entries. |
| Script filter | `ru` must be Cyrillic, all other languages Latin | Latin "Moscow" tagged `ru` is read by eSpeak's *English* voice after a language switch. The filter drops about a third of the RU names in names-dataset, which are Latin transliterations. |
| `frequency_norm` | Min-max to 0..1 per (lang, category). Ranks are inverted; population is log-scaled. | One global scale is not meaningful across ranks, populations and Zipf values. |

### Consequences

* Good: within a language, frequencies are comparable and the entries are pronounceable by the matching voice.
* Bad: languages are not balanced. Cities range from 4.3k (tr) to 18.4k (ru), and names from 10k to 17k because some languages are mapped from two countries. Analyses that pool languages must sample or weight them.
* Bad: names-dataset ranks reflect Facebook users, not official statistics. For example, "Jose" is the #1 male first name for the US.

## More Information

See [SOURCES.md](../../SOURCES.md) for licenses and citations.
