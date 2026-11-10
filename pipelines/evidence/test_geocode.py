"""Geocoding resolver (brief E2 B2): regexes, bbox validation, GeoNames fixture, store update."""
from __future__ import annotations

import pandas as pd
import pytest

from pipelines.evidence import geocode_sites as gs


@pytest.mark.parametrize("text, expected", [
    ("The site is located at 9°02′N and 38°44′E at 2400 m", (9.03333, 38.73333)),
    ("located at 7.05° N, 38.47° E", (7.05, 38.47)),
    ("lat 9.03, long 38.74", (9.03, 38.74)),
    ("between 09° 01' 48'' N and 38° 45' 30'' E", (9.03, 38.75833)),
    ("N 11.6 E 37.4", (11.6, 37.4)),
    ("7°03'S, 39°17'E", (-7.05, 39.28333)),
])
def test_parse_coordinates(text, expected):
    pairs = gs.parse_coordinates(text)
    assert len(pairs) == 1
    assert pairs[0][:2] == pytest.approx(expected, abs=1e-4)


def test_no_coordinates_in_plain_text():
    assert gs.parse_coordinates("Yield increased by 12% over 3 years at 2,400 m altitude.") == []


def test_site_sentences():
    s = gs.site_sentences("Maize was grown. The study area is located in Dedo district, Jimma zone. Yields rose.")
    assert s == ["The study area is located in Dedo district, Jimma zone."]


def test_bbox_from_country_config():
    bbox = gs.country_bbox("ET")
    assert gs.in_bbox(9.0, 38.7, bbox) and not gs.in_bbox(48.8, 2.3, bbox)
    assert gs.in_bbox(1.0, 1.0, None)


def _gazetteer():
    rows = [
        # geonameid, name, asciiname, alternatenames, lat, lon, class, code, cc, admin1, population
        ("1", "Holeta", "Holeta", "Holetta,Genet", 9.06, 38.50, "P", "PPL", "ET", "51", 30000),
        ("2", "Dedo", "Dedo", "", 7.52, 36.86, "A", "ADM3", "ET", "51", 0),
        ("3", "Dedo", "Dedo", "", 11.0, 39.0, "P", "PPL", "ET", "46", 200),
        ("4", "Oromiya", "Oromiya", "Oromia", 8.0, 39.0, "A", "ADM1", "ET", "51", 0),
        ("5", "Mount X", "Mount X", "", 9.0, 39.0, "T", "MT", "ET", "51", 0),
    ]
    df = pd.DataFrame(rows, columns=["geonameid", "name", "asciiname", "alternatenames", "latitude", "longitude",
                                     "feature_class", "feature_code", "country_code", "admin1", "population"])
    return gs.Gazetteer.build(df, {"ET.51": "Oromiya", "ET.46": "Amhara"})


def test_gazetteer_resolution():
    g = _gazetteer()
    hit = g.resolve("Holetta Agricultural Research Center", ["Oromia"])
    assert hit["geonames_id"] == 1 and hit["loc_precision"] == "site"
    amhara = g.resolve("Dedo", ["Amhara"])                       # admin agreement picks the Amhara place
    assert amhara["geonames_id"] == 3
    assert g.resolve("Dedo woreda", ["Oromia"])["geonames_id"] == 2   # Oromia: the district
    assert g.resolve("Oromia", []) is None                        # ADM1 is not a usable position
    assert g.resolve("Mount X", []) is None                       # class T is not used
    assert g.resolve("Nowhere", []) is None


def test_resolve_study_rules():
    g = _gazetteer()
    rec = {"study_id": "HAB_X_2020", "doi": "10.1/x", "country": "ET", "zone_text": "Sub-humid Oromia"}
    text = "The experiment was conducted at Holetta (9°04′N, 38°30′E), Oromia."
    stated = {"sites": [{"name": "Holetta", "admin": ["Oromia"], "lat": 9.0667, "lon": 38.5,
                         "coordinate_source": "stated", "quote": "The experiment was conducted at Holetta"}],
              "confidence": 0.9}
    row = gs.resolve_study(rec, text, stated, g)
    assert row["method"] == "stated_coordinates_llm_regex" and row["loc_precision"] == "site"
    assert row["quote_verified"] == "yes"
    invented = {"sites": [{"name": "Holetta", "admin": ["Oromia"], "lat": 5.0, "lon": 40.0,
                           "coordinate_source": "stated", "quote": "made up"}], "confidence": 0.9}
    row2 = gs.resolve_study(rec, "The experiment was conducted at Holetta, Oromia.", invented, g)
    assert row2["method"].startswith("geonames:") and row2["lat"] == pytest.approx(9.06)  # not the invented point
    assert row2["quote_verified"] == "no"
    outside = gs.resolve_study(rec, "Site at 48.8° N, 2.3° E.", None, g)            # Paris: outside ET bbox
    assert outside["loc_precision"] == "country" and outside["quote"]
    nothing = gs.resolve_study({**rec, "zone_text": ""}, "", None, g)
    assert nothing["loc_precision"] == "country" and nothing["quote"].startswith("No site statement")


def test_parse_site_answer_is_defensive():
    ans = gs.parse_site_answer('{"sites": [{"name": "Dedo", "admin": ["Jimma"], "lat": "x", "coordinate_source": '
                               '"stated", "quote": "q"}, {"name": ""}], "confidence": 3}')
    assert ans["sites"][0]["coordinate_source"] == "none" and len(ans["sites"]) == 1 and ans["confidence"] == 1.0
    assert gs.parse_site_answer("not json") == {"sites": [], "confidence": 0.0}


def test_apply_geocoding_and_frame(tmp_path):
    sheet = pd.DataFrame([
        {"study_id": "HAB_A", "lat": "9.0", "lon": "38.5", "loc_precision": "site", "site_name": "A", "method": "m",
         "quote": "q", "accepted": "yes"},
        {"study_id": "HAB_B", "lat": "7.5", "lon": "36.9", "loc_precision": "district", "site_name": "B", "method": "m",
         "quote": "q", "accepted": ""},
        {"study_id": "HAB_C", "lat": "", "lon": "", "loc_precision": "country", "site_name": "", "method": "unresolved",
         "quote": "q", "accepted": ""},
        {"study_id": "HAB_D", "lat": "1", "lon": "1", "loc_precision": "site", "site_name": "D", "method": "m",
         "quote": "q", "accepted": "no"},
    ]).reindex(columns=gs.REVIEW_COLUMNS).fillna("")
    sheet.to_csv(tmp_path / "rev.csv", index=False)
    out = gs.apply_geocoding(tmp_path / "rev.csv", tmp_path / "applied.csv")
    assert list(out["study_id"]) == ["HAB_A", "HAB_B"]
    assert list(out["loc_method"]) == ["geocoded_llm_checked", "geocoded_llm_unchecked"]
    df = pd.DataFrame({"study_id": ["HAB_A", "HAB_B", "HAB_C"], "lat": [None] * 3, "lon": [None] * 3,
                       "loc_precision": ["country"] * 3, "loc_method": ["none"] * 3})
    got = gs.apply_to_frame(df, tmp_path / "applied.csv")
    assert got.loc[0, "lat"] == 9.0 and got.loc[0, "loc_method"] == "geocoded_llm_checked"
    assert got.loc[1, "loc_precision"] == "district" and got.loc[1, "loc_method"] == "geocoded_llm_unchecked"
    assert got.loc[2, "loc_method"] == "none" and pd.isna(got.loc[2, "lat"])


def test_review_map_is_self_contained():
    sheet = pd.DataFrame([{"study_id": "HAB_A", "lat": "9.0", "lon": "38.5", "site_name": "A</script>",
                           "loc_precision": "site", "method": "m", "confidence": "0.9", "quote": "q", "accepted": ""}])
    html = gs.review_map(sheet.reindex(columns=gs.REVIEW_COLUMNS).fillna(""))
    assert "leaflet@1.9.4" in html and "<\\/script>" in html and "HAB_A" in html
