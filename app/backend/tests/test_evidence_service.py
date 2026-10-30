"""Evidence sufficiency + knowledge candidates on synthetic graphs (P9).

No chromadb, no rasters, no model: a FakeGraphQuery with hand-written
summaries, fixture passages, and a stub settings object.
"""
from __future__ import annotations

from typing import Any

import pytest

from app.config import Settings
from app.services import evidence_service as ev
from app.services import explain_service as es


@pytest.fixture(autouse=True)
def _hermetic(monkeypatch: pytest.MonkeyPatch) -> None:
    """Never touch the real graph store, the Chroma index or the network."""
    monkeypatch.setattr(es, "get_graph_query", lambda: None)
    monkeypatch.setattr(es, "get_guidance_retriever", lambda: None)

ECWM = "Erosion control and water management"
INDICATORS = ["yield", "biomass yield", "income", "water use efficiency", "SOM content", "soil loss", "runoff"]


def _settings(**overrides: Any) -> Settings:
    return Settings(_env_file=None, openai_api_key="", **overrides)


class FakeGraphQuery:
    """``summaries[(practice, indicator)]`` → evidence_summary payload."""

    def __init__(self, summaries: dict[tuple[str, str], dict[str, Any]], related: dict[str, list[str]] | None = None,
                 records: list[dict[str, Any]] | None = None) -> None:
        self.summaries = summaries
        self.related = related or {}
        self.records = records or []
        self.calls: list[tuple[str, str]] = []

    def evidence_summary(self, practice: str, indicator: str) -> dict[str, Any]:
        self.calls.append((practice, indicator))
        base = {"practice": practice, "indicator": indicator, "found": False, "n_studies": 0, "n_obs": 0,
                "aez_belts": [], "crop_groups": [], "corpus_status": {}, "obs_by_belt": {},
                "belt_counts_exact": True, "studies": []}
        return {**base, **self.summaries.get((practice, indicator), {})}

    def related_practices(self, practice: str, k: int = 5) -> list[dict[str, Any]]:
        return [{"practice": p} for p in self.related.get(practice, [])][:k]

    def similar_context_technologies(self, context, practice=None, k=5, include_synthetic=False):
        return [r for r in self.records if include_synthetic or not r.get("synthetic")][:k]


def summary(n_studies: int, obs_by_belt: dict[str, int], exact: bool = True, studies: list | None = None) -> dict[str, Any]:
    n_obs = sum(obs_by_belt.values())
    return {"found": n_studies > 0, "n_studies": n_studies, "n_obs": n_obs, "aez_belts": sorted(obs_by_belt),
            "obs_by_belt": obs_by_belt if exact else {}, "belt_counts_exact": exact,
            "corpus_status": {"full_text": min(n_studies, 1), "abstract": 0, "none": max(0, n_studies - 1)},
            "studies": studies or [{"study_no": f"ERA_{i}", "era_code": f"X{i:04d}", "title": f"Study {i}", "year": 2010 + i, "doi": None}
                                   for i in range(n_studies)]}


def model(ranked: list[str], belt: str = "Dry Kolla") -> dict[str, Any]:
    return {
        "query": {"lat": 8.38, "lon": 39.37, "practice_family": ECWM, "indicator": "soil loss", "goal_direction": "reduce"},
        "recommendations": [{"practice": p, "effect": "~10% reduction in soil loss"} for p in ranked],
        "details": {"context": {"aez_belt": belt, "Rainfall": 750, "slope": 2.3}, "confidence": "low",
                    "ranked": [{"practice": p, "pct_change": -10.0, "log_ratio": -0.1, "n_evidence": 1} for p in ranked],
                    "n_candidates": len(ranked), "note": "n"},
    }


# ------------------------------------------------------------------ belts
@pytest.mark.parametrize("belt,zone", [
    ("Dry Kolla", "Dry-lowland"), ("Dry Berha", "Dry-lowland"), ("Moist Weyna Dega", "Moist-midland"),
    ("Wet Dega", "Wet-highland"), ("Moist High Dega", "Moist-highland"), ("Wet Wurch", "Wet-highland"),
    ("Dry Weyna Dega", "Dry-midland"),
])
def test_zone_of_groups_the_belts(belt, zone):
    assert ev.zone_of(belt) == zone


def test_zone_of_never_guesses():
    for bad in (None, "", "Kolla", "Humid Dega", 3, "Dry Nowhere"):
        assert ev.zone_of(bad) is None


def test_belt_group_table_covers_every_lookup_belt():
    import csv
    from pathlib import Path

    rows = list(csv.DictReader((Path(__file__).resolve().parents[1] / "aez_belt_lookup.csv").open(encoding="utf-8")))
    belts = {r["Agro_zone"] for r in rows}
    assert belts and all(ev.zone_of(b) for b in belts), [b for b in belts if not ev.zone_of(b)]


# ------------------------------------------------------- candidate counts
def test_candidate_counts_use_exact_per_belt_rows():
    gq = FakeGraphQuery({("Mulch", "soil loss"): summary(4, {"Dry Kolla": 6, "Moist Kolla": 3, "Wet Dega": 5})})
    row = ev.candidate_counts(gq, "Mulch", "soil loss", "Dry Berha")
    assert (row["n_studies"], row["n_obs"]) == (4, 14)
    assert row["n_obs_in_belt"] == 0           # Dry Berha itself has none
    assert row["n_obs_in_zone"] == 6           # Dry Kolla is the same Dry-lowland zone
    assert row["belt_counts_exact"] is True


def test_candidate_counts_degrade_to_presence_on_a_pre_p9_store():
    gq = FakeGraphQuery({("Mulch", "soil loss"): summary(2, {"Dry Kolla": 9}, exact=False)})
    row = ev.candidate_counts(gq, "Mulch", "soil loss", "Dry Kolla")
    assert row["belt_counts_exact"] is False
    assert row["n_obs_in_belt"] == 1 and row["n_obs_in_zone"] == 1  # presence, never a guessed count
    assert ev.candidate_counts(gq, "Mulch", "soil loss", "Wet Dega")["n_obs_in_zone"] == 0


# ------------------------------------------------------------- mode rules
LIMITS = {"min_studies": 3, "min_obs": 10, "min_obs_in_zone": 1}


def row(practice, n_studies, n_obs, in_zone):
    return {"practice": practice, "n_studies": n_studies, "n_obs": n_obs, "n_obs_in_belt": 0, "n_obs_in_zone": in_zone}


def test_model_led_needs_strong_evidence_and_zone_coverage():
    mode, reasons = ev.decide_mode([row("A", 3, 10, 1), row("B", 1, 2, 0)], engine_error=None, user_zone="Dry-lowland", limits=LIMITS)
    assert mode == ev.MODEL_LED
    assert [r["key"] for r in reasons] == ["mode.reason.strong_evidence", "mode.reason.in_zone"]
    assert reasons[0]["params"] == {"practice": "A", "n_studies": 3, "n_obs": 10}


def test_strong_evidence_from_other_zones_only_is_hybrid():
    mode, reasons = ev.decide_mode([row("A", 5, 40, 0)], engine_error=None, user_zone="Wet-highland", limits=LIMITS)
    assert mode == ev.HYBRID
    assert [r["key"] for r in reasons] == ["mode.reason.strong_evidence", "mode.reason.other_zones_only"]


def test_thin_evidence_in_zone_is_hybrid():
    mode, reasons = ev.decide_mode([row("A", 2, 9, 4)], engine_error=None, user_zone="Dry-lowland", limits=LIMITS)
    assert mode == ev.HYBRID
    assert reasons[0]["key"] == "mode.reason.thin_evidence"
    assert reasons[0]["params"]["min_studies"] == 3 and reasons[1]["key"] == "mode.reason.in_zone"


def test_zone_coverage_counts_any_top3_practice_not_only_the_strong_one():
    rows = [row("A", 4, 12, 0), row("B", 1, 1, 2), row("C", 0, 0, 0)]
    assert ev.decide_mode(rows, engine_error=None, user_zone="Dry-lowland", limits=LIMITS)[0] == ev.MODEL_LED


def test_only_the_top3_count():
    rows = [row("A", 1, 1, 0), row("B", 1, 1, 0), row("C", 1, 1, 0), row("D", 9, 99, 9)]
    assert ev.decide_mode(rows[:3], engine_error=None, user_zone="Dry-lowland", limits=LIMITS)[0] == ev.HYBRID


def test_engine_errors_are_knowledge_led():
    assert ev.decide_mode([], engine_error="no_evidence", user_zone=None, limits=LIMITS) == (
        ev.KNOWLEDGE_LED, [{"key": "mode.reason.engine_no_evidence", "params": {}}])
    assert ev.decide_mode([], engine_error="unsupported", user_zone=None, limits=LIMITS)[0] == ev.KNOWLEDGE_LED


def test_no_studies_at_all_is_knowledge_led():
    assert ev.decide_mode([row("A", 0, 0, 0)], engine_error=None, user_zone="Dry-lowland", limits=LIMITS)[0] == ev.KNOWLEDGE_LED


def test_unknown_zone_is_reported_not_guessed():
    mode, reasons = ev.decide_mode([row("A", 3, 10, 0)], engine_error=None, user_zone=None, limits=LIMITS)
    assert mode == ev.HYBRID and reasons[-1]["key"] == "mode.reason.zone_unknown"


def test_graph_unavailable_keeps_the_model_ranking_with_a_reason():
    mode, reasons = ev.decide_mode([], engine_error=None, user_zone="Dry-lowland", limits=LIMITS, graph_available=False)
    assert mode == ev.MODEL_LED and reasons == [{"key": "mode.reason.graph_unavailable", "params": {}}]


def test_thresholds_are_config_driven():
    s = _settings(EVIDENCE_MIN_STUDIES=5, EVIDENCE_MIN_OBS=50, EVIDENCE_MIN_OBS_IN_ZONE=2)
    assert ev.thresholds(s) == {"min_studies": 5, "min_obs": 50, "min_obs_in_zone": 2}
    gq = FakeGraphQuery({("A", "soil loss"): summary(3, {"Dry Kolla": 10})})
    suff = ev.evidence_sufficiency(model(["A"]), ECWM, "soil loss", {"aez_belt": "Dry Kolla"}, gq, settings=s)
    assert suff["mode"] == ev.HYBRID  # 3/10 is strong under defaults but not under 5/50


def test_evidence_sufficiency_marks_top3_and_reports_belt_and_zone():
    gq = FakeGraphQuery({(p, "soil loss"): summary(3, {"Dry Kolla": 10}) for p in "ABCD"})
    suff = ev.evidence_sufficiency(model(list("ABCD")), ECWM, "soil loss", {"aez_belt": "Dry Kolla"}, gq, settings=_settings())
    assert suff["mode"] == ev.MODEL_LED
    assert [c["in_top3"] for c in suff["candidates"]] == [True, True, True, False]
    assert suff["user_belt"] == "Dry Kolla" and suff["user_zone"] == "Dry-lowland"
    assert set(suff["candidates"][0]) >= {"n_studies", "n_obs", "n_obs_in_belt", "n_obs_in_zone", "corpus_status"}


# ------------------------------------------------------ knowledge candidates
class FakeGuidance:
    def __init__(self, passages): self.passages = passages
    def retrieve(self, query: str, k: int = 8): return self.passages[:k]


GOOD = ("Farmers in the highlands build soil bunds along the contour and stabilise them with grass strips; "
        "mulch between rows keeps moisture. Maintain bunds after each rainy season and plant trees on the bund. ") * 3
TABLE = "Table 3 Yield 2012 2013 2014 1.2 1.4 1.1 2.3 2.1 2.6 0.9 1.1 1.0 12.5 13.1 11.9 14.0 mulch 45 51 48 50 | 3 | 4 |" * 4


def passages():
    return [
        {"chunk_id": "G_d1_000", "tier": "guidance", "title": "Bund manual", "year": 2021, "url": "https://g/1", "text": GOOD},
        {"chunk_id": "G_d1_001", "tier": "guidance", "title": "Bund manual", "year": 2021, "url": "https://g/1", "text": GOOD},
        {"chunk_id": "G_d2_000", "tier": "guidance", "title": "Mulch leaflet", "year": 2019, "url": "https://g/2", "text": "Mulch the field with crop residue. " * 20},
        {"chunk_id": "G_d3_000", "tier": "guidance", "title": "A table", "year": 2018, "url": "https://g/3", "text": TABLE},
        {"chunk_id": "G_d4_000", "tier": "guidance", "title": "Compost guide", "year": 2017, "url": "https://g/4", "text": "Make compost from manure and residues. " * 20},
    ]


POOL = ["Mulch", "Mulch-Water Harvesting", "Physical SWC Measures", "Deficit Irrigation"]


def test_guidance_candidates_filter_quality_and_stay_within_the_family():
    allowed = {"Mulch", "Water Harvesting", "Physical SWC Measures", "Deficit Irrigation"}
    cands, funnel = ev.guidance_candidates(passages(), allowed, min_quality=0.55)
    assert funnel == {"retrieved": 5, "kept": 4, "with_component": 3}  # the table is dropped; compost is off-family
    assert set(cands) == {"Mulch", "Physical SWC Measures"}
    mulch = cands["Mulch"]
    assert mulch.n_passages == 3 and mulch.documents == {"doc:https://g/1", "doc:https://g/2"}
    assert len(mulch.citations) == 2  # one per document


def test_graph_candidates_report_other_objectives_with_study_citations():
    gq = FakeGraphQuery({("Mulch", "yield"): summary(5, {"Dry Kolla": 20}), ("Mulch", "soil loss"): summary(1, {"Dry Kolla": 1}),
                         ("Deficit Irrigation", "water use efficiency"): summary(2, {"Dry Kolla": 4})})
    cands = ev.graph_other_objective_candidates(gq, POOL, "soil loss", INDICATORS)
    assert cands["Mulch"].other_objectives == {"yield": 5}          # soil loss itself is excluded
    assert cands["Deficit Irrigation"].other_objectives == {"water use efficiency": 2}
    assert all(c["tier"] == "evidence" for c in cands["Mulch"].citations)
    # Mulch-Water Harvesting has no other-objective evidence here, so its
    # second component is NOT proposed: nothing is inferred beyond the rows.
    assert "Water Harvesting" not in cands and "Physical SWC Measures" not in cands


def test_knowledge_candidates_rank_by_support_dedupe_cap_and_cite():
    gq = FakeGraphQuery({("Mulch", "yield"): summary(5, {"Dry Kolla": 20}), ("Deficit Irrigation", "water use efficiency"): summary(2, {"Dry Kolla": 4})})
    cands, funnel = ev.knowledge_candidates(
        practice_family=ECWM, indicator="soil loss", context={"aez_belt": "Dry Kolla", "Rainfall": 700, "slope": 3},
        pool=POOL, indicators=INDICATORS, graph_query=gq, guidance_retriever=FakeGuidance(passages()),
        settings=_settings(KNOWLEDGE_CANDIDATES_MAX=2), language="en",
    )
    # Support order: distinct sources, then distinct documents, then passages —
    # Mulch (2 sources) > Deficit Irrigation (1 source, 2 studies) > bunds (1 source, 1 document, 2 passages).
    assert [c["key"] for c in cands] == ["Mulch", "Deficit Irrigation"]
    three, _ = ev.knowledge_candidates(
        practice_family=ECWM, indicator="soil loss", context={"aez_belt": "Dry Kolla", "Rainfall": 700, "slope": 3},
        pool=POOL, indicators=INDICATORS, graph_query=gq, guidance_retriever=FakeGuidance(passages()),
        settings=_settings(KNOWLEDGE_CANDIDATES_MAX=5), language="en",
    )
    assert [c["key"] for c in three] == ["Mulch", "Deficit Irrigation", "Physical SWC Measures"]
    mulch = cands[0]
    assert set(mulch["sources"]) == {ev.SOURCE_OTHER_OBJECTIVES, ev.SOURCE_GUIDANCE}
    assert mulch["practices"] == ["Mulch", "Mulch-Water Harvesting"]
    assert mulch["support"]["n_guidance_documents"] == 2 and mulch["support"]["other_objectives"] == {"yield": 5}
    assert all(c.get("ref") for c in mulch["citations"])
    assert {c["ref"] for c in mulch["citations"]} >= {"1", "G1", "G2"}
    assert "2 guidance documents" in mulch["rationale_text"] and "yield (5 studies)" in mulch["rationale_text"]
    assert ev.rationale_numbers_are_counts(mulch)
    assert funnel["guidance"]["retrieved"] == 5 and len(cands) == 2


def test_candidate_without_any_citation_is_dropped():
    gq = FakeGraphQuery({("Mulch", "yield"): {**summary(2, {"Dry Kolla": 2}), "studies": []}})
    cands, _ = ev.knowledge_candidates(practice_family=ECWM, indicator="soil loss", context={}, pool=["Mulch"],
                                       indicators=INDICATORS, graph_query=gq, guidance_retriever=None, settings=_settings())
    assert cands == []


def test_rationale_is_localised_and_numbers_are_counts_only():
    gq = FakeGraphQuery({("Mulch", "yield"): summary(5, {"Dry Kolla": 20})})
    for lang, script in (("am", "[ሀ-፿]"), ("om", "[a-z]")):
        cands, _ = ev.knowledge_candidates(practice_family=ECWM, indicator="soil loss", context={}, pool=["Mulch"],
                                           indicators=INDICATORS, graph_query=gq, guidance_retriever=None, settings=_settings(), language=lang)
        import re
        assert re.search(script, cands[0]["rationale_text"]) and "5" in cands[0]["rationale_text"]
        assert ev.rationale_numbers_are_counts(cands[0])


def test_practice_records_are_wired_and_empty_without_wocat():
    gq = FakeGraphQuery({}, records=[])
    assert ev.practice_record_candidates(gq, {"Rainfall": 700}) == {}
    gq2 = FakeGraphQuery({}, records=[{"wocat_id": "T_1", "title": "Stone bunds", "country": "Ethiopia", "url": "https://w/1", "licence": "CC BY-NC-SA 4.0"},
                                      {"wocat_id": "SYN", "title": "fake", "synthetic": True}])
    cands = ev.practice_record_candidates(gq2, {"Rainfall": 700})
    assert list(cands) == ["record:T_1"] and cands["record:T_1"].citations[0]["tier"] == "practice"
    out, _ = ev.knowledge_candidates(practice_family=ECWM, indicator="soil loss", context={}, pool=POOL, indicators=INDICATORS,
                                     graph_query=gq2, guidance_retriever=None, settings=_settings(), language="en")
    assert out[0]["key"] == "record:T_1" and out[0]["citations"][0]["ref"] == "W1" and "Ethiopia" in out[0]["rationale_text"]


def test_dataset_only_studies_are_cited_by_dataset_id_and_uncitable_rows_are_dropped():
    """A study outside the ERA corpus has no code and no title but a dataset id:
    it gets its own number. A citation with no identity at all is dropped, and a
    candidate left without citations disappears (doctrine 2)."""
    studies = [
        {"study_no": "101", "era_code": None, "title": None, "year": None, "doi": None},
        {"study_no": "102", "era_code": None, "title": None, "year": None, "doi": None},
    ]
    gq = FakeGraphQuery(
        summaries={
            ("Mulch", "yield"): summary(2, {"Dry Kolla": 4}, studies=studies),
            ("Mulch", "soil loss"): summary(0, {}),
            ("Physical SWC Measures", "runoff"): summary(1, {"Dry Dega": 2},
                                                          studies=[{"study_no": None, "era_code": None, "title": None, "year": None, "doi": None}]),
        },
        related={ECWM: ["Mulch", "Physical SWC Measures"]},
    )
    cands, _ = ev.knowledge_candidates(
        practice_family=ECWM, indicator="soil loss", context={"aez_belt": "Dry Kolla", "Rainfall": 700, "slope": 3},
        pool=POOL, indicators=INDICATORS, graph_query=gq, guidance_retriever=FakeGuidance([]),
        settings=_settings(), language="en",
    )
    keys = [c["key"] for c in cands]
    assert "Mulch" in keys and "Physical SWC Measures" not in keys
    mulch = next(c for c in cands if c["key"] == "Mulch")
    assert [(c["ref"], c["study_no"]) for c in mulch["citations"]] == [("1", "101"), ("2", "102")]
    assert all(c["era_code"] is None and c["title"] is None for c in mulch["citations"])
