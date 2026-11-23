# Data sources and licenses

Write these up in the report when you use the database.

| Source | Used for | License | Notes |
|---|---|---|---|
| [names-dataset](https://github.com/philipperemy/name-dataset) 3.3.1 (pip) | `first_name`, `last_name` | MIT (package, incl. data files), per the package metadata. | The package README says the names were "extracted from the Facebook massive dump (533M users)", i.e. the **2021 Facebook data leak**. You should think about the ethics and legality of this before you publish. Ranks reflect Facebook users, not official statistics. Some are clearly biased, e.g. "Jose" is the #1 male first name for the US. The package lists first names separately by gender; we use the per-country `rank` field, which covers both genders. |
| [GeoNames](https://www.geonames.org/) dump: `cities15000.zip`, `alternateNamesV2.zip`, `countryInfo.txt` | `city`, `country` | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) | Attribution: "Contains data from GeoNames (www.geonames.org), licensed under CC BY 4.0." Downloaded 2026-11-23 from https://download.geonames.org/export/dump/ |
| [wordfreq](https://github.com/rspeer/wordfreq) 3.1.1 (pip) | `word` | Code: Apache-2.0. Data: CC BY-SA 4.0 | Several corpora are aggregated (see the wordfreq README for the list). `frequency` is the Zipf value. |
| [WikiPron](https://github.com/CUNY-CL/wikipron) (`data/scrape/tsv`, master) | `reference_pron` only (cross-check) | Wiktionary content, CC BY-SA | Files: see `WIKIPRON_FILES` in `src/config.py`. Russian has only a *narrow* transcription. |
| [eSpeak NG](https://github.com/espeak-ng/espeak-ng) 1.52.0 via [phonemizer](https://github.com/bootphon/phonemizer) 3.6.0 | `ipa` column | GPL-3.0 (eSpeak NG), GPL-3.0 (phonemizer) | eSpeak generates the IPA with rules. It is not a human transcription. |

| [PanPhon](https://github.com/dmort27/panphon) 0.22.2 (pip) | `variants.similarity` and similar sounds | MIT | Articulatory feature vectors for IPA segments. |

## Citations

- Remy, P. (2021). *Name Dataset*. https://github.com/philipperemy/name-dataset
- Speer, R. *wordfreq*. https://github.com/rspeer/wordfreq (cite the version: 3.1.1)
- Lee, J. L., Ashby, L. F. E., Garza, M. E., et al. (2020). Massively multilingual pronunciation mining with WikiPron. *LREC 2020*.
- Mortensen, D. R., et al. (2016). PanPhon: A resource for mapping IPA segments to articulatory feature vectors. *COLING 2016*.
- Bhagat, R., & Hovy, E. (2007). Phonetic models for generating spelling variants. *IJCAI 2007*.
- Bernard, M., & Titeux, H. (2021). Phonemizer: Text to phones transcription for multiple languages in Python. *JOSS*, 6(68), 3958.
