"""Central configuration: languages, mappings, limits and paths."""
from __future__ import annotations

import os
from pathlib import Path

# --- Languages -------------------------------------------------------------

# Our language code -> eSpeak NG voice used by phonemizer.
ESPEAK_VOICES: dict[str, str] = {
    "en": "en-us",
    "de": "de",
    "fr": "fr-fr",
    "es": "es",
    "it": "it",
    "pt": "pt",
    "nl": "nl",
    "ru": "ru",
    "pl": "pl",
    "tr": "tr",
}
LANGS: list[str] = list(ESPEAK_VOICES)

# Country (ISO 3166-1 alpha-2) -> language its names/places are pronounced in.
# Extend this dict to add countries; the language must be in ESPEAK_VOICES.
COUNTRY_TO_LANG: dict[str, str] = {
    "US": "en", "GB": "en",
    "DE": "de", "AT": "de",
    "FR": "fr",
    "ES": "es", "MX": "es",
    "IT": "it",
    "PT": "pt", "BR": "pt",
    "NL": "nl",
    "RU": "ru",
    "PL": "pl",
    "TR": "tr",
}

# Script each language is expected to be written in. Entries in another script
# are dropped (e.g. Latin "Moscow" tagged as Russian would be read by the
# English voice after eSpeak's language switch, which is not what we want).
LANG_SCRIPT: dict[str, str] = {lang: "LATIN" for lang in LANGS}
LANG_SCRIPT["ru"] = "CYRILLIC"


def countries_for_lang(lang: str) -> list[str]:
    """All countries mapped to the given language."""
    return [c for c, l in COUNTRY_TO_LANG.items() if l == lang]


def lang_for_country(country: str) -> str | None:
    return COUNTRY_TO_LANG.get(country.upper())


# --- Limits ----------------------------------------------------------------

TOP_N_FIRST_NAMES = 5000   # per country
TOP_N_LAST_NAMES = 5000    # per country
TOP_N_WORDS = 20000        # per language
IPA_BATCH_SIZE = 5000      # texts per phonemizer call (one commit per batch)

# --- Categories / frequency semantics -------------------------------------

CATEGORIES = ["first_name", "last_name", "city", "country", "word"]

# How the raw `frequency` value should be read when normalizing to 0..1
# (1 = most frequent).  "rank": lower is better; "log": higher is better,
# log-scaled (population); "linear": higher is better (zipf is already log).
FREQ_SCALE: dict[str, str] = {
    "first_name": "rank",
    "last_name": "rank",
    "city": "log",
    "country": "log",
    "word": "linear",
}

# --- Paths -----------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
GEONAMES_DIR = RAW_DIR / "geonames"
WIKIPRON_DIR = RAW_DIR / "wikipron"
DEFAULT_DB_PATH = DATA_DIR / "lexicon.db"

GEONAMES_BASE_URL = "https://download.geonames.org/export/dump/"
GEONAMES_FILES = ["cities15000.zip", "alternateNamesV2.zip", "countryInfo.txt"]

WIKIPRON_BASE_URL = (
    "https://raw.githubusercontent.com/CUNY-CL/wikipron/master/data/scrape/tsv/"
)
# Closest WikiPron dialect to the eSpeak voice we use.
WIKIPRON_FILES: dict[str, str] = {
    "en": "eng_latn_us_broad.tsv",
    "de": "deu_latn_broad.tsv",
    "fr": "fra_latn_broad.tsv",
    "es": "spa_latn_ca_broad.tsv",     # Castilian, matches eSpeak "es"
    "it": "ita_latn_broad.tsv",
    "pt": "por_latn_po_broad.tsv",     # European, matches eSpeak "pt"
    "nl": "nld_latn_broad.tsv",
    "ru": "rus_cyrl_narrow.tsv",       # no broad file exists for Russian
    "pl": "pol_latn_broad.tsv",
    "tr": "tur_latn_broad.tsv",
}


def espeak_library() -> str | None:
    """Path to libespeak-ng for phonemizer (needed on macOS/Homebrew)."""
    env = os.environ.get("PHONEMIZER_ESPEAK_LIBRARY")
    if env:
        return env
    for p in (
        "/opt/homebrew/lib/libespeak-ng.dylib",
        "/usr/local/lib/libespeak-ng.dylib",
    ):
        if Path(p).exists():
            return p
    return None  # let phonemizer find it (works on most Linux installs)


# --- Step 2: spelling variants (src/build_variants.py) -----------------------

VARIANT_TOP_N = 2000          # originals per (lang, category), single-token entries only
VARIANT_CANDIDATES = 40       # candidates generated per original (before checking)
VARIANT_KEEP = 20             # variants stored per original
VARIANT_MAX_CHANGES = 3       # letter groups changed per variant
NEAR_THRESHOLD = 0.80         # PanPhon similarity for a "near" (sounds similar) variant
NEIGHBOUR_MAX_DIST = 0.3      # PanPhon distance for similar sounds (p~b 0.04, m~n 0.13)

# Plausibility (src/plausibility.py, ADR-0012): prior x typicality x similarity
PRIOR_NAME_KNOWN = 1.0        # name variant that is itself a real name (Philip -> Phillip)
PRIOR_NAME_UNKNOWN = 0.6      # name variant not seen anywhere (Philip -> Fillipp)
PRIOR_WORD_KNOWN = 0.7        # word heard as another real word (Pferd -> fährt)
PRIOR_WORD_UNKNOWN_MAX = 0.10 # non-word misspelling of the rarest word in the list
PRIOR_WORD_UNKNOWN_MIN = 0.02 # ... of the most frequent word (Pferd -> Fert)
WORD_KNOWN_ZIPF = 3.0         # wordfreq Zipf >= this counts as a real word
