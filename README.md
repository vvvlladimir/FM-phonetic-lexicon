# FM phonetic lexicon

This builds a multilingual SQLite knowledge base of person names, cities, countries and common words. Each entry has its origin country, a frequency, and an IPA transcription from eSpeak NG. It is step 1 of the phonetic-mistake generation project (Universität Augsburg, Data Engineering chair).

Languages: en, de, fr, es, it, pt, nl, ru, pl, tr. The sources and their licenses are listed in [SOURCES.md](SOURCES.md).

## Setup

You need Python 3.11+ and eSpeak NG.

```bash
brew install espeak-ng            # macOS (Debian/Ubuntu: apt install espeak-ng)
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

On macOS the Homebrew library is found automatically. If it is installed somewhere else, set `PHONEMIZER_ESPEAK_LIBRARY=/path/to/libespeak-ng.dylib`.

## Run

```bash
python -m src.build_db --langs en                 # one language
python -m src.build_db                            # all 10 languages
python -m src.build_db --wikipron --report-path data/report.txt
python -m src.build_db --langs de --top-n 1000    # smaller top-N for names and words
python -m src.build_db --skip-ingest              # only fill missing IPA + print report
python -m pytest -q
```

Useful options:

- `--db-path`: default `data/lexicon.db`.
- `--sources names geonames wordfreq`: run only some of the sources.
- `--top-n-first`, `--top-n-last`, `--top-n-words`: per-source limits. The defaults are 5000, 5000 and 20000, set in `src/config.py`.

Downloads go into `data/raw/`. A file that is already there is not downloaded again. If a download fails, the script stops and prints the URL and the path where you should put the file manually.

A full run of all 10 languages takes about a minute after the downloads. Most of that time is spent streaming `alternateNamesV2` and loading names-dataset, which needs about 3 GB of RAM.

### Re-runs and resuming

- Entries are upserted on `UNIQUE(text, lang, category)`, so re-running never creates duplicates.
- IPA is only computed for rows where `ipa IS NULL`. It is computed in batches of 5000, with a commit after each batch, so a crash loses at most one batch.
- If the same `(text, lang)` already has IPA in another category, that IPA is copied instead of computed again.
- `ipa = ''` means eSpeak returned nothing. Those rows are listed in the report and are not retried.
- Rows are never deleted. If you lower `--top-n`, the old rows stay. Delete the DB to start clean.

## What goes into `entries`

| category | source | lang | origin_country | frequency |
|---|---|---|---|---|
| first_name / last_name | names-dataset | from `COUNTRY_TO_LANG` | country of the rank list | per-country rank, lower = more frequent |
| city | GeoNames cities15000 (class P) | main name: country's language; alternate names: their GeoNames language tag | city's country | population |
| country | GeoNames countryInfo + alternate names | main (English) name: `en`; alternate names: their language tag | the country itself | population |
| word | wordfreq `top_n_list` | the language | NULL | Zipf frequency |

`frequency_norm` scales frequency to 0..1 within each `(lang, category)`, where 1 is the most frequent:

- ranks: `1 - (rank - min) / (max - min)`
- population: the same min-max scaling on `log1p(population)`
- Zipf: plain min-max scaling

### Processing rules

- Normalization: Unicode NFC. Typographic apostrophes and hyphens become ASCII. Whitespace is trimmed and collapsed.
- Filtering:
  - Drop anything with a digit or shorter than 2 characters.
  - Words must be letters only.
  - Names and places may also contain a space, `-` and `'`.
- Script filter: `ru` entries must be Cyrillic, and all other languages must be Latin script.
  - eSpeak's `ru` voice would otherwise read Latin "Moscow" with the English voice. Because of this filter, the Latin-script Russian names in names-dataset (about a third of them) and the Latin GeoNames main names of Russian cities are dropped. The Cyrillic alternate names cover the cities.
- Deduplication on `(text, lang, category)` keeps the most frequent record. For example, "John" from both US and GB keeps the better rank and its country.
- GeoNames alternate names marked historic or colloquial are skipped. Cities come from the whole world (about 34k). A city's main name is only used if its country is in `COUNTRY_TO_LANG`, while alternate names in our 10 languages are used for all cities. That way the DB has e.g. "Munich" (en), "München" (de) and "Monaco di Baviera" (it).
- IPA comes from phonemizer with `EspeakBackend`, with one backend per language and batched calls. Settings: `preserve_punctuation=False`, `with_stress=False`, `language_switch="remove-flags"`. Phones are not separated, and words are separated by a space.

### `reference_pron` (optional, `--wikipron`)

This table holds WikiPron pronunciations: `word, lang, ipa, ipa_compact`. `ipa_compact` is the IPA with spaces, stress and syllable marks removed. The report compares eSpeak with WikiPron in two ways:

- **exact**: the strings must be equal
- **loose**: length marks and combining diacritics are ignored

Low agreement is expected because the two use different conventions: broad vs. narrow transcription, eSpeak's British-leaning vowels in en-us, and tie bars. The table is a sanity check, not ground truth.

## Changing the configuration

To add a country, add it to `COUNTRY_TO_LANG` in `src/config.py`. To add a language, also add its eSpeak voice to `ESPEAK_VOICES`, its script to `LANG_SCRIPT`, and optionally a file to `WIKIPRON_FILES`.

## Example query (homophones)

```sql
SELECT a.text, b.text, a.ipa FROM entries a
JOIN entries b ON a.lang = b.lang AND a.ipa = b.ipa AND a.id < b.id
WHERE a.lang = 'de' AND a.category = 'first_name' AND b.category = 'first_name'
  AND a.text <> b.text LIMIT 20;
```
