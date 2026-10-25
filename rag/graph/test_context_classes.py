"""Unit tests for the engine-context -> QT class mapper (Phase P6b-i).

Band edges are tested exhaustively: every boundary is checked on both sides,
because an off-by-one here silently mis-files a pin into the wrong WOCAT
context and the error would only ever surface as a slightly wrong
"similar technologies" list.

Run from the repo root:
    python -m pytest rag/graph/test_context_classes.py -q
"""
from __future__ import annotations

import pytest

from rag.graph import wocat_taxonomy as wt
from rag.graph.context_classes import (
    MAPPERS,
    SOURCE_KEYS,
    agroclimatic_zone_from_lgp,
    altitude_zone,
    context_to_classes,
    rainfall_band,
    slope_class,
    soil_texture_from_clay,
)


# ------------------------------------------------------------- band edges
@pytest.mark.parametrize("mm,expected", [
    (0, "< 250 mm"), (249.9, "< 250 mm"), (250, "< 250 mm"),
    (250.1, "251-500 mm"), (500, "251-500 mm"),
    (500.1, "501-750 mm"), (750, "501-750 mm"),
    (750.1, "751-1,000 mm"), (1000, "751-1,000 mm"),
    (1000.1, "1,001-1,500 mm"), (1500, "1,001-1,500 mm"),
    (1500.1, "1,501-2,000 mm"), (1947, "1,501-2,000 mm"), (2000, "1,501-2,000 mm"),
    (2000.1, "2,001-3,000 mm"), (3000, "2,001-3,000 mm"),
    (3000.1, "3,001-4,000 mm"), (4000, "3,001-4,000 mm"),
    (4000.1, "> 4,000 mm"), (9000, "> 4,000 mm"),
])
def test_rainfall_band_edges(mm, expected):
    assert rainfall_band(mm) == expected


@pytest.mark.parametrize("pct,expected", [
    (0, "flat (0-2%)"), (2, "flat (0-2%)"),
    (2.1, "gentle (3-5%)"), (5, "gentle (3-5%)"),
    (5.1, "moderate (6-10%)"), (10, "moderate (6-10%)"),
    (10.1, "rolling (11-15%)"), (15, "rolling (11-15%)"),
    (15.1, "hilly (16-30%)"), (30, "hilly (16-30%)"),
    (30.1, "steep (31-60%)"), (60, "steep (31-60%)"),
    (60.1, "very steep (> 60%)"), (89, "very steep (> 60%)"),
])
def test_slope_class_edges(pct, expected):
    assert slope_class(pct) == expected


@pytest.mark.parametrize("m,expected", [
    (-100, "< 100 m a.s.l."), (100, "< 100 m a.s.l."),
    (100.1, "101-500 m a.s.l."), (500, "101-500 m a.s.l."),
    (500.1, "501-1,000 m a.s.l."), (1000, "501-1,000 m a.s.l."),
    (1000.1, "1,001-1,500 m a.s.l."), (1500, "1,001-1,500 m a.s.l."),
    (1500.1, "1,501-2,000 m a.s.l."), (2000, "1,501-2,000 m a.s.l."),
    (2000.1, "2,001-2,500 m a.s.l."), (2500, "2,001-2,500 m a.s.l."),
    (2500.1, "2,501-3,000 m a.s.l."), (3000, "2,501-3,000 m a.s.l."),
    (3000.1, "3,001-4,000 m a.s.l."), (4000, "3,001-4,000 m a.s.l."),
    (4000.1, "> 4,000 m a.s.l."),
])
def test_altitude_zone_edges(m, expected):
    assert altitude_zone(m) == expected


@pytest.mark.parametrize("clay,expected", [
    (0, "coarse/ light (sandy)"), (17.9, "coarse/ light (sandy)"),
    (18, "coarse/ light (sandy)"),
    (18.1, "medium (loamy, silty)"), (30, "medium (loamy, silty)"),
    (35, "medium (loamy, silty)"),
    (35.1, "fine/ heavy (clay)"), (100, "fine/ heavy (clay)"),
])
def test_soil_texture_edges(clay, expected):
    assert soil_texture_from_clay(clay) == expected


@pytest.mark.parametrize("days,expected", [
    (0, "arid"), (74, "arid"), (75, "arid"),
    (75.1, "semi-arid"), (179, "semi-arid"), (180, "semi-arid"),
    (180.1, "sub-humid"), (269, "sub-humid"), (270, "sub-humid"),
    (270.1, "humid"), (366, "humid"),
])
def test_agroclimatic_zone_edges(days, expected):
    assert agroclimatic_zone_from_lgp(days) == expected


def test_lgp_bands_agree_with_the_questionnaire_definitions():
    """Spot-check against QT §5.1's own wording, transcribed in the taxonomy."""
    assert set(wt.AGROCLIMATIC_ZONE_LGP) == {"humid", "sub-humid", "semi-arid", "arid"}
    assert agroclimatic_zone_from_lgp(300) == "humid"       # QT: LGP > 270
    assert agroclimatic_zone_from_lgp(200) == "sub-humid"   # QT: 180-269
    assert agroclimatic_zone_from_lgp(100) == "semi-arid"   # QT: 75-179
    assert agroclimatic_zone_from_lgp(50) == "arid"         # QT: < 74


# ------------------------------------------------------- refusing to guess
@pytest.mark.parametrize("bad", [None, "", "n/a", float("nan"), float("inf"), [], {}])
def test_unusable_values_map_to_nothing(bad):
    for mapper in MAPPERS.values():
        assert mapper(bad) is None, (mapper, bad)


@pytest.mark.parametrize("mapper,value", [
    (rainfall_band, -1), (rainfall_band, -9999),
    (slope_class, -5), (slope_class, 91),
    (altitude_zone, -600), (altitude_zone, 9001),
    (soil_texture_from_clay, -1), (soil_texture_from_clay, 101),
    (agroclimatic_zone_from_lgp, -1), (agroclimatic_zone_from_lgp, 400),
])
def test_out_of_range_values_map_to_nothing(mapper, value):
    """Nodata sentinels and unit mix-ups must not become a band."""
    assert mapper(value) is None


def test_booleans_are_not_numbers():
    assert rainfall_band(True) is None and slope_class(False) is None


def test_numeric_strings_are_accepted():
    assert rainfall_band("812.5") == "751-1,000 mm"


# ------------------------------------------------------------- the mapper
def test_context_to_classes_on_a_real_pin():
    ctx = {"aez_belt": "Moist Weyna Dega", "Rainfall": 1947.0, "slope": 4.0,
           "Altitude_r": 1800.0, "soil_clay": 30.0, "lgp_days": 200.0,
           "temp_mean_annual": 19.2, "soil_ph": 6.1, "soil_soc": 1.4,
           "land_cover": 40, "precip_seasonality": 70.0}
    assert context_to_classes(ctx) == {
        "rainfall_band": "1,501-2,000 mm",
        "slope_class": "gentle (3-5%)",
        "altitude_zone": "1,501-2,000 m a.s.l.",
        "soil_texture": "medium (loamy, silty)",
        "agroclimatic_zone": "sub-humid",
    }


def test_context_to_classes_omits_rather_than_guesses():
    ctx = {"Rainfall": 812.5, "slope": None, "soil_clay": -9999, "lgp_days": "x"}
    assert context_to_classes(ctx) == {"rainfall_band": "751-1,000 mm"}


@pytest.mark.parametrize("ctx", [None, {}, {"temp_mean_annual": 19.0}])
def test_context_to_classes_handles_empty_input(ctx):
    assert context_to_classes(ctx) == {}


def test_every_output_is_a_real_questionnaire_class():
    """Guards against a typo in the band tables drifting from the taxonomy."""
    for kind, mapper in MAPPERS.items():
        for probe in (0, 1, 10, 50, 100, 200, 400, 1200, 2600, 3500, 5000):
            label = mapper(probe)
            if label is not None:
                assert label in wt.CONTEXT_CLASSES[kind], (kind, probe, label)


def test_every_mapped_kind_is_a_graph_context_kind():
    from rag.graph.schema import CONTEXT_CLASS_KINDS

    for kind in SOURCE_KEYS.values():
        assert kind in CONTEXT_CLASS_KINDS, kind
    assert set(SOURCE_KEYS.values()) == set(MAPPERS)


def test_source_keys_match_what_the_engine_actually_returns():
    """The keys are recommend.STACK's output names — wrap, never fork."""
    import ast
    from pathlib import Path

    source = (Path(__file__).resolve().parents[2]
              / "app" / "backend" / "recommend.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    stack = next(
        ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(getattr(t, "id", None) == "STACK" for t in node.targets)
    )
    engine_keys = set(stack.values()) | {"aez_belt"}
    missing = set(SOURCE_KEYS) - engine_keys
    assert not missing, f"context keys the engine never produces: {missing}"
