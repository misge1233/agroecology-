"""Evidence fusion (U9): lead source, disagreement, ordering, caution, rounding.

Synthetic graph + injected study statistics — no dataset, rasters or model.
Rules under test: docs/decisions/evidence_fusion.md §3–§5.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import pytest

from app.config import Settings
from app.services import fusion_service as fu
from app.services.numbers import display_text, display_value, number

log = math.log


def _settings(**kw: Any) -> Settings:
    return Settings(_env_file=None, openai_api_key="", **kw)


class Graph:
    """``studies[(practice, indicator)]`` → list of study dicts as the graph returns them."""

    def __init__(self, studies: dict[tuple[str, str], list[dict[str, Any]]]) -> None:
        self.studies = studies

    def evidence_summary(self, practice: str, indicator: str) -> dict[str, Any]:
        return {"studies": self.studies.get((practice, indicator), [])}


def study(no: str, effect_pct: float, n: int, belts: dict[str, int]) -> dict[str, Any]:
    return {"study_no": no, "era_code": f"E{no}", "title": f"Study {no}", "year": 2015, "doi": None,
            "mean_log_rr": log(1 + effect_pct / 100), "n_obs": n, "share_positive": 0.0, "obs_by_belt": belts}


def payload(items: list[tuple[str, float]], confidence: str = "low", belt: str = "Dry Kolla",
            indicator: str = "soil loss", direction: str = "reduce") -> dict[str, Any]:
    return {
        "query": {"indicator": indicator, "goal_direction": direction},
        "details": {"confidence": confidence, "context": {"aez_belt": belt},
                    "ranked": [{"practice": p, "pct_change": v, "log_ratio": round(log(1 + v / 100), 4), "n_evidence": 3}
                               for p, v in items]},
    }


def fuse(p: dict[str, Any], graph: Graph, stats: dict | None = None, **settings: Any) -> list[dict[str, Any]]:
    return fu.fuse(p, graph_query=graph, settings=_settings(**settings),
                   stats_fn=lambda: (stats or {}, {"soil loss": 0.6, "yield": 0.4}),
                   rmse_fn=lambda: {"soil loss": 0.5, "yield": 0.3})


# ------------------------------------------------------------- lead source
def test_model_leads_when_confident_and_measured_in_the_users_zone() -> None:
    g = Graph({("Mulch", "soil loss"): [study("1", -70, 4, {"Dry Kolla": 4})]})
    [b] = fuse(payload([("Mulch", -60.0)], confidence="medium"), g)
    assert b["lead_source"] == "model" and b["headline"]["source"] == "model"
    assert b["headline"]["value"] == -60.0 and b["model"]["n_obs_in_zone"] == 4
    assert b["study"]["refs"] == ["study:1"]  # the study still supports


def test_a_zone_study_leads_when_the_model_is_thin() -> None:
    g = Graph({("Mulch", "soil loss"): [study("1", -80, 3, {"Dry Kolla": 3}), study("2", -50, 9, {"Wet Dega": 9})]})
    [b] = fuse(payload([("Mulch", -75.0)], confidence="low"), g)
    assert b["lead_source"] == "study" and b["match"] == "zone"
    assert b["headline"]["source"] == "study" and b["headline"]["ref"] == "study:1"
    assert b["headline"]["value"] == pytest.approx(-80.0)
    assert b["model"]["value"] == -75.0  # shown as support, unchanged


def test_study_fallback_goes_zone_then_altitude_group_then_moisture() -> None:
    group = Graph({("M", "soil loss"): [study("1", -40, 5, {"Moist Kolla": 5}), study("2", -10, 5, {"Dry Dega": 5})]})
    [b] = fuse(payload([("M", -30.0)]), group)
    assert b["match"] == "belt_group" and b["study"]["refs"] == ["study:1"]  # Kolla = lowland
    moisture = Graph({("M", "soil loss"): [study("2", -10, 5, {"Dry Dega": 5})]})
    [b] = fuse(payload([("M", -30.0)]), moisture)
    assert b["match"] == "moisture"
    other = Graph({("M", "soil loss"): [study("3", -10, 5, {"Wet Dega": 5})]})
    [b] = fuse(payload([("M", -30.0)]), other)
    assert b["lead_source"] == "model" and b["study"] is None  # no comparable study: the model stays


def test_several_leading_studies_use_the_median_and_report_counts() -> None:
    g = Graph({("M", "soil loss"): [study(s, e, 2, {"Dry Kolla": 2}) for s, e in (("1", -20), ("2", -60), ("3", -50))]})
    [b] = fuse(payload([("M", -40.0)]), g)
    assert b["study"]["n_studies"] == 3 and b["study"]["n_obs"] == 6
    assert b["headline"]["value"] == pytest.approx(-50.0)


# ------------------------------------------------------------ disagreement
def test_opposite_directions_disagree_and_the_headline_becomes_a_range() -> None:
    g = Graph({("M", "soil loss"): [study("1", +15, 4, {"Dry Kolla": 4})]})
    [b] = fuse(payload([("M", -30.0)]), g)
    assert b["disagreement"] is True
    lo, hi = b["headline"]["range"]
    assert (lo["value"], hi["value"]) == (pytest.approx(-30.0), pytest.approx(15.0))
    assert {lo["source"], hi["source"]} == {"model", "study"}


def test_a_gap_beyond_the_threshold_disagrees_and_within_it_does_not() -> None:
    g = Graph({("M", "soil loss"): [study("1", -80, 4, {"Dry Kolla": 4})]})
    assert fuse(payload([("M", -50.0)]), g)[0]["disagreement"] is True   # 30 points
    assert fuse(payload([("M", -60.0)]), g)[0]["disagreement"] is False  # 20 points
    assert fuse(payload([("M", -60.0)]), g, evidence_disagree_pct=10)[0]["disagreement"] is True


# ---------------------------------------------------------------- ordering
def test_conservative_ordering_stops_a_thin_combination_burying_a_well_studied_practice() -> None:
    # The thin combination has the larger point estimate but rests on one
    # single-observation study (pooled SD); the other has many observations.
    tight = [study(str(i), -55, 12, {"Dry Kolla": 12}) for i in range(5)]
    stats = {(str(i), "Physical SWC", "soil loss"): {"n": 12, "mean": log(0.45), "sd": 0.1} for i in range(5)}
    # As in the P9 mode report: a thin combination at about -70% vs a well-studied practice at about -55%.
    g = Graph({("Combo", "soil loss"): [study("9", -70, 1, {"Dry Kolla": 1})], ("Physical SWC", "soil loss"): tight})
    p = payload([("Combo", -72.0), ("Physical SWC", -50.0)])
    bundles = fuse(p, g, stats)
    assert [b["practice"] for b in fu.order(bundles, "model")] == ["Combo", "Physical SWC"]
    assert [b["practice"] for b in fu.order(bundles, "conservative")] == ["Physical SWC", "Combo"]


def test_the_bound_is_direction_aware() -> None:
    g = Graph({})
    up = fuse(payload([("A", 40.0), ("B", 10.0)], confidence="medium", indicator="yield", direction="increase"), g)
    assert [b["practice"] for b in fu.order(up, "conservative")] == ["A", "B"]
    down = fuse(payload([("A", -40.0), ("B", -10.0)], confidence="medium"), g)
    assert [b["practice"] for b in fu.order(down, "conservative")] == ["A", "B"]


def test_caution_flags_large_increases_only() -> None:
    g = Graph({})
    [inc] = fuse(payload([("A", 95.0)], confidence="medium", indicator="yield", direction="increase"), g)
    [dec] = fuse(payload([("A", -95.0)], confidence="medium"), g)
    assert inc["caution"] is True and dec["caution"] is False


# ---------------------------------------------------------- provenance/rounding
def test_every_number_in_a_bundle_carries_provenance() -> None:
    g = Graph({("M", "soil loss"): [study("1", -80, 3, {"Dry Kolla": 3})]})
    [b] = fuse(payload([("M", -75.0)]), g)
    for obj in (b["headline"], b["model"], b["study"], b["studies"][0]["effect"]):
        assert {"value", "unit", "source", "ref", "display"} <= set(obj)
        assert obj["source"] in {"model", "study"}


FIXTURE = Path(__file__).resolve().parents[2] / "frontend" / "src" / "lib" / "number-format.fixture.json"


@pytest.mark.parametrize("case", json.loads(FIXTURE.read_text(encoding="utf-8")))
def test_display_rounding_matches_the_shared_frontend_fixture(case: dict[str, Any]) -> None:
    assert display_text(case["in"]) == case["out"]


def test_number_objects() -> None:
    assert number(-79.44, "%", "model") == {"value": -79.44, "unit": "%", "source": "model", "ref": None, "display": "-79"}
    assert display_value(-0.04) == 0.0
