"""Unit tests for the grounded /explain service layer (Phase P2b).

These tests run WITHOUT rasterio, chromadb, the Chroma index, or network:
they import only ``app.config`` and ``app.services.explain_service`` (which
never pulls ``recommend.py``) and inject a fake retriever.
"""
from __future__ import annotations

import json
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


@pytest.fixture(autouse=True)
def _no_auto_guidance(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep unit tests hermetic: never auto-build the real Tier-2 retriever
    (tests that want guidance inject one via ``guidance_retriever=``)."""
    monkeypatch.setattr(es, "get_guidance_retriever", lambda: None)


@pytest.fixture(autouse=True)
def _no_auto_graph(monkeypatch: pytest.MonkeyPatch) -> None:
    """Same for the P6b-i knowledge graph: never load the real store.

    Without this the suite would quietly depend on whether
    ``rag/graph/store/graph.json`` happens to exist on the machine. Tests
    that want a graph inject one via ``graph_query=``.
    """
    monkeypatch.setattr(es, "get_graph_query", lambda: None)


@pytest.fixture()
def no_key_settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    settings = make_settings()
    monkeypatch.setattr(es, "get_settings", lambda: settings)
    return settings


def make_guidance_chunks() -> list[dict[str, Any]]:
    return [
        {
            "chunk_id": "G_doc1_000",
            "era_code": None,
            "tier": "guidance",
            "doi": None,
            "url": "https://gardian.example/doc1",
            "title": "Soil bund construction manual for Ethiopian highlands",
            "year": 2021,
            "journal": None,
            "source": "gardian",
            "text": "Space bunds 15 m apart on steep land; maintain after "
                    "each rainy season. Construction costs about 120 "
                    "person-days per hectare.",
            "for_practice": "Soil bunds",
        },
        {
            "chunk_id": "G_doc1_001",
            "era_code": None,
            "tier": "guidance",
            "doi": None,
            "url": "https://gardian.example/doc1",
            "title": "Soil bund construction manual for Ethiopian highlands",
            "year": 2021,
            "journal": None,
            "source": "gardian",
            "text": "Combine bunds with grass strips for stability.",
            "for_practice": "Soil bunds",
        },
    ]


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


# ------------------------------------------------- Tier-2 guidance (P5a)
def test_guardrail_strips_guidance_markers():
    rec, chunks = make_recommendation(), make_chunks()
    assert es.numbers_are_grounded("build bunds as advised [G1] [G12]", rec, chunks)


def test_guardrail_allows_numbers_quoted_from_guidance_chunks():
    rec = make_recommendation()
    combined = make_chunks() + make_guidance_chunks()
    # 15 m spacing and 120 person-days exist only in the guidance text.
    assert es.numbers_are_grounded(
        "space bunds 15 m apart [G1]; budget 120 person-days", rec, combined
    )
    # Without the guidance chunks those same numbers are invented -> reject.
    assert es.numbers_are_grounded(
        "space bunds 15 m apart [G1]; budget 120 person-days", rec, make_chunks()
    ) is False


def test_guardrail_rejects_invented_numbers_with_guidance_present():
    rec = make_recommendation()
    combined = make_chunks() + make_guidance_chunks()
    assert es.numbers_are_grounded("costs fall by 73%", rec, combined) is False


def test_guardrail_does_not_whitelist_numbers_from_urls():
    # URLs never appear in the prompt, so their digits (handle ids, dates)
    # must not license numbers in the output (review hardening, P5a).
    rec = make_recommendation()
    chunks = make_guidance_chunks()
    chunks[0]["url"] = "https://hdl.handle.net/10568/54321"
    assert es.numbers_are_grounded("apply 54321 kg per plot", rec, chunks) is False


def test_shape_citations_tags_guidance_tier_and_dedupes_per_document():
    citations = es.shape_citations(make_guidance_chunks())
    assert len(citations) == 1  # both chunks are the same document (same url)
    c = citations[0]
    assert c["tier"] == "guidance"
    assert c["era_code"] is None
    assert c["url"] == "https://gardian.example/doc1"
    assert c["n_passages"] == 2


def test_shape_citations_defaults_evidence_tier():
    citations = es.shape_citations(make_chunks())
    assert all(c["tier"] == "evidence" for c in citations)
    assert all(c["url"] is None for c in citations)


def test_prompt_contains_guidance_block_with_g_markers():
    rec, chunks = make_recommendation(), make_chunks()
    messages = es._build_messages(rec, None, chunks, make_guidance_chunks())
    user = messages[1]["content"]
    assert "GUIDANCE PASSAGES" in user
    # Both fixture passages come from ONE document, so they are [G1a]/[G1b] (P9).
    assert "[G1a] Soil bund construction manual" in user and "[G1b] Soil bund construction manual" in user
    assert "\n[G2]" not in user  # no second document (the rule text itself mentions [G2])
    assert user.index("EVIDENCE PASSAGES") < user.index("GUIDANCE PASSAGES")


# ------------------------------------------------ per-study numbering (P9)
def make_chunks_two_per_study() -> list[dict[str, Any]]:
    a, b = make_chunks()
    a2 = {**a, "chunk_id": "c1b", "text": "A second passage of the mulching study, 40% less sediment."}
    return [a, a2, b]


def test_prompt_numbers_passages_per_study():
    messages = es._build_messages(make_recommendation(), None, make_chunks_two_per_study())
    user = messages[1]["content"]
    assert "[1a] (NN0123)" in user and "[1b] (NN0123)" in user and "[2] (NN0456)" in user
    assert "[3]" not in user
    assert "numbered per study" in user
    assert "cite the study as [1]" in messages[0]["content"]


def test_shape_citations_refs_follow_the_prompt_numbering():
    cites = es.shape_citations(make_chunks_two_per_study() + make_guidance_chunks())
    assert [(c["ref"], c["n_passages"]) for c in cites] == [("1", 2), ("2", 1), ("G1", 2)]
    assert cites[0]["era_code"] == "NN0123" and cites[2]["tier"] == "guidance"


def test_shape_citations_numbers_practice_records_with_w():
    chunk = {"chunk_id": "W_1_000", "tier": "practice", "title": "Stone bunds", "url": "https://w/1", "text": "t"}
    assert es.shape_citations([chunk])[0]["ref"] == "W1"


def test_group_chunks_by_study_keeps_first_appearance_order():
    groups = es.group_chunks_by_study(make_chunks_two_per_study())
    assert [key for key, _ in groups] == ["NN0123", "NN0456"]
    assert [len(g) for _, g in groups] == [2, 1]


def test_guardrail_strips_per_study_and_record_markers():
    rec, chunks = make_recommendation(), make_chunks()
    assert es.numbers_are_grounded("mulch helps [1a] [1b] [2] [G1a] [W3]", rec, chunks)
    assert not es.numbers_are_grounded("yield rose 57% [1a]", rec, chunks)


def test_faithfulness_auditor_maps_markers_to_studies():
    import importlib.util
    from pathlib import Path as _P

    path = _P(__file__).resolve().parents[2].parent / "rag" / "eval" / "eval_faithfulness.py"
    spec = importlib.util.spec_from_file_location("eval_faithfulness", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    chunks = make_chunks_two_per_study()
    row = mod.audit_sentence("Mulch cut soil loss by 34% [1b].", make_recommendation(), chunks, es)
    assert row["cite_markers"] == "1" and row["cited_era_codes"] == "NN0123"
    assert row["cited_support"] == "yes"
    row2 = mod.audit_sentence("Bunds retained runoff on 8% slopes [2].", make_recommendation(), chunks, es)
    assert row2["cited_era_codes"] == "NN0456" and row2["cited_support"] == "yes"


def test_prompt_without_guidance_has_no_guidance_block():
    messages = es._build_messages(make_recommendation(), None, make_chunks())
    assert "GUIDANCE PASSAGES" not in messages[1]["content"]


def test_explain_llm_path_appends_guidance_citations(monkeypatch: pytest.MonkeyPatch):
    settings = make_settings(openai_api_key="sk-test")
    monkeypatch.setattr(es, "get_settings", lambda: settings)
    llm_text = "Mulching helps [1]; space bunds 15 m apart [G1]."
    monkeypatch.setattr(es, "_call_llm", lambda messages: llm_text)
    result = es.explain(
        make_recommendation(),
        retriever=FakeRetriever(make_chunks()),
        guidance_retriever=FakeRetriever(make_guidance_chunks()),
    )
    assert result["llm_used"] is True
    tiers = [c["tier"] for c in result["citations"]]
    assert tiers == ["evidence", "evidence", "guidance"]
    assert result["citations"][-1]["url"] == "https://gardian.example/doc1"


def test_explain_fallback_path_excludes_guidance_citations(no_key_settings: Settings):
    result = es.explain(
        make_recommendation(),
        retriever=FakeRetriever(make_chunks()),
        guidance_retriever=FakeRetriever(make_guidance_chunks()),
    )
    assert result["llm_used"] is False
    assert all(c["tier"] == "evidence" for c in result["citations"])


def test_explain_guidance_retrieval_failure_degrades_to_evidence_only(
    monkeypatch: pytest.MonkeyPatch,
):
    settings = make_settings(openai_api_key="sk-test")
    monkeypatch.setattr(es, "get_settings", lambda: settings)
    monkeypatch.setattr(es, "_call_llm", lambda messages: "Mulching helps [1].")

    class BrokenRetriever:
        def retrieve_for_recommendation(self, recommendation, k=8):
            raise RuntimeError("collection missing")

    result = es.explain(
        make_recommendation(),
        retriever=FakeRetriever(make_chunks()),
        guidance_retriever=BrokenRetriever(),
    )
    assert result["llm_used"] is True
    assert all(c["tier"] == "evidence" for c in result["citations"])


def test_get_guidance_retriever_none_when_chunks_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    # Bypass the autouse stub — exercise the REAL availability check.
    monkeypatch.undo()
    settings = make_settings(
        RAG_GUIDANCE_CHUNKS_PATH=str(tmp_path / "no-such-guidance.jsonl"),
    )
    monkeypatch.setattr(es, "get_settings", lambda: settings)
    es.set_guidance_retriever(None)  # reset cache + sticky flag
    try:
        assert es.get_guidance_retriever() is None
        assert es.get_guidance_retriever() is None  # sticky, still no crash
    finally:
        es.set_guidance_retriever(None)


# ------------------------------------------------- graph evidence base (P6b-i)
class FakeGraphQuery:
    """Minimal stand-in for ``rag.graph.query.GraphQuery``.

    Returns the shape ``evidence_summary`` really returns — including the
    ``mean_log_rr`` / ``median_log_rr`` aggregates, so the tests can prove
    those are dropped rather than merely absent from the fixture.
    """

    def __init__(self, summaries: dict[str, dict[str, Any]] | None = None,
                 raises: bool = False):
        self.summaries = summaries if summaries is not None else _default_summaries()
        self.raises = raises
        self.calls: list[tuple[str, str]] = []

    def evidence_summary(self, practice: str, indicator: str) -> dict[str, Any]:
        self.calls.append((practice, indicator))
        if self.raises:
            raise RuntimeError("graph exploded")
        return self.summaries.get(
            practice,
            {"practice": practice, "indicator": indicator, "found": False,
             "studies": [], "n_studies": 0, "n_obs": 0, "aez_belts": [],
             "crop_groups": [], "corpus_status": {}},
        )


def _default_summaries() -> dict[str, dict[str, Any]]:
    return {
        "Mulching": {
            "practice": "Mulching",
            "indicator": "soil loss",
            "found": True,
            "n_studies": 3,
            "n_obs": 17,
            "aez_belts": ["Dry Dega", "Moist Weyna Dega"],
            "crop_groups": ["Cereal"],
            "corpus_status": {"full_text": 1, "abstract": 1, "none": 1},
            "studies": [
                {"study_no": "ERA_NN0123", "era_code": "NN0123",
                 "title": "Mulching effects on erosion", "year": 2019,
                 "doi": "10.1000/xyz1", "corpus_status": "full_text",
                 "n_chunks": 4, "n_obs": 9,
                 # magnitudes the service must NOT copy through:
                 "mean_log_rr": -0.55123, "median_log_rr": -0.5,
                 "share_positive": 0.11, "aez_belts": ["Dry Dega"],
                 "crop_groups": ["Cereal"]},
                {"study_no": "ERA_NN0999", "era_code": "NN0999",
                 "title": "Residue cover trial", "year": 2016,
                 "doi": None, "corpus_status": "abstract",
                 "n_chunks": 1, "n_obs": 5, "mean_log_rr": -0.21,
                 "median_log_rr": -0.2, "share_positive": 0.2,
                 "aez_belts": ["Moist Weyna Dega"], "crop_groups": ["Cereal"]},
                {"study_no": "CSA_7", "era_code": None, "title": None,
                 "year": None, "doi": None, "corpus_status": "none",
                 "n_chunks": 0, "n_obs": 3, "mean_log_rr": -0.3,
                 "median_log_rr": -0.3, "share_positive": 0.0,
                 "aez_belts": ["Dry Dega"], "crop_groups": ["Cereal"]},
            ],
        }
    }


def test_evidence_base_reports_counts_and_provenance():
    gq = FakeGraphQuery()
    base = es.build_evidence_base(make_recommendation(), gq)
    assert set(base) == {"Mulching"}          # "Soil bunds" has found=False
    entry = base["Mulching"]
    assert entry["n_studies"] == 3 and entry["n_obs"] == 17
    assert entry["aez_belts"] == ["Dry Dega", "Moist Weyna Dega"]
    assert entry["crop_groups"] == ["Cereal"]
    assert entry["corpus_status"] == {"full_text": 1, "abstract": 1, "none": 1}
    assert [st["era_code"] for st in entry["studies"]] == ["NN0123", "NN0999", None]
    assert entry["studies"][0]["year"] == 2019
    assert gq.calls == [("Mulching", "soil loss"), ("Soil bunds", "soil loss")]


def test_evidence_base_never_exposes_effect_magnitudes():
    """Doctrine 1: the graph's dataset aggregates must not reach the API."""
    base = es.build_evidence_base(make_recommendation(), FakeGraphQuery())
    blob = json.dumps(base)
    for forbidden in ("mean_log_rr", "median_log_rr", "share_positive",
                      "-0.55123", "0.11"):
        assert forbidden not in blob, forbidden
    allowed_keys = {"n_studies", "n_obs", "aez_belts", "crop_groups",
                    "corpus_status", "studies"}
    assert set(base["Mulching"]) == allowed_keys
    assert set(base["Mulching"]["studies"][0]) == {
        "era_code", "title", "year", "doi", "corpus_status"}


def test_evidence_base_is_empty_without_a_graph():
    assert es.build_evidence_base(make_recommendation(), None) == {}


def test_evidence_base_survives_a_failing_graph_query():
    """One bad practice must not sink the whole response."""
    assert es.build_evidence_base(
        make_recommendation(), FakeGraphQuery(raises=True)
    ) == {}


def test_evidence_base_needs_an_indicator():
    rec = make_recommendation()
    rec["query"].pop("indicator")
    assert es.build_evidence_base(rec, FakeGraphQuery()) == {}


def test_evidence_base_sentence_states_counts_and_corpus_coverage():
    entry = es.build_evidence_base(make_recommendation(), FakeGraphQuery())["Mulching"]
    sentence = es.evidence_base_sentence("Mulching", entry)
    assert "3 studies" in sentence and "17 field observations" in sentence
    assert "Dry Dega, Moist Weyna Dega" in sentence
    assert "2 of the studies are in the retrievable corpus" in sentence
    assert "%" not in sentence          # no magnitudes, ever


def test_evidence_base_sentence_uses_singulars():
    entry = {"n_studies": 1, "n_obs": 1, "aez_belts": [],
             "corpus_status": {"full_text": 1, "abstract": 0, "none": 0}}
    sentence = es.evidence_base_sentence("P", entry)
    assert "1 study / 1 field observation" in sentence
    assert "1 of the studies is in the retrievable corpus" in sentence


def test_prompt_contains_the_evidence_base_block():
    base = es.build_evidence_base(make_recommendation(), FakeGraphQuery())
    messages = es._build_messages(
        make_recommendation(), None, make_chunks(), None, base
    )
    user = messages[1]["content"]
    assert "EVIDENCE BASE" in user
    assert "backed by 3 studies / 17 field observations" in user
    assert "NOT effect sizes" in user
    # it must sit before the passages
    assert user.index("EVIDENCE BASE") < user.index("EVIDENCE PASSAGES")
    assert "mean_log_rr" not in user


def test_prompt_without_a_graph_has_no_evidence_base_block():
    user = es._build_messages(make_recommendation(), None, make_chunks(), None, {})[1]
    assert "EVIDENCE BASE" not in user["content"]


def test_guardrail_whitelists_the_evidence_base_counts():
    base = es.build_evidence_base(make_recommendation(), FakeGraphQuery())
    rec, chunks = make_recommendation(), make_chunks()
    text = "Mulching is backed by 3 studies and 17 field observations."
    assert not es.numbers_are_grounded(text, rec, chunks)      # 17 not in the JSON
    assert es.numbers_are_grounded(text, rec, chunks, base)


def test_guardrail_still_rejects_invented_numbers_with_an_evidence_base():
    """Extending the whitelist must not open a hole."""
    base = es.build_evidence_base(make_recommendation(), FakeGraphQuery())
    assert not es.numbers_are_grounded(
        "Mulching cuts soil loss by 77.4% across 3 studies.",
        make_recommendation(), make_chunks(), base,
    )


def test_guardrail_whitelists_only_the_numbers_the_prompt_states():
    """Reviewer hardening (25 Oct 2026): the evidence base contributes exactly
    n_studies, n_obs and the in-corpus count. Study years, era codes and the
    per-bucket corpus counts are not in the prompt, so they are not admitted."""
    base = es.build_evidence_base(make_recommendation(), FakeGraphQuery())
    rec, chunks = make_recommendation(), make_chunks()
    # 2019 / 2016 are study years in the evidence base, NOT in any retrieved chunk
    years_in_chunks = {c.get("year") for c in chunks}
    assert 2016 not in years_in_chunks
    assert not es.numbers_are_grounded(
        "A 2016 residue trial backs Mulching.", rec, chunks, base
    )
    # 2 studies in the corpus (1 full text + 1 abstract) IS stated in the sentence
    assert es.numbers_are_grounded(
        "2 of the 3 studies behind Mulching are in the retrievable corpus.",
        rec, chunks, base,
    )
    # the per-bucket count "1" is admitted only because 0-10 integers always are;
    # a bucket-sized number outside that range must not pass
    big = {k: dict(v) for k, v in base.items()}
    big["Mulching"]["corpus_status"] = {"full_text": 40, "abstract": 3, "none": 2}
    big["Mulching"]["n_studies"], big["Mulching"]["n_obs"] = 45, 300
    assert es.numbers_are_grounded("Mulching: 45 studies, 300 observations, 43 in corpus.", rec, chunks, big)
    assert not es.numbers_are_grounded("40 of them are full-text studies.", rec, chunks, big)


def test_fallback_text_includes_the_evidence_base_sentence():
    base = es.build_evidence_base(make_recommendation(), FakeGraphQuery())
    text = es.build_fallback_text(make_recommendation(), make_chunks(), base)
    assert "the model estimates ~42% decrease in soil loss" in text
    assert "backed by 3 studies / 17 field observations" in text


def test_fallback_text_unchanged_without_a_graph():
    rec, chunks = make_recommendation(), make_chunks()
    assert es.build_fallback_text(rec, chunks) == es.build_fallback_text(rec, chunks, {})


def test_explain_returns_the_evidence_base(no_key_settings: Settings):
    result = es.explain(
        make_recommendation(), retriever=FakeRetriever(make_chunks()),
        graph_query=FakeGraphQuery(),
    )
    assert set(result["evidence_base"]) == {"Mulching"}
    assert result["evidence_base"]["Mulching"]["n_studies"] == 3
    assert "backed by 3 studies" in result["explanation"]


def test_explain_evidence_base_is_empty_not_null_without_a_graph(
    no_key_settings: Settings,
):
    result = es.explain(make_recommendation(), retriever=FakeRetriever(make_chunks()))
    assert result["evidence_base"] == {}


def test_explain_with_no_chunks_still_reports_the_evidence_base(
    no_key_settings: Settings,
):
    """Nothing retrieved is not the same as no evidence existing."""
    result = es.explain(
        make_recommendation(), retriever=FakeRetriever([]),
        graph_query=FakeGraphQuery(),
    )
    assert result["grounded"] is False
    assert result["evidence_base"]["Mulching"]["n_studies"] == 3


def test_graph_is_ready_follows_the_store_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    backend_root = tmp_path / "repo" / "app" / "backend"
    backend_root.mkdir(parents=True)
    monkeypatch.setattr(es, "get_settings",
                        lambda: make_settings(backend_root=backend_root))
    assert es.graph_is_ready() is False
    store = tmp_path / "repo" / "rag" / "graph" / "store"
    store.mkdir(parents=True)
    (store / "graph.json").write_text("{}", encoding="utf-8")
    assert es.graph_is_ready() is True


def test_get_graph_query_degrades_when_the_store_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    backend_root = tmp_path / "repo" / "app" / "backend"
    backend_root.mkdir(parents=True)
    monkeypatch.setattr(es, "get_settings",
                        lambda: make_settings(backend_root=backend_root))
    monkeypatch.setattr(es, "_graph_query", None)
    monkeypatch.setattr(es, "_graph_unavailable", False)
    assert es.get_graph_query() is None          # logs once, never raises
