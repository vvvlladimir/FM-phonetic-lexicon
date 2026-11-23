"""Build the phonetic lexicon DB.

    python -m src.build_db --langs en
    python -m src.build_db                       # all 10 languages
    python -m src.build_db --langs de fr --top-n 1000 --wikipron

Safe to re-run: entries are upserted (unique on text, lang, category) and IPA is
only computed for rows where it is still NULL.
"""
from __future__ import annotations

import argparse
import logging
import sys
import time

from . import config, db, fetch_geonames, fetch_names, fetch_wikipron, fetch_wordfreq, ipa, report
from .download import DownloadError

log = logging.getLogger("build_db")

SOURCES = ["names", "geonames", "wordfreq"]


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--langs", nargs="+", default=config.LANGS, choices=config.LANGS)
    ap.add_argument("--top-n", type=int, help="shorthand: sets all three top-N limits")
    ap.add_argument("--top-n-first", type=int, default=config.TOP_N_FIRST_NAMES)
    ap.add_argument("--top-n-last", type=int, default=config.TOP_N_LAST_NAMES)
    ap.add_argument("--top-n-words", type=int, default=config.TOP_N_WORDS)
    ap.add_argument("--db-path", default=str(config.DEFAULT_DB_PATH))
    ap.add_argument("--sources", nargs="+", default=SOURCES, choices=SOURCES)
    ap.add_argument("--skip-ingest", action="store_true", help="only (re)compute IPA + report")
    ap.add_argument("--wikipron", action="store_true", help="also import WikiPron reference_pron")
    ap.add_argument("--report-path", help="also write the report to this file")
    a = ap.parse_args(argv)
    if a.top_n:
        a.top_n_first = a.top_n_last = a.top_n_words = a.top_n
    return a


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        datefmt="%H:%M:%S")
    a = parse_args(argv)
    conn = db.connect(a.db_path)
    log.info("DB: %s | langs: %s", a.db_path, a.langs)
    t0 = time.time()

    try:
        if not a.skip_ingest:
            if "names" in a.sources:
                db.upsert_entries(conn, fetch_names.load(a.langs, a.top_n_first, a.top_n_last))
            if "geonames" in a.sources:
                db.upsert_entries(conn, fetch_geonames.load(a.langs))
            if "wordfreq" in a.sources:
                db.upsert_entries(conn, fetch_wordfreq.load(a.langs, a.top_n_words))
            db.update_frequency_norm(conn)
        if a.wikipron:
            fetch_wikipron.load_into(conn, a.langs)
    except DownloadError as e:
        log.error("%s", e)
        return 2

    for lang in a.langs:
        ipa.fill_ipa(conn, lang)

    text = report.print_report(conn, a.langs)
    if a.report_path:
        with open(a.report_path, "w", encoding="utf-8") as f:
            f.write(text + "\n")
    log.info("done in %.0f s", time.time() - t0)
    return 0


if __name__ == "__main__":
    sys.exit(main())
