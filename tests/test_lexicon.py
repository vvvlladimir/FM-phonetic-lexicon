"""On-demand API (src/lexicon.py) on a tiny hand-made DB with a fake phonemizer."""
import json

import pytest

from src import db
from src.lexicon import Lexicon

IPA = {"Philip": "fɪlɪp", "Fillipp": "fɪlɪp", "Phillip": "fɪlɪp", "Filling": "fɪlɪŋ",
       "pferd": "pfeːɾt", "Pferd": "pfeːɾt", "Fert": "fɛɾt", "fährt": "fɛːɾt"}


class FakePhonemizer:
    def __init__(self):
        self.calls: list[list[str]] = []

    def __call__(self, lang, with_stress=False):
        def phonemize(texts):
            self.calls.append(list(texts))
            return [IPA.get(t, "x") for t in texts]
        return phonemize


@pytest.fixture
def lex(tmp_path):
    path = tmp_path / "t.db"
    conn = db.connect(path)
    entries = [("Philip", "en", "first_name", 0.9, "fɪlɪp"), ("Phillip", "en", "first_name", 0.8, "fɪlɪp"),
               ("filling", "en", "word", 0.5, "fɪlɪŋ"),
               ("pferd", "de", "word", 0.25, "pfeːɾt"), ("fährt", "de", "word", 0.34, "fɛːɾt")]
    conn.executemany("INSERT INTO entries (text, lang, category, frequency, frequency_norm, source, ipa) "
                     "VALUES (?, ?, ?, 1.0, ?, 't', ?)", [(t, l, c, f, i) for t, l, c, f, i in entries])
    conn.executemany("INSERT INTO g2p_alignment VALUES (?, ?, 'rules', ?)", [
        ("Philip", "en", json.dumps([["ph", "f"], ["i", "I"], ["l", "l"], ["i", "I"], ["p", "p"]])),
        ("pferd", "de", json.dumps([["pf", "pF"], ["er", "e:r"], ["d", "t"]]))])
    rows = [("en", "f", "f", "B", "f", 90), ("en", "f", "f", "B", "ph", 10), ("en", "l", "l", "M", "l", 80),
            ("en", "l", "l", "M", "ll", 20), ("en", "p", "p", "E", "p", 100), ("en", "", "", "M", "p", 30),
            ("en", "I", "ɪ", "M", "i", 100),
            ("de", "pF", "pf", "B", "pf", 50), ("de", "f", "f", "B", "f", 100), ("de", "e:r", "eːɾ", "M", "er", 50),
            ("de", "t", "t", "E", "t", 60), ("de", "t", "t", "E", "d", 40)]
    conn.executemany("INSERT INTO sound_spelling VALUES (?, ?, ?, ?, ?, ?, 1.0)", rows)
    conn.executemany("INSERT INTO known_names VALUES (?)", [("fert",), ("filling",), ("phillip",)])
    conn.commit()
    fake = FakePhonemizer()
    lx = Lexicon(path, phonemizer_factory=fake)
    lx.fake = fake
    return lx


def test_reference_cases(lex):
    fillipp = lex.score("Philip", "Fillipp", "en")
    fert = lex.score("Pferd", "Fert", "de")
    assert fillipp.kind == "name" and fillipp.same_sound and fillipp.known_as is None
    assert fert.kind == "word" and fert.known_as is None      # surname, but not a German word
    assert fillipp.plausibility > 3 * fert.plausibility
    assert lex.score("Philip", "Phillip", "en").plausibility == 1.0
    assert lex.score("Pferd", "fährt", "de").known_as == "word"


def test_names_dataset_words_count_as_words(lex):
    assert lex.score("Philip", "Filling", "en").known_as == "word"


def test_ipa_cache_avoids_second_espeak_call(lex):
    lex.score_many("Philip", ["Fillipp", "Zzz"], "en")
    n = len(lex.fake.calls)
    assert n == 1 and set(lex.fake.calls[0]) == {"Fillipp", "Zzz"}   # Philip came from entries
    lex.score_many("Philip", ["Fillipp", "Zzz"], "en")
    assert len(lex.fake.calls) == n                                  # served from ipa_cache
    assert lex.conn.execute("SELECT COUNT(*) FROM ipa_cache").fetchone()[0] == 2


def test_rerank_drops_original_and_blends_own_score(lex):
    cands = [("Philip", 0.99), ("Fillipp", 0.98), ("Phillip", 0.90)]
    out = lex.rerank("Philip", cands, "en")
    assert [s.variant for s in out] == ["Phillip", "Fillipp"]
    only_own = lex.rerank("Philip", cands, "en", weight=0.0)
    assert [s.variant for s in only_own] == ["Fillipp", "Phillip"]
    assert out[0].extra == 0.90


def test_textclass_mapping(lex):
    assert lex.score("Pferd", "Fert", "de", textclass="NAME").kind == "name"
    assert lex.score("Philip", "Fillipp", "en", textclass="NATURAL_TEXT").kind == "word"


def test_unsupported_language(lex):
    with pytest.raises(ValueError):
        lex.score("a", "b", "xx")
