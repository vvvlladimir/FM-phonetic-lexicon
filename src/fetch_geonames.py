"""Cities (feature class P, population > 15000) and countries from GeoNames (CC BY 4.0).

Files (downloaded into data/raw/geonames/):
  cities15000.zip, alternateNamesV2.zip, countryInfo.txt

Rules:
  * main city name -> language of the city's country (COUNTRY_TO_LANG); skipped
    if the country is not mapped (we don't know how it is pronounced)
  * country main name (countryInfo, English) -> "en"
  * alternate names whose isolanguage is one of our languages -> that language,
    excluding historic and colloquial names
  * frequency = population; origin_country = the city's / the country's ISO code
"""
from __future__ import annotations

import io
import logging
import zipfile

from tqdm import tqdm

from . import config
from .download import download
from .normalize import clean, dedupe

log = logging.getLogger(__name__)
SOURCE = "geonames"


def fetch() -> None:
    for name in config.GEONAMES_FILES:
        download(config.GEONAMES_BASE_URL + name, config.GEONAMES_DIR / name)


def _read_cities() -> dict[int, tuple[str, str, int]]:
    """geonameid -> (name, country_code, population), feature class P only."""
    cities = {}
    with zipfile.ZipFile(config.GEONAMES_DIR / "cities15000.zip") as z:
        with z.open("cities15000.txt") as f:
            for line in io.TextIOWrapper(f, encoding="utf-8"):
                c = line.rstrip("\n").split("\t")
                if c[6] != "P":
                    continue
                cities[int(c[0])] = (c[1], c[8], int(c[14] or 0))
    return cities


def _read_countries() -> dict[int, tuple[str, str, int]]:
    """geonameid -> (English name, ISO alpha-2, population)."""
    countries = {}
    with open(config.GEONAMES_DIR / "countryInfo.txt", encoding="utf-8") as f:
        for line in f:
            if line.startswith("#") or not line.strip():
                continue
            c = line.rstrip("\n").split("\t")
            if c[16]:
                countries[int(c[16])] = (c[4], c[0], int(c[7] or 0))
    return countries


def _iter_alternate_names(langs: set[str]):
    """Yield (geonameid, lang, name) from alternateNamesV2, filtered to our languages."""
    with zipfile.ZipFile(config.GEONAMES_DIR / "alternateNamesV2.zip") as z:
        with z.open("alternateNamesV2.txt") as f:
            for line in tqdm(io.TextIOWrapper(f, encoding="utf-8"),
                             desc="alternateNamesV2", unit=" lines", miniters=500000):
                c = line.rstrip("\n").split("\t")
                if c[2] not in langs:
                    continue
                is_colloquial, is_historic = c[6] == "1", c[7] == "1"
                if is_colloquial or is_historic:
                    continue
                yield int(c[1]), c[2], c[3]


def load(langs: list[str]) -> list[dict]:
    fetch()
    lang_set = set(langs)
    cities = _read_cities()
    countries = _read_countries()
    log.info("[geonames] %d cities (class P), %d countries in source files",
             len(cities), len(countries))

    records: list[dict] = []

    def add(raw: str, lang: str, category: str, country: str, pop: int) -> None:
        text = clean(raw, lang, category)
        if text:
            records.append({"text": text, "lang": lang, "category": category,
                            "origin_country": country, "frequency": float(pop),
                            "source": SOURCE})

    for name, cc, pop in cities.values():
        lang = config.lang_for_country(cc)
        if lang in lang_set:
            add(name, lang, "city", cc, pop)
    if "en" in lang_set:
        for name, cc, pop in countries.values():
            add(name, "en", "country", cc, pop)

    for gid, lang, name in _iter_alternate_names(lang_set):
        if gid in cities:
            _, cc, pop = cities[gid]
            add(name, lang, "city", cc, pop)
        elif gid in countries:
            _, cc, pop = countries[gid]
            add(name, lang, "country", cc, pop)

    # e.g. several "Springfield"s -> keep the most populous one
    out = dedupe(records, higher_is_better=True)
    for lang in langs:
        for cat in ("city", "country"):
            n = sum(1 for r in out if r["lang"] == lang and r["category"] == cat)
            log.info("[geonames] %s %s: %d", lang, cat, n)
    return out
