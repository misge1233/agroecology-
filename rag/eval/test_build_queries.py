"""Unit tests for the P3 evaluation harness' pure functions.

Run from rag/eval (or with rag/eval on the path):
    cd rag/eval && python -m pytest test_build_queries.py -q
No network, no chromadb, no index — synthetic rows only. ``build_queries``
imports ``rag.retrieve`` for ``build_query_text``, which needs ``requests``
installed (it is in rag/requirements.txt and the backend venv).
"""
from __future__ import annotations

from typing import Any

import re

import build_queries as bq
import eval_faithfulness as ef
import eval_retrieval as er

_NUM_RE = re.compile(r"\d+(?:\.\d+)?")  # mirror of the service's token regex


# ------------------------------------------------------------------ fixtures
def make_row(
    study: str = "ERA_AA0001",
    family: str = "Erosion control and water management",
    indicator: str = "soil loss",
    practice: str = "Physical SWC measures",
    source: str = "ERA",
    **extra: Any,
) -> dict[str, str]:
    row = {
        "source": source,
        "Study_No_": study,
        "practice_family": family,
        "Indicator": indicator,
        "CSA_practices": practice,
        "latitude": "8.38",
        "longitude": "39.37",
        "Rainfall": "812.5",
        "slope": "8.0",
        "aez_belt": "Moist Dega",
        "crop_type": "Maize",
    }
    row.update(extra)
    return row


# ------------------------------------------------------------ label building
def test_strip_era_prefix():
    assert bq.strip_era_prefix("ERA_NN0206") == "NN0206"
    assert bq.strip_era_prefix("CSA_6") == "CSA_6"  # non-ERA ids untouched


def test_relevant_studies_matches_family_indicator_practice():
    rows = [
        make_row(study="ERA_AA0001"),
        make_row(study="ERA_BB0002"),
        make_row(study="ERA_CC0003", practice="Mulch"),          # other practice
        make_row(study="ERA_DD0004", indicator="yield"),         # other indicator
        make_row(study="ERA_EE0005", family="Integrated soil fertility management"),
        make_row(study="CSA_6", source="CSA"),                   # not ERA-linkable
    ]
    corpus = {"AA0001", "BB0002", "CC0003", "DD0004", "EE0005"}
    got = bq.relevant_studies(
        rows, "Erosion control and water management", "soil loss",
        "Physical SWC measures", corpus,
    )
    assert got == ["AA0001", "BB0002"]


def test_relevant_studies_without_practice_is_family_level():
    rows = [make_row(study="ERA_AA0001"), make_row(study="ERA_CC0003", practice="Mulch")]
    got = bq.relevant_studies(
        rows, "Erosion control and water management", "soil loss", None,
        {"AA0001", "CC0003"},
    )
    assert got == ["AA0001", "CC0003"]


def test_relevant_studies_filters_to_corpus_backed():
    rows = [make_row(study="ERA_AA0001"), make_row(study="ERA_BB0002")]
    assert bq.relevant_studies(
        rows, "Erosion control and water management", "soil loss",
        "Physical SWC measures", {"BB0002"},
    ) == ["BB0002"]


# --------------------------------------------------------- scenario sampling
def test_build_scenarios_skips_zero_corpus_and_counts():
    # AA0001's practice has no corpus-backed study -> its scenario is skipped;
    # BB0002 (Mulch) is corpus-backed -> one scenario survives.
    rows = [
        make_row(study="ERA_AA0001", practice="Physical SWC measures"),
        make_row(study="ERA_BB0002", practice="Mulch"),
    ]
    scenarios, report = bq.build_scenarios(rows, {"BB0002"}, n_target=4, seed=1)
    assert [s["practice"] for s in scenarios] == ["Mulch"]
    assert report["n_skipped_no_relevant_in_corpus"] == 1
    assert scenarios[0]["relevant_era_codes"] == ["BB0002"]
    assert scenarios[0]["relevant_era_codes_family_level"] == ["BB0002"]


def test_build_scenarios_stratified_and_deterministic():
    rows = []
    for fam in ("F1", "F2"):
        for ind in ("I1", "I2"):
            for i in range(5):
                rows.append(make_row(
                    study=f"ERA_{fam}{ind}{i:02d}", family=fam,
                    indicator=ind, practice="P",
                ))
    corpus = {bq.strip_era_prefix(r["Study_No_"]) for r in rows}
    a, report = bq.build_scenarios(rows, corpus, n_target=8, seed=42)
    b, _ = bq.build_scenarios(rows, corpus, n_target=8, seed=42)
    assert [s["anchor_study"] for s in a] == [s["anchor_study"] for s in b]
    assert report["per_cell_quota"] == 2  # 8 target / 4 cells
    cells = {(s["practice_family"], s["indicator"]) for s in a}
    assert len(cells) == 4 and len(a) == 8
    assert [s["scenario_id"] for s in a] == [f"S{i:03d}" for i in range(1, 9)]


def test_recommendation_stub_and_query_text():
    scenarios, _ = bq.build_scenarios([make_row()], {"AA0001"}, n_target=1, seed=0)
    (s,) = scenarios
    rec = s["recommendation"]
    assert rec["query"]["practice_family"] == "Erosion control and water management"
    assert rec["recommendations"] == [{"practice": "Physical SWC measures"}]
    assert rec["details"]["context"]["aez_belt"] == "Moist Dega"
    # composed by the REAL rag.retrieve.build_query_text
    q = s["query_text"]
    for fragment in ("Physical SWC measures", "effect on soil loss",
                     "Ethiopia", "Moist Dega", "Maize", "812 mm", "8% slope"):
        assert fragment in q, (fragment, q)


# ---------------------------------------------------------- retrieval metrics
def test_success_at_k():
    ranked = ["A", "B", "A", "C", "D"]
    assert er.success_at_k(ranked, {"C", "Z"}, 4) == 1.0  # C at rank 4
    assert er.success_at_k(ranked, {"C", "Z"}, 3) == 0.0  # nothing in top-3
    assert er.success_at_k(ranked, {"A"}, 1) == 1.0
    assert er.success_at_k(ranked, {"Q"}, 5) == 0.0       # never retrieved
    assert er.success_at_k(ranked, set(), 4) == 0.0       # empty labels -> 0
    assert er.success_at_k([], {"A"}, 4) == 0.0           # nothing retrieved


def test_recall_and_mrr():
    ranked = ["A", "B", "A", "C", "D"]
    relevant = {"C", "Z"}
    assert er.recall_at_k(ranked, relevant, 4) == 0.5   # C within top-4
    assert er.recall_at_k(ranked, relevant, 2) == 0.0
    assert er.mrr(ranked, relevant) == 0.25             # first hit at rank 4
    assert er.mrr(ranked, {"Q"}) == 0.0
    assert er.recall_at_k(ranked, set(), 4) == 0.0      # empty labels -> 0


def test_score_and_aggregate():
    scenario = {
        "relevant_era_codes": ["B"],
        "relevant_era_codes_family_level": ["A", "B"],
    }
    m = er.score_scenario(["A", "B", "C"], scenario)
    assert m["recall@4"] == 1.0 and m["mrr"] == 0.5
    assert m["recall@4_family"] == 1.0 and m["mrr_family"] == 1.0
    assert m["success@4"] == 1.0 and m["success@4_family"] == 1.0
    agg = er.aggregate([
        {"practice_family": "F1", "indicator": "I1", "metrics": m},
        {"practice_family": "F1", "indicator": "I2",
         "metrics": {k: 0.0 for k in m}},
    ])
    assert agg["n_scenarios"] == 2
    assert agg["overall"]["mrr"] == 0.25
    assert agg["per_family"]["F1"]["n"] == 2
    assert agg["per_indicator"]["I1"]["mrr"] == 0.5


# ------------------------------------------------- faithfulness (two-tier)
def test_faithfulness_strips_both_citation_marker_kinds():
    assert ef.digit_tokens("cut 42.5% [1] [G12]", _NUM_RE) == ["42.5"]
    assert ef.digit_tokens("[3][G4]", _NUM_RE) == []


def test_faithfulness_guidance_marker_indices():
    assert ef.cited_guidance_indices("see [G1] and [G3]", 2) == [0]  # G3 invalid
    assert ef.cited_guidance_indices("see [1] only", 2) == []


def test_audit_sentence_accepts_guidance_quoted_numbers():
    # eval_faithfulness put BACKEND_DIR on sys.path at import time.
    from app.services import explain_service as es

    rec = {"recommendations": [{"practice": "Soil bunds"}]}
    chunks = [{"era_code": "NN0001", "text": "bunds reduced runoff"}]
    guidance = [{"chunk_id": "G_doc1_000", "era_code": None, "tier": "guidance",
                 "text": "space bunds 15 m apart on slopes above 12 percent"}]
    sentence = "Space bunds 15 m apart [G1]."
    with_g = ef.audit_sentence(sentence, rec, chunks, es, guidance_chunks=guidance)
    assert with_g["auto_verdict"] == "pass"
    assert with_g["cite_markers"] == "G1"
    assert with_g["cited_support"] == "yes"
    without_g = ef.audit_sentence(sentence, rec, chunks, es)
    assert without_g["auto_verdict"] == "fail_digits"
    assert without_g["ungrounded_digits"] == "15"
