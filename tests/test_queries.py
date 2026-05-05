# tests/test_queries.py
import site_queries

DB = "data/streets.db"


def _conn():
    return site_queries.get_connection(DB)


def test_section1_shape():
    d = site_queries.section1(_conn())
    assert "total_streets" in d
    assert isinstance(d["total_streets"], int)
    assert d["total_streets"] > 100_000

    assert "top_men" in d
    assert len(d["top_men"]) == 5
    assert "full_name" in d["top_men"][0]
    assert "street_count" in d["top_men"][0]

    assert "top_women" in d
    # May be empty if no women classified yet — that's OK
    assert isinstance(d["top_women"], list)

    assert "total_persons_m" in d
    assert "total_persons_f" in d
    assert isinstance(d["total_persons_m"], int)
    assert isinstance(d["total_persons_f"], int)


def test_section2_shape():
    d = site_queries.section2(_conn())
    assert "top_names" in d
    assert len(d["top_names"]) == 50
    row = d["top_names"][0]
    assert "name_normalized" in row
    assert "street_count" in row
    assert "category" in row
    assert isinstance(row["street_count"], int)


def test_section3_shape():
    d = site_queries.section3(_conn())
    assert "top_persons" in d
    assert len(d["top_persons"]) >= 1
    row = d["top_persons"][0]
    assert "full_name" in row
    assert "street_count" in row
    assert "gender" in row

    assert "total_m" in d
    assert "total_f" in d
    assert isinstance(d["total_m"], int)

    assert "profession_dist" in d
    assert "era_dist" in d


def test_section4_shape():
    d = site_queries.section4(_conn())
    assert "top_pageviews" in d
    assert isinstance(d["top_pageviews"], list)

    assert "tier_counts" in d
    assert "universal" in d["tier_counts"]
    assert "national" in d["tier_counts"]
    assert "local" in d["tier_counts"]
    assert isinstance(d["tier_counts"]["universal"], int)


def test_section5_shape():
    d = site_queries.section5(_conn())
    assert "theme_dist" in d
    assert len(d["theme_dist"]) >= 1
    for row in d["theme_dist"]:
        assert "category" in row
        assert "count" in row

    assert "nature_subtypes" in d
    assert "ideo_tokens" in d


def test_section6_shape():
    d = site_queries.section6(_conn())
    assert "by_judet" in d
    assert len(d["by_judet"]) >= 40
    row = d["by_judet"][0]
    assert "judet" in row
    assert "total_streets" in row
    assert "saint_pct" in row
    assert "numeric_pct" in row
    assert "modal_name" in row


def test_section8_shape():
    d = site_queries.section8(_conn())
    assert "ciorani" in d
    assert "total" in d["ciorani"]
    assert "numeric" in d["ciorani"]

    assert "longest_names" in d
    assert isinstance(d["longest_names"], list)

    assert "animal_names" in d
    assert isinstance(d["animal_names"], list)

    assert "local_honorees" in d
    assert isinstance(d["local_honorees"], list)
