"""Tests for the external-signal helpers."""


def test_english_common_flags_dictionary_words():
    from cleo.discovery_v2.signals import is_english_common_token

    assert is_english_common_token("river")
    assert is_english_common_token("insurance")
    assert is_english_common_token("valley")
    assert is_english_common_token("holdings")


def test_english_common_does_not_flag_made_up_names():
    from cleo.discovery_v2.signals import is_english_common_token

    assert not is_english_common_token("metrus")
    assert not is_english_common_token("kingsett")
    assert not is_english_common_token("rasenberg")  # rare surname, below threshold


def test_english_common_threshold_is_configurable():
    from cleo.discovery_v2.signals import is_english_common_token

    # 'river' Zipf ~5.63 — common at any reasonable threshold
    assert is_english_common_token("river", zipf_threshold=3.0)
    assert is_english_common_token("river", zipf_threshold=5.0)
    # With threshold 6.5, river falls below
    assert not is_english_common_token("river", zipf_threshold=6.5)


def test_place_name_flags_ontario_cities():
    from cleo.discovery_v2.signals import load_place_names, is_place_name

    places = load_place_names()
    assert is_place_name("toronto", places)
    assert is_place_name("ottawa", places)
    assert is_place_name("windsor", places)
    assert is_place_name("ontario", places)


def test_place_name_not_flags_non_places():
    from cleo.discovery_v2.signals import load_place_names, is_place_name

    places = load_place_names()
    assert not is_place_name("kingsett", places)
    assert not is_place_name("metrus", places)


def test_industry_stopwords_loads_seed_and_db_entries():
    """Seed entries in the JSON + any DB entries are combined."""
    import sqlite3
    from cleo.discovery_v2.signals import load_industry_stopwords

    conn = sqlite3.connect(":memory:")
    conn.executescript("""
        CREATE TABLE industry_stopwords (
            token TEXT PRIMARY KEY, added_by TEXT, added_at TEXT, source TEXT
        );
        INSERT INTO industry_stopwords VALUES ('brickyard', 'brandon', datetime('now'), 'user');
    """)

    stopwords = load_industry_stopwords(conn)
    assert "gp" in stopwords  # from seed
    assert "reit" in stopwords  # from seed
    assert "brickyard" in stopwords  # user-added
