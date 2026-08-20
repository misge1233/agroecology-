"""Unit tests for the grounded /explain service layer (Phase P2b).

These tests run WITHOUT rasterio, chromadb, the Chroma index, or network:
they import only ``app.config`` and ``app.services.explain_service`` (which
never pulls ``recommend.py``) and inject a fake retriever.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from app.config import Settings
from app.services import explain_service as es


# ------------------------------------------------------------------ fixtures
def make_recommendation() -> dict[str, Any]:
    """A realistic two-tier engine payload (shape of recommend.py output)."""
    return {
        "query": {
            "lat": 8.38,
            "lon": 39.37,
            "practice_family": "Erosion control and water management",
            "indicator": "soil loss",
            "crop_type": None,
            "goal_direction": "decrease",
        },
        "recommendations": [
            {"practice": "Mulching", "effect": "~42% decrease in soil loss"},
            {"practice": "Soil bunds", "effect": "~35% decrease in soil loss"},
        ],
        "details": {
            "context": {"aez_belt": "Moist Dega", "Rainfall": 812.5, "slope": 8.0},
            "confidence": "medium",
            "ranked": [
                {"practice": "Mulching", "pct_change": -42.3157, "log_ratio": -0.55, "n_evidence": 14},
                {"practice": "Soil bunds", "pct_change": -35.02, "log_ratio": -0.43, "n_evidence": 21},
            ],
            "n_candidates": 12,
            "note": "ranking signal, not exact percentages",
        },
    }


def make_chunks() -> list[dict[str, Any]]:
    return [
        {
            "chunk_id": "c1",
            "era_code": "NN0123",
            "doi": "10.1000/xyz1",
            "title": "Mulching effects on erosion in the Ethiopian highlands",
            "year": "2019",
            "journal": "Soil & Tillage Research",
            "source": "era",
            "text": "Mulch cover reduced soil loss by 34% on cultivated slopes. " + "x" * 300,
            "for_practice": "Mulching",
        },
        {
            "chunk_id": "c2",
            "era_code": "NN0456",
            "doi": "10.1000/xyz2",
            "title": "Soil bunds under smallholder conditions",
            "year": 2015,
            "journal": "Catena",
            "source": "era",
            "text": "Bund construction on 8% slopes retained runoff and sediment.",
            "for_practice": "Soil bunds",
        },
    ]


class FakeRetriever:
    def __init__(self, chunks: list[dict[str, Any]]):
        self.chunks = chunks
        self.calls: list[int] = []

    def retrieve_for_recommendation(self, recommendation: dict[str, Any], k: int = 8):
        self.calls.append(k)
        return self.chunks[:k]


def make_settings(**overrides: Any) -> Settings:
    """Settings decoupled from backend/.env and the process env.

    ``rag_index_dir`` / ``rag_chunks_path`` carry validation aliases
    (RAG_INDEX_DIR / RAG_CHUNKS_PATH), so init kwargs must use those names.
    """
    defaults: dict[str, Any] = {"openai_api_key": ""}
    if "rag_index_dir" in overrides:
        defaults["RAG_INDEX_DIR"] = overrides.pop("rag_index_dir")
    if "rag_chunks_path" in overrides:
        defaults["RAG_CHUNKS_PATH"] = overrides.pop("rag_chunks_path")
    defaults.update(overrides)
    return Settings(_env_file=None, **defaults)


@pytest.fixture()
def no_key_settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    settings = make_settings()
    monkeypatch.setattr(es, "get_settings", lambda: settings)
    return settings


# ----------------------------------------------------------- numeric guardrail
def test_guardrail_allows_numbers_from_recommendation_json():
    rec, chunks = make_recommendation(), make_chunks()
    text = "Mulching cuts soil loss by ~42% here; the model saw 14 studies."
    assert es.numbers_are_grounded(text, rec, chunks) is True


def test_guardrail_allows_rounded_forms_of_json_numbers():
    rec, chunks = make_recommendation(), make_chunks()
    # 42.3157 in details -> 42.3 and 42 both allowed; 812.5 mm -> 812 allowed.
    assert es.numbers_are_grounded("a 42.3% reduction at 812 mm rainfall", rec, chunks)


def test_guardrail_allows_numbers_quoted_from_chunk_text():
    rec, chunks = make_recommendation(), make_chunks()
    assert es.numbers_are_grounded("one study reported a 34% reduction", rec, chunks)


def test_guardrail_allows_small_list_integers_and_citation_markers():
    rec, chunks = make_recommendation(), make_chunks()
    # 3 (0-10 list position) and the [19] citation marker must not trip it.
    assert es.numbers_are_grounded("the top 3 options [19] agree", rec, chunks)


@pytest.mark.parametrize("text", ["soil loss drops 47%", "yields rose 99.9 percent", "apply 250 kg/ha of urea"])
def test_guardrail_rejects_invented_numbers(text: str):
    rec, chunks = make_recommendation(), make_chunks()
    assert es.numbers_are_grounded(text, rec, chunks) is False


# ------------------------------------------------------------------- fallback
def test_fallback_text_uses_effect_strings_and_citations():
    rec, chunks = make_recommendation(), make_chunks()
    text = es.build_fallback_text(rec, chunks)
    assert "~42% decrease in soil loss" in text
    assert "~35% decrease in soil loss" in text
    assert "supported by evidence from" in text
    # Practice-matched citations (title + era_code), not cross-wired.
    assert "Mulching effects on erosion" in text and "NN0123" in text
    assert "Soil bunds under smallholder conditions" in text and "NN0456" in text
    # Deterministic template never invents numbers.
    assert es.numbers_are_grounded(text, rec, chunks) is True


def test_fallback_text_without_recommendations_makes_no_claims():
    rec = make_recommendation()
    rec["recommendations"] = []
    text = es.build_fallback_text(rec, make_chunks())
    assert "No practices were recommended" in text


# ------------------------------------------------------------------ citations
def test_shape_citations_maps_provenance_and_truncates_snippet():
    citations = es.shape_citations(make_chunks())
    assert len(citations) == 2
    first = citations[0]
    assert first["era_code"] == "NN0123"
    assert first["doi"] == "10.1000/xyz1"
    assert first["year"] == 2019  # coerced from the string "2019"
    assert first["journal"] == "Soil & Tillage Research"
    assert first["practice"] == "Mulching"
    assert len(first["snippet"]) == es.SNIPPET_CHARS
    assert first["snippet"].startswith("Mulch cover reduced soil loss")
    assert first["n_passages"] == 1


def test_shape_citations_dedupes_per_study_and_counts_passages():
    chunks = make_chunks()
    # Two more chunks of the FIRST study (lower-ranked sections of NN0123).
    chunks.append({**chunks[0], "chunk_id": "c3", "text": "Later section.",
                   "for_practice": "Soil bunds"})
    chunks.append({**chunks[0], "chunk_id": "c4", "text": "Another section."})
    citations = es.shape_citations(chunks)
    assert [c["era_code"] for c in citations] == ["NN0123", "NN0456"]
    assert citations[0]["n_passages"] == 3
    assert citations[1]["n_passages"] == 1
    # The highest-ranked chunk supplies snippet and practice.
    assert citations[0]["snippet"].startswith("Mulch cover reduced soil loss")
    assert citations[0]["practice"] == "Mulching"


def test_shape_citations_never_collapses_unidentified_studies():
    anon = {"chunk_id": "a1", "era_code": None, "doi": None, "title": None,
            "year": None, "journal": None, "text": "First anonymous chunk."}
    citations = es.shape_citations([anon, {**anon, "chunk_id": "a2",
                                           "text": "Second anonymous chunk."}])
    assert len(citations) == 2
    assert all(c["n_passages"] == 1 for c in citations)


def test_fallback_text_cites_each_study_once():
    rec, chunks = make_recommendation(), make_chunks()
    # A second, lower-ranked chunk of NN0123 for the same practice.
    chunks.insert(1, {**chunks[0], "chunk_id": "c1b", "text": "More mulch text."})
    text = es.build_fallback_text(rec, chunks)
    assert text.count("NN0123") == 1
    assert "NN0456" in text


# ------------------------------------------------------------------- is_ready
def test_is_ready_false_when_index_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    settings = make_settings(
        rag_index_dir=str(tmp_path / "no-such-store"),
        rag_chunks_path=str(tmp_path / "no-such-chunks.jsonl"),
    )
    monkeypatch.setattr(es, "get_settings", lambda: settings)
    assert es.is_ready() is False


def test_is_ready_true_when_index_and_chunks_exist(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    index_dir = tmp_path / "store"
    index_dir.mkdir()
    chunks = tmp_path / "chunks.jsonl"
    chunks.write_text("{}\n", encoding="utf-8")
    settings = make_settings(rag_index_dir=str(index_dir), rag_chunks_path=str(chunks))
    monkeypatch.setattr(es, "get_settings", lambda: settings)
    # An empty index dir (e.g. interrupted build) must NOT count as ready…
    assert es.is_ready() is False
    # …only a dir holding Chroma's persistence file does.
    (index_dir / "chroma.sqlite3").write_bytes(b"")
    assert es.is_ready() is True


# ------------------------------------------------- explain() with fake retriever
def test_explain_without_api_key_returns_grounded_fallback(no_key_settings: Settings):
    rec = make_recommendation()
    retriever = FakeRetriever(make_chunks())
    result = es.explain(rec, question=None, k=2, retriever=retriever)
    assert retriever.calls == [2]  # injected retriever used, k passed through
    assert result["grounded"] is True
    assert result["llm_used"] is False
    assert len(result["citations"]) == 2
    assert result["explanation"] == es.build_fallback_text(rec, make_chunks())


def test_explain_with_no_retrieved_chunks_is_ungrounded(no_key_settings: Settings):
    result = es.explain(make_recommendation(), retriever=FakeRetriever([]))
    assert result["grounded"] is False
    assert result["llm_used"] is False
    assert result["citations"] == []
    assert "No evidence passages were retrieved" in result["explanation"]


def test_explain_llm_text_passing_guardrail_is_returned(monkeypatch: pytest.MonkeyPatch):
    settings = make_settings(openai_api_key="sk-test")
    monkeypatch.setattr(es, "get_settings", lambda: settings)
    llm_text = "Mulching reduces soil loss (~42%) on this 8% slope [1]."
    monkeypatch.setattr(es, "_call_llm", lambda messages: llm_text)
    result = es.explain(make_recommendation(), retriever=FakeRetriever(make_chunks()))
    assert result["llm_used"] is True
    assert result["grounded"] is True
    assert result["explanation"] == llm_text


def test_explain_llm_text_failing_guardrail_falls_back(monkeypatch: pytest.MonkeyPatch):
    settings = make_settings(openai_api_key="sk-test")
    monkeypatch.setattr(es, "get_settings", lambda: settings)
    monkeypatch.setattr(es, "_call_llm", lambda messages: "soil loss falls by 87.6%")
    rec = make_recommendation()
    result = es.explain(rec, retriever=FakeRetriever(make_chunks()))
    assert result["llm_used"] is False
    assert result["grounded"] is True
    assert result["explanation"] == es.build_fallback_text(rec, make_chunks())


def test_explain_llm_failure_returns_fallback(monkeypatch: pytest.MonkeyPatch):
    settings = make_settings(openai_api_key="sk-test")
    monkeypatch.setattr(es, "get_settings", lambda: settings)
    monkeypatch.setattr(es, "_call_llm", lambda messages: None)  # network down
    result = es.explain(make_recommendation(), retriever=FakeRetriever(make_chunks()))
    assert result["llm_used"] is False
    assert result["grounded"] is True


# -------------------------------------------------------------- prompt content
def test_prompt_contains_json_labeled_passages_and_question():
    rec, chunks = make_recommendation(), make_chunks()
    messages = es._build_messages(rec, "How deep should bunds be?", chunks)
    assert messages[0]["role"] == "system"
    assert "Use ONLY numbers" in messages[0]["content"]
    user = messages[1]["content"]
    assert '"practice_family": "Erosion control and water management"' in user
    assert "[1] (NN0123)" in user and "[2] (NN0456)" in user
    assert "How deep should bunds be?" in user
