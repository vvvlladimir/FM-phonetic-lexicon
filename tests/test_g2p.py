import shutil

import pytest

from src import db
from src.espeak_trace import _parse_clause, clean_ph, trace_words
from src.g2p import Table, align_to_final, build_alignments, position
from src.phonetic import (ru_equivalent, similarity, sound_neighbours, strip_diacritics,
                          stressed_vowel_index)
from src.variants import deaccent_variants, generate

needs_espeak = pytest.mark.skipif(shutil.which("espeak-ng") is None, reason="espeak-ng missing")

PHILIP_TRACE = """Unpronouncable? 'philip'
 46\t_) ph (  [f]
Translate 'philip'
  1\tp        [p]
 22\tph       [f]
 46\t_) ph (  [f]

  1\ti        [I]

  1\tl        [l]

  1\ti        [I]

  1\tp        [p]
""".split("\n")


# --- eSpeak trace parsing ---------------------------------------------------------

def test_parse_picks_highest_score_and_ignores_unpronounceable_pass():
    t = _parse_clause("Philip", PHILIP_TRACE, "f'IlIp")
    assert t.chunks == [("ph", "f"), ("i", "I"), ("l", "l"), ("i", "I"), ("p", "p")]
    assert t.rules_ok and t.final == "fIlIp"


def test_parse_ignores_second_translate_of_stem():
    lines = ["Translate 'akça'", "  1\ta        [a]", "", "  1\tk        [k]", "",
             " 36\tç       [tS]", "", "  1\ta        [a]", "",
             "Translate 'akç'", "  1\ta        [a]", ""]
    t = _parse_clause("Akça", lines, "aktS'a")
    assert "".join(g for g, _ in t.chunks) == "akça" and t.rules_ok


def test_parse_dictionary_word():
    t = _parse_clause("Stephen", ["Found: 'stephen' [sti:v@n]  "], "st'i:v@n")
    assert not t.rules_ok and t.dict_ph == "sti:v@n" and "dictionary" in t.notes


def test_clean_ph_strips_stress_and_language_flags():
    assert clean_ph("(en)dZ'0n(de)") == "dZ0n"
    assert clean_ph("f'IlIp") == "fIlIp"


@needs_espeak
def test_trace_words_batch_matches_single_calls():
    words = ["Philip", "Stephen", "knight", "arrest", "Pferd"]
    batch = trace_words(words, "en-us")
    assert [t.word for t in batch] == words
    assert batch[2].chunks[0] == ("kn", "n")
    assert batch[3].rules_ok  # final line "3r'Est" starts with a digit


# --- alignment / table ------------------------------------------------------------

def test_align_to_final_handles_vowel_reduction():
    chunks = [("м", "m"), ("о", "o"), ("л", "l"), ("о", "o"), ("к", "k"), ("о", "o")]
    assert align_to_final(chunks, "mVlVko") == ["m", "V", "l", "V", "k", "o"]


def test_position():
    assert [position(i, 3) for i in range(3)] == ["B", "M", "E"]


def _toy_table():
    t = Table()
    for _ in range(10):
        t.add([("f", "f"), ("i", "I"), ("x", "ks")])
        t.add([("ph", "f"), ("o", "o"), ("n", "n")])
        t.add([("a", "a"), ("ph", "f"), ("e", "")])
    for _ in range(5):
        t.add([("a", "a"), ("f", "f"), ("t", "t")])
    return t


def test_table_probabilities():
    t = _toy_table()
    alts = dict(t.alternatives("f", "B"))
    assert alts == {"f": 0.5, "ph": 0.5}
    assert dict(t.alternatives("", "E")) == {"e": 1.0}


def test_viterbi_align_uses_table():
    t = _toy_table()
    assert t.viterbi_align("phon", "fon") == [("ph", "f"), ("o", "o"), ("n", "n")]


def test_build_alignments_counts_methods():
    good = _parse_clause("Philip", PHILIP_TRACE, "f'IlIp")
    dict_word = _parse_clause("Phip", ["Found: 'phip' [fIp]"], "f'Ip")
    aligned, table, stats = build_alignments([good, dict_word])
    assert stats["rules"] == 1 and stats["viterbi"] == 1
    assert aligned["Phip"][0] == "viterbi" and aligned["Phip"][1][0] == ("ph", "f")


# --- generation -------------------------------------------------------------------

def test_generate_respell_keeps_case_and_excludes_original():
    t = _toy_table()
    out = generate("Phix", [("ph", "f"), ("i", "I"), ("x", "ks")], t)
    texts = [c.text for c in out]
    assert "Fix" in texts and "Phix" not in texts
    assert all(c.text[0].isupper() for c in out)
    assert next(c for c in out if c.text == "Fix").kinds == ("respell",)


def test_generate_silent_letters():
    t = _toy_table()
    out = {c.text: c.kinds for c in generate("aphe", [("a", "a"), ("ph", "f"), ("e", "")], t)}
    assert "aph" in out and "silent" in out["aph"]          # silent e dropped


def test_generate_near_sound_limited_to_one_change():
    t = _toy_table()
    out = generate("fon", [("f", "f"), ("o", "o"), ("n", "n")], t, neighbours={"f": ["ks"], "n": ["ks"]})
    for c in out:
        assert c.text.count("x") <= 1


def test_deaccent():
    assert strip_diacritics("ş") == "s" and strip_diacritics("ı") == "i" and strip_diacritics("ł") == "l"
    assert strip_diacritics("й") == "й"  # Cyrillic letters are not "diacritics"
    texts = {c.text for c in deaccent_variants("Şahinç")}
    assert texts == {"Sahinc", "Sahinç", "Şahinc"}
    assert deaccent_variants("Philip") == []


# --- phonetic comparison ----------------------------------------------------------

def test_similarity():
    assert similarity("pa", "pa") == 1.0
    assert similarity("pa", "ba") > similarity("pa", "ma") > similarity("pa", "a")


def test_neighbours_include_dropped_sound():
    nb = sound_neighbours({"pF": "pf", "f": "f", "p": "p", "b": "b", "a": "a"})
    assert "f" in nb["pF"] and "b" in nb["p"] and "a" not in nb["p"]


def test_ru_unstressed_vowels():
    idx = stressed_vowel_index("mʌɭʌkˈo")  # молоко, stress on 3rd vowel
    assert idx == 2
    assert ru_equivalent("молоко", "малоко", "mʌɭʌko", "maɭokʌ", idx)
    assert not ru_equivalent("молоко", "молока", "mʌɭʌko", "mʌɭʌkʌ", idx)   # stressed vowel changed
    assert not ru_equivalent("молоко", "мулоко", "mʌɭʌko", "muɭokʌ", idx)   # у is not о/а
    assert not ru_equivalent("молоко", "молого", "mʌɭʌko", "mʌɭʌɡo", idx)   # consonant changed


def test_variants_table_unique():
    conn = db.connect(":memory:")
    row = ("Philip", "en", "Filip", "respell", "homophone", 1.0, -0.5, 1, 0, "fɪlɪp")
    sql = ("INSERT INTO variants (text, lang, variant, kinds, match, similarity, score, "
           "attested_name, attested_entry, ipa) VALUES (?,?,?,?,?,?,?,?,?,?)")
    conn.execute(sql, row)
    with pytest.raises(Exception):
        conn.execute(sql, row)


def test_generate_output_unique_for_turkish_dotted_i():
    t = Table()
    for _ in range(5):
        t.add([("ş", "S"), ("i", "i")])
        t.add([("ş", "S"), ("ı", "@")])
        t.add([("s", "S"), ("i", "i")])
    out = [c.text for c in generate("Şi", [("ş", "S"), ("i", "i")], t)]
    assert len(out) == len(set(out)) and "Si" in out


def test_silent_letters_ignore_mostly_pronounced_letters():
    t = Table()
    for _ in range(10):
        t.add([("a", "a"), ("n", "n")])   # final n usually pronounced
        t.add([("o", "o"), ("e", "")])    # final e always silent
    for _ in range(4):
        t.add([("a", "a"), ("n", "")])    # alignment noise: n -> nothing
    assert [g for g, _ in t.silent_letters("E")] == ["e"]


def test_neighbours_prefer_frequent_mnemonic_for_same_ipa():
    nb = sound_neighbours({"pF": "pf", "f": "f", ":f": "f"}, freq={"f": 1000, ":f": 3})
    assert "f" in nb["pF"] and ":f" not in nb["pF"]
