import shutil

import pytest

from src import db, ipa


class FakePhonemizer:
    """Counts backend creations and phonemized texts."""

    def __init__(self):
        self.backends = 0
        self.seen: list[str] = []

    def factory(self, lang):
        self.backends += 1

        def phonemize(texts):
            self.seen += texts
            return ["" if t == "???" else f"/{t.lower()}/" for t in texts]

        return phonemize


def rec(text, cat="word", lang="en"):
    return {"text": text, "lang": lang, "category": cat, "origin_country": None,
            "frequency": 1.0, "source": "test"}


@pytest.fixture
def conn():
    return db.connect(":memory:")


def test_fill_and_cache(conn):
    db.upsert_entries(conn, [rec("Paris", "city"), rec("Paris", "first_name"), rec("Rome", "city")])
    fake = FakePhonemizer()
    stats = ipa.fill_ipa(conn, "en", fake.factory, batch_size=1)
    # identical (text, lang) phonemized once, even across categories
    assert sorted(fake.seen) == ["Paris", "Rome"]
    assert fake.backends == 1  # one backend per language, not per batch
    assert stats["phonemized"] == 2
    assert set(conn.execute("SELECT ipa FROM entries")) == {("/paris/",), ("/rome/",)}

    # second run: nothing recomputed, no backend created
    fake2 = FakePhonemizer()
    ipa.fill_ipa(conn, "en", fake2.factory)
    assert fake2.seen == [] and fake2.backends == 0


def test_new_rows_reuse_cache(conn):
    db.upsert_entries(conn, [rec("Paris", "city")])
    ipa.fill_ipa(conn, "en", FakePhonemizer().factory)
    db.upsert_entries(conn, [rec("Paris", "word"), rec("Lyon", "city")])  # later run adds rows
    fake = FakePhonemizer()
    stats = ipa.fill_ipa(conn, "en", fake.factory)
    assert fake.seen == ["Lyon"] and stats["reused"] == 1


def test_languages_are_separate(conn):
    db.upsert_entries(conn, [rec("Paris", lang="en"), rec("Paris", lang="fr")])
    fake = FakePhonemizer()
    ipa.fill_ipa(conn, "en", fake.factory)
    ipa.fill_ipa(conn, "fr", fake.factory)
    assert fake.seen == ["Paris", "Paris"] and fake.backends == 2


def test_empty_output_is_stored_and_not_retried(conn):
    db.upsert_entries(conn, [rec("???")])
    ipa.fill_ipa(conn, "en", FakePhonemizer().factory)
    assert conn.execute("SELECT ipa FROM entries").fetchone() == ("",)
    fake = FakePhonemizer()
    ipa.fill_ipa(conn, "en", fake.factory)
    assert fake.seen == []


def test_resume_after_crash(conn):
    db.upsert_entries(conn, [rec(t) for t in ["aa", "bb", "cc", "dd"]])

    def crashing_factory(lang):
        calls = {"n": 0}

        def phonemize(texts):
            calls["n"] += 1
            if calls["n"] == 2:
                raise KeyboardInterrupt  # simulate crash in 2nd batch
            return [f"/{t}/" for t in texts]

        return phonemize

    with pytest.raises(KeyboardInterrupt):
        ipa.fill_ipa(conn, "en", crashing_factory, batch_size=2)
    assert conn.execute("SELECT COUNT(*) FROM entries WHERE ipa IS NOT NULL").fetchone()[0] == 2
    fake = FakePhonemizer()
    ipa.fill_ipa(conn, "en", fake.factory, batch_size=2)
    assert fake.seen == ["cc", "dd"]


@pytest.mark.skipif(shutil.which("espeak-ng") is None, reason="espeak-ng not installed")
def test_real_espeak():
    ph = ipa.make_espeak_phonemizer("en")
    out = ph(["Philip", "Phillip", "hello world"])
    assert out[0] == out[1] and out[0]          # spelling variants -> same IPA
    assert " " in out[2]                         # word separator kept
    assert "ˈ" not in "".join(out)               # with_stress=False
    de = ipa.make_espeak_phonemizer("de")(["Müller"])
    assert de[0] and "(" not in de[0]            # no language-switch flags


def test_report_homophones_and_loose():
    from src import report
    conn = db.connect(":memory:")
    db.upsert_entries(conn, [rec("Steven", "first_name"), rec("Stephen", "first_name"),
                             rec("Stephen", "last_name"), rec("steven", "word")])
    conn.execute("UPDATE entries SET ipa = 'stiːvən', frequency_norm = 1.0")
    rows = report.homophones(conn, "en")
    assert [(r[0], r[1]) for r in rows] == [("Stephen", "Steven"), ("Stephen", "steven")]
    assert report.homophone_count(conn, "en") == 2
    assert report.loose("d͡ʒʌst") == report.loose("dʒʌst") == "dʒʌst"
    assert report.loose("laɪ̯k") == "laɪk" and report.loose("fɔːɹ") == "fɔɹ"
