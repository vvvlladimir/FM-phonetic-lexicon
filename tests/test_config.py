from src import config


def test_country_to_lang_mapping():
    expected = {"US": "en", "GB": "en", "DE": "de", "AT": "de", "FR": "fr", "ES": "es",
                "MX": "es", "IT": "it", "PT": "pt", "BR": "pt", "NL": "nl", "RU": "ru",
                "PL": "pl", "TR": "tr"}
    for c, l in expected.items():
        assert config.lang_for_country(c) == l
    assert config.lang_for_country("us") == "en"
    assert config.lang_for_country("JP") is None


def test_every_mapped_lang_has_voice():
    assert set(config.COUNTRY_TO_LANG.values()) <= set(config.ESPEAK_VOICES)
    assert len(config.LANGS) == 10


def test_countries_for_lang():
    assert sorted(config.countries_for_lang("pt")) == ["BR", "PT"]


def test_every_category_has_freq_scale():
    assert set(config.CATEGORIES) == set(config.FREQ_SCALE)
