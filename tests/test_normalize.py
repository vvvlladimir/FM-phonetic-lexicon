import unicodedata

from src.normalize import clean, dedupe, is_valid, normalize


def test_nfc_and_whitespace():
    decomposed = "Müller"  # u + combining diaeresis
    assert unicodedata.is_normalized("NFD", decomposed)
    out = normalize(f"  {decomposed}\t ")
    assert out == "Müller" and unicodedata.is_normalized("NFC", out)
    assert normalize("Van   Den\nBerg") == "Van Den Berg"


def test_words_reject_digits_punct_short():
    assert is_valid("hello", "en", "word")
    assert not is_valid("a", "en", "word")
    assert not is_valid("covid19", "en", "word")
    assert not is_valid("don't", "en", "word")
    assert not is_valid("e-mail", "en", "word")


def test_names_allow_hyphen_apostrophe_space():
    assert is_valid("O'Brien", "en", "last_name")
    assert is_valid("Saint-Denis", "fr", "city")
    assert is_valid("De Jong", "nl", "last_name")
    assert not is_valid("St. Louis", "en", "city")
    assert not is_valid("--", "en", "city")


def test_script_filter():
    assert is_valid("Москва", "ru", "city")
    assert not is_valid("Moscow", "ru", "city")
    assert not is_valid("Москва", "en", "city")
    assert is_valid("Łódź", "pl", "city")
    assert is_valid("Yılmaz", "tr", "last_name")


def test_clean_returns_none_for_invalid():
    assert clean("  Paris ", "fr", "city") == "Paris"
    assert clean("123", "fr", "city") is None


def test_dedupe_keeps_best():
    recs = [
        {"text": "John", "lang": "en", "category": "first_name", "frequency": 5.0, "origin_country": "GB"},
        {"text": "John", "lang": "en", "category": "first_name", "frequency": 2.0, "origin_country": "US"},
    ]
    assert dedupe(recs, higher_is_better=False)[0]["origin_country"] == "US"
    assert dedupe(recs, higher_is_better=True)[0]["origin_country"] == "GB"


def test_typographic_apostrophe_unified():
    assert normalize("People’s Republic") == "People's Republic"
    assert clean("D’Angelo", "it", "last_name") == "D'Angelo"
