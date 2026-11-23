"""First and last names from the `names-dataset` package (philipperemy/name-dataset).

Data ships inside the pip package (no download). Origin: a 2021 Facebook data
leak, see SOURCES.md. `rank` is the per-country rank of the name in that data.
"""
from __future__ import annotations

import logging
from collections import defaultdict

from . import config
from .normalize import clean, dedupe

log = logging.getLogger(__name__)
SOURCE = "names-dataset"


def _top_by_country(table: dict, countries: set[str], top_n: int, lang_of: dict,
                    category: str) -> dict[str, list[tuple[int, str]]]:
    """One pass over the name table -> {country: [(rank, cleaned_name), ...]} top N."""
    per_country: dict[str, list[tuple[int, str]]] = defaultdict(list)
    for name, info in table.items():
        for country, rank in info.get("rank", {}).items():
            if country in countries:
                text = clean(name, lang_of[country], category)
                if text:
                    per_country[country].append((rank, text))
    return {c: sorted(v)[:top_n] for c, v in per_country.items()}


def load(langs: list[str], top_n_first: int, top_n_last: int) -> list[dict]:
    from names_dataset import NameDataset  # heavy: ~3 GB RAM, ~10 s

    countries = {c for c, l in config.COUNTRY_TO_LANG.items() if l in langs}
    lang_of = {c: config.COUNTRY_TO_LANG[c] for c in countries}
    log.info("[names] loading names-dataset for countries %s", sorted(countries))
    nd = NameDataset()

    records: list[dict] = []
    for category, table, n in (
        ("first_name", nd.first_names, top_n_first),
        ("last_name", nd.last_names, top_n_last),
    ):
        top = _top_by_country(table, countries, n, lang_of, category)
        for country in sorted(countries):
            rows = top.get(country, [])
            if not rows:
                log.warning("[names] no %s data for country %s", category, country)
            log.info("[names] %s %s: %d", category, country, len(rows))
            records += [
                {"text": t, "lang": lang_of[country], "category": category,
                 "origin_country": country, "frequency": float(rank), "source": SOURCE}
                for rank, t in rows
            ]
    del nd
    # same name in e.g. US and GB -> keep the better (lower) rank
    return dedupe(records, higher_is_better=False)
