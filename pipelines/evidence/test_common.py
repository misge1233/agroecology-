"""Tests for ``pipelines.evidence.common``: text numerics, effect sizes, ids."""
from __future__ import annotations

import math

import pandas as pd
import pytest

from pipelines.evidence import common


# The awkward strings seen in the Habtamu sheet (brief Part E), plus edge cases.
@pytest.mark.parametrize("raw, mean, context, rule", [
    ("700–900 mm yr⁻¹", None, 800.0, "range_as_null"),
    ("~800", 800.0, 800.0, "approx"),
    ("1,204", 1204.0, 1204.0, "thousands_separator"),
    ("NR", None, None, "missing"),
    ("NA", None, None, "missing"),
    ("", None, None, "missing"),
    ("12 ± 3", 12.0, 12.0, "plus_minus_first"),
    ("0–34 years", None, 17.0, "range_as_null"),
    ("2 to 4", None, 3.0, "range_as_null"),
    ("535-788 MASL", None, 661.5, "range_as_null"),
    ("1300 mm yr⁻¹", 1300.0, 1300.0, "number_with_unit"),
    ("<0.05", None, None, "comparator_bound"),
    ("1,2", None, None, "ambiguous_decimal_comma"),
    ("-2.5", -2.5, -2.5, "number"),
    ("Mediterranean", None, None, "unparsed"),
])
def test_parse_quantity_table(raw, mean, context, rule):
    p = common.parse_quantity(raw, kind="mean")
    assert p.value == mean
    assert p.rule == rule
    assert common.parse_number(raw, kind="context") == context


def test_parse_quantity_keeps_unit_and_range():
    p = common.parse_quantity("700–900 mm yr⁻¹", kind="context")
    assert (p.low, p.high, p.unit) == (700.0, 900.0, "mm yr-1")


def test_parse_number_passes_numbers_through():
    assert common.parse_number(3.5) == 3.5
    assert common.parse_number(None) is None
    assert common.parse_number(float("nan")) is None


def test_lrr_and_var():
    assert common.lrr(120, 100) == pytest.approx(math.log(1.2))
    assert common.lrr(0, 100) is None and common.lrr(10, None) is None
    v = common.var_lrr(120, 100, 10, 8, 4, 4)
    assert v == pytest.approx(100 / (4 * 120 ** 2) + 64 / (4 * 100 ** 2))
    assert common.var_lrr(120, 100, 0, 0, 4, 4) is None  # zero variance is not usable
    assert common.var_lrr(120, 100, 10, None, 4, 4) is None


def test_vectorised_effect_sizes_match_scalar():
    df = pd.DataFrame({"mean_with": [120.0, 0.0, 50.0], "mean_without": [100.0, 5.0, 40.0],
                       "sd_with": [10.0, 1.0, None], "sd_without": [8.0, 1.0, 2.0],
                       "n_with": [4, 4, 3], "n_without": [4, 4, 3]})
    lrr = common.lrr_series(df["mean_with"], df["mean_without"])
    assert lrr[0] == pytest.approx(math.log(1.2)) and pd.isna(lrr[1])
    var = common.var_lrr_series(df)
    assert var[0] == pytest.approx(common.var_lrr(120, 100, 10, 8, 4, 4)) and var[1:].isna().all()


def test_ids():
    assert common.slug("Roschewitz_2005_001") == "Roschewitz_2005_001"
    assert common.slug("De Oliveira, 2026") == "De_Oliveira_2026"
    assert common.upper_snake("Inorganic Fertilizer-Organic Fertilizer") == "INORGANIC_FERTILIZER_ORGANIC_FERTILIZER"
    assert common.upper_snake("Physical + Biological SWC practices") == "PHYSICAL_PLUS_BIOLOGICAL_SWC_PRACTICES"
    ids = common.make_row_ids("ERA", pd.Series(["ERA_A", "ERA_B", "ERA_A"]))
    assert list(ids) == ["ERA:ERA_A:1", "ERA:ERA_B:1", "ERA:ERA_A:2"]


def test_normalise_doi():
    assert common.normalise_doi("https://doi.org/10.1016/J.AGEE.2020.1") == ("10.1016/j.agee.2020.1", None)
    assert common.normalise_doi("IJPSS.2014.8.004") == (None, "IJPSS.2014.8.004")
    assert common.normalise_doi("NR") == (None, None)


def test_mark_duplicates_and_row_key():
    df = pd.DataFrame({"a": [1, 1, 2, 1], "b": [None, None, "x", None]})
    ids = pd.Series(["r1", "r2", "r3", "r4"])
    dup = common.mark_duplicates(df, ["a", "b"], ids)
    assert list(dup) == [None, "r1", None, "r1"]
    assert common.row_key(df, ["a", "b"]).iloc[0] == common.row_key(df, ["a", "b"]).iloc[1]


def test_json_extra_drops_nulls():
    assert common.json_extra({"a": None, "b": float("nan"), "c": "", "d": 1}) == '{"d": 1}'
    assert common.json_extra({"a": None}) is None
