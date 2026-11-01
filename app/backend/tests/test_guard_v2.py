"""Numeric guard v2, the two registers and the citation registry (U9 A4/A5/B4).

Runs anywhere: synthetic recommendation, chunks and graph; no key, no index.
"""
from __future__ import annotations

import math
import re
from typing import Any

import pytest

from app.config import Settings
from app.services import explain_service as es
from app.services import fusion_service as fu

ALLOWED: dict[str, set[float]] = {
    "model": es._number_variants(-42.0) | es._number_variants(42),
    "study": es._number_variants(-80.0) | es._number_variants(80),
    "context": es._number_variants(1024.0) | es._number_variants(8.0),
    "count": es._number_variants(14.0),
}
PASSAGES = {"1": es._number_variants(37.0), "2": es._number_variants(61.0)}


def guard(text: str) -> dict[str, Any]:
    return es.guard_v2(text, ALLOWED, PASSAGES)


def test_a_passage_number_stands_only_in_the_sentence_that_cites_that_passage() -> None:
    ok = guard("Mulch cut runoff by 37% in the Tigray trial [1].")
    assert ok["removed"] == 0 and ok["numbers"][0]["source"] == "passage" and ok["numbers"][0]["ref"] == "1"
    wrong_ref = guard("Mulch cut runoff by 37% in the Tigray trial [2]. Bunds help [1].")
    assert wrong_ref["removed"] == 1 and "37" not in wrong_ref["text"]
    uncited = guard("Mulch cut runoff by 37%. Bunds help [1].")
    assert uncited["removed"] == 1


def test_an_unsourced_number_removes_its_sentence_and_all_removed_is_ungrounded() -> None:
    out = guard("Yields double, about 97% more [1]. Mulch keeps soil in place [1].")
    assert out["removed"] == 1 and "97" not in out["text"] and out["grounded"] is True
    assert guard("Yields rise 97% [1].")["grounded"] is False


def test_model_study_context_and_counts_are_allowed_anywhere_with_provenance() -> None:
    out = guard("The model expects about 42% less soil loss; field studies found about 80% less, from 14 studies [1].")
    assert out["removed"] == 0
    assert [n["source"] for n in out["numbers"]] == ["model", "study", "count"]
    assert all({"value", "unit", "source", "ref", "display"} <= set(n) for n in out["numbers"])
    assert out["numbers"][0]["unit"] == "%"


def test_no_study_marker_on_a_sentence_that_only_states_the_users_context() -> None:
    out = guard("Your area gets an annual average of 1024 mm [1]. Mulch helps [1].")
    first = out["text"].split(". ")[0]
    assert "1024 mm" in first and "[1]" not in first
    assert out["numbers"][0]["source"] == "context" and out["numbers"][0]["unit"] == "mm"


def test_sub_labels_are_normalised_and_identifiers_are_not_numbers() -> None:
    out = guard("Trial NN0123 found 37% less runoff [1a], see also [1b].")
    assert "[1a]" not in out["text"] and "[1]" in out["text"] and out["removed"] == 0


# ------------------------------------------------------------- end to end
class Retriever:
    def __init__(self, chunks: list[dict[str, Any]]) -> None:
        self.chunks = chunks

    def retrieve_for_recommendation(self, rec: dict[str, Any], k: int = 8) -> list[dict[str, Any]]:
        return self.chunks[:k]


class Graph:
    def evidence_summary(self, practice: str, indicator: str) -> dict[str, Any]:
        st = {"study_no": "S1", "era_code": "NN0123", "title": "Mulching effects on erosion", "year": 2019,
              "doi": None, "mean_log_rr": math.log(0.2), "n_obs": 4, "share_positive": 0.0,
              "obs_by_belt": {"Dry Kolla": 4}, "aez_belts": ["Dry Kolla"], "corpus_status": "full_text"}
        other = {**st, "study_no": "S2", "era_code": "NN9999", "title": "Another study", "mean_log_rr": math.log(0.3)}
        studies = [st, other] if practice == "Mulching" else []
        return {"practice": practice, "indicator": indicator, "found": bool(studies), "n_studies": len(studies),
                "n_obs": 8 if studies else 0, "aez_belts": ["Dry Kolla"], "crop_groups": [], "studies": studies,
                "corpus_status": {"full_text": 1}, "obs_by_belt": {"Dry Kolla": 8}, "belt_counts_exact": True}


REC = {
    "query": {"lat": 8.38, "lon": 39.37, "practice_family": "Erosion control and water management",
              "indicator": "soil loss", "crop_type": None, "goal_direction": "reduce"},
    "recommendations": [{"practice": "Mulching", "effect": "~70% reduction in soil loss"}],
    "details": {"context": {"aez_belt": "Dry Kolla", "Rainfall": 1024.0}, "confidence": "low",
                "ranked": [{"practice": "Mulching", "pct_change": -70.0, "log_ratio": -1.204, "n_evidence": 8}]},
}
CHUNKS = [{"era_code": "NN0123", "title": "Mulching effects on erosion", "year": 2019, "text": "Mulch cut soil loss by 64%.",
           "for_practice": "Mulching", "tier": "evidence"}]


@pytest.fixture()
def no_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(es, "get_settings", lambda: Settings(_env_file=None, openai_api_key=""))
    monkeypatch.setattr(fu, "_dataset_study_stats", lambda: ({}, {"soil loss": 0.6}))
    monkeypatch.setattr(fu, "_model_rmse", lambda: {"soil loss": 0.5})


@pytest.mark.parametrize("language", ["en", "am", "om"])
def test_explain_returns_a_plain_summary_and_a_labelled_cited_evidence_register(no_key: None, language: str) -> None:
    out = es.explain(REC, retriever=Retriever(CHUNKS), graph_query=Graph(), language=language)
    # Plain register: no citation markers, only the headline value (study-led: the median of the two
    # studies' log ratios, -75.5%, shown with the shared rounding rule as 76).
    assert out["summary"] and not re.search(r"\[[GW]?\d+\]", out["summary"])
    assert set(re.findall(r"\d+(?:\.\d+)?", out["summary"])) <= {"76"}
    # Evidence register: labelled study lines with registry numbers; every number has provenance.
    assert "[1]" in out["explanation"] and "[2]" in out["explanation"]
    assert out["numbers"] and all(n["source"] in {"model", "study", "context", "count", "passage"} for n in out["numbers"])


def test_one_registry_numbers_passages_and_study_effects_without_collisions(no_key: None) -> None:
    out = es.explain(REC, retriever=Retriever(CHUNKS), graph_query=Graph())
    refs = [c["ref"] for c in out["citations"]]
    assert len(refs) == len(set(refs))
    by_ref = {c["ref"]: c for c in out["citations"]}
    assert by_ref["1"]["era_code"] == "NN0123"  # the passage's study keeps its number
    assert by_ref["2"]["era_code"] == "NN9999"  # the other study gets the next one
