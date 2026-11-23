import sqlite3

import pytest

from src import db


def rec(text, cat="word", freq=1.0, lang="en", country=None, source="wordfreq"):
    return {"text": text, "lang": lang, "category": cat, "origin_country": country,
            "frequency": freq, "source": source}


@pytest.fixture
def conn():
    return db.connect(":memory:")


def test_unique_text_lang_category(conn):
    conn.execute("INSERT INTO entries (text, lang, category, source) VALUES ('a', 'en', 'word', 'x')")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO entries (text, lang, category, source) VALUES ('a', 'en', 'word', 'y')")
    # same text in another category or language is fine
    conn.execute("INSERT INTO entries (text, lang, category, source) VALUES ('a', 'en', 'city', 'x')")
    conn.execute("INSERT INTO entries (text, lang, category, source) VALUES ('a', 'de', 'word', 'x')")


@pytest.mark.parametrize("col", ["text", "lang", "category", "source"])
def test_not_null(conn, col):
    vals = {"text": "'a'", "lang": "'en'", "category": "'word'", "source": "'x'"}
    vals[col] = "NULL"
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(f"INSERT INTO entries (text, lang, category, source) VALUES "
                     f"({vals['text']}, {vals['lang']}, {vals['category']}, {vals['source']})")


def test_upsert_idempotent_and_keeps_ipa(conn):
    db.upsert_entries(conn, [rec("hello", freq=5.0)])
    conn.execute("UPDATE entries SET ipa = 'həloʊ'")
    db.upsert_entries(conn, [rec("hello", freq=6.0)])  # re-run with new freq
    rows = conn.execute("SELECT text, frequency, ipa FROM entries").fetchall()
    assert rows == [("hello", 6.0, "həloʊ")]


def test_schema_indexes(conn):
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    assert {"idx_entries_ipa", "idx_entries_text", "idx_entries_cat"} <= names


def test_frequency_norm(conn):
    db.upsert_entries(conn, [
        rec("Anna", "first_name", 1, source="names-dataset"),
        rec("Bea", "first_name", 11, source="names-dataset"),
        rec("Bigcity", "city", 1_000_000, source="geonames"),
        rec("Smalltown", "city", 15_000, source="geonames"),
        rec("the", "word", 7.5),
        rec("cat", "word", 4.5),
    ])
    db.update_frequency_norm(conn)
    norm = dict(conn.execute("SELECT text, frequency_norm FROM entries"))
    assert norm["Anna"] == 1.0 and norm["Bea"] == 0.0        # rank: lower is better
    assert norm["Bigcity"] == 1.0 and norm["Smalltown"] == 0.0
    assert norm["the"] == 1.0 and norm["cat"] == 0.0
    assert all(0.0 <= v <= 1.0 for v in norm.values())
