"""Plausibility: the supervisor's reference cases (Philip/Fillipp vs Pferd/Fert)."""
from src.g2p import Table
from src.plausibility import KnownSpellings, kind_of, plausibility, prior, typicality
from src.variants import explain_variant


def test_kind_of():
    assert kind_of({"first_name": 0.9, "word": 0.5}) == "name"
    assert kind_of({"word": 0.5}) == "word"


def test_typicality_is_per_change_mean():
    assert typicality(0.0, 0) == 1.0
    # three changes with p=0.5 each are as typical as one change with p=0.5
    assert abs(typicality(3 * -0.693, 3) - typicality(-0.693, 1)) < 1e-9


def test_priors_follow_supervisor_rule():
    assert prior("name", True, 0) > prior("name", False, 0) > prior("word", False, 0)
    assert prior("word", True, 0.9) > prior("word", False, 0.0)
    # the more frequent the word, the less plausible a non-word misspelling
    assert prior("word", False, 0.9) < prior("word", False, 0.1)


def test_reference_cases_ranked_correctly():
    # Philip -> Fillipp: name, unknown spelling, 3 typical changes, same sound
    philip = plausibility("name", False, 0.0, logp=3 * -1.0, n_changes=3, similarity=1.0)
    # Pferd -> Fert: frequent word, not a word, 2 changes, similar sound
    pferd = plausibility("word", False, 0.25, logp=-0.5, n_changes=2, similarity=0.8)
    # Pferd -> fährt: real word, misheard
    faehrt = plausibility("word", True, 0.25, logp=-6.0, n_changes=2, similarity=0.8)
    assert philip > 3 * pferd
    assert faehrt > pferd


def test_known_spellings_are_category_aware():
    k = KnownSpellings(names={"fert", "phillip"}, words={"de": {"pferd", "fährt"}})
    assert k.is_known("Phillip", "name", "en")
    assert not k.is_known("Fert", "word", "de")      # a surname, but not a German word
    assert k.is_known("fährt", "word", "de")


def _table():
    t = Table()
    for _ in range(10):
        t.add([("f", "f"), ("i", "I"), ("l", "l")])
        t.add([("ph", "f"), ("i", "I"), ("p", "p")])
        t.add([("a", "a"), ("ll", "l"), ("pp", "p")])
        t.add([("a", "a"), ("l", "l"), ("p", "p")])
    return t


def test_explain_variant_counts_changes():
    pairs = [("ph", "f"), ("i", "I"), ("l", "l"), ("i", "I"), ("p", "p")]
    lp, ch = explain_variant("Fillipp", pairs, _table())
    assert ch == 3 and lp > -5          # ph->f, l->ll, p->pp: all observed spellings
    lp0, ch0 = explain_variant("Philip", pairs, _table())
    assert (lp0, ch0) == (0.0, 0)
    lp_x, _ = explain_variant("Qhilip", pairs, _table())
    assert lp_x <= -8                    # never-seen spelling


def test_explain_variant_uses_other_positions():
    t = Table()
    for _ in range(10):
        t.add([("a", "a"), ("pp", "p"), ("y", "i")])   # 'pp' only in the middle
        t.add([("u", "u"), ("p", "p")])
    lp, ch = explain_variant("upp", [("u", "u"), ("p", "p")], t)
    assert ch == 1 and -8 < lp < 0
