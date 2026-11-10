"""E2: guidelines on the documented path (C3) and graph documents on cards (D2); no index needed."""
from __future__ import annotations

from types import SimpleNamespace

from app.services import evidence_service as es
from app.services import explain_service as xs


def _settings(tmp_path, enabled=True, exists=True):
    path = tmp_path / "chunks.jsonl"
    if exists:
        path.write_text("", encoding="utf-8")
    return SimpleNamespace(rag_guidelines_enabled=enabled, resolved_rag_guidelines_chunks_path=path,
                           resolved_rag_index_dir=tmp_path, openai_api_key="")


def test_disabled_or_missing_guidelines_leave_tier2_untouched(tmp_path):
    tier2 = object()
    assert xs._with_guidelines(tier2, _settings(tmp_path, enabled=False)) is tier2
    assert xs._with_guidelines(tier2, _settings(tmp_path, exists=False)) is tier2


def test_enabled_guidelines_give_a_tiered_retriever(tmp_path, monkeypatch):
    xs._ensure_repo_root_on_path()
    import rag.retrieve as rr

    monkeypatch.setattr(rr, "RagRetriever", lambda **kw: SimpleNamespace(kw=kw))
    tier2 = object()
    out = xs._with_guidelines(tier2, _settings(tmp_path))
    assert isinstance(out, rr.TieredRetriever)
    assert out.retrievers[0] is tier2 and out.retrievers[1].kw["collection"] == rr.GUIDELINES_COLLECTION


def _gl(page, doc="MOA_X"):
    return {"chunk_id": f"GL_{doc}_p{page:03d}_0", "tier": "guidelines", "doc_id": doc, "page": page,
            "title": "Guide", "citation": f"MoA 2016, Guide, p. {page}", "url": "u", "year": 2016,
            "language": "en", "text": f"Build bunds on page {page}."}


def test_shape_citations_shares_g_numbering_and_labels_pages():
    chunks = [
        {"chunk_id": "G_doc_001", "tier": "guidance", "url": "https://cgspace/x", "title": "Tier 2 doc", "text": "t"},
        _gl(34), _gl(34) | {"chunk_id": "GL_MOA_X_p034_1"}, _gl(36),
    ]
    cits = xs.shape_citations(chunks)
    assert [c["ref"] for c in cits] == ["G1", "G2", "G3"]               # one [Gn] sequence for both tiers
    g2 = cits[1]
    assert (g2["tier"], g2["title"], g2["page"], g2["n_passages"]) == ("guidelines", "MoA 2016, Guide, p. 34", 34, 2)
    assert cits[2]["title"].endswith("p. 36")


def test_evidence_tier_numbering_unchanged():
    cits = xs.shape_citations([{"chunk_id": "A_000", "era_code": "A", "text": "x"},
                               {"chunk_id": "B_000", "era_code": "B", "text": "y"}])
    assert [c["ref"] for c in cits] == ["1", "2"] and "page" not in cits[0]


def test_candidate_citations_share_prefix():
    cands = [{"citations": [{"tier": "guidance", "url": "u1"}, {"tier": "guidelines", "doc_id": "D", "page": 3},
                            {"tier": "guidelines", "doc_id": "D", "page": 4}, {"tier": "evidence", "era_code": "E1"}]}]
    es._number_citations(cands)
    assert [c["ref"] for c in cands[0]["citations"]] == ["G1", "G2", "G3", "1"]


def test_practice_documents_from_graph():
    class FakeGraph:
        def documents_for_practice(self, p):
            return {"catalogue": [{"catalogue_id": "CAT_01", "relation": "alias"}],
                    "guideline_docs": [{"doc_id": f"D_{p}", "n_chunks": 3, "title_match": p == "Mulch"}]}

    cats, docs = es.practice_documents(FakeGraph(), ["Mulch", "Physical SWC measures"])
    assert [c["catalogue_id"] for c in cats] == ["CAT_01"]
    assert [d["doc_id"] for d in docs] == ["D_Mulch", "D_Physical SWC measures"]
    assert es.practice_documents(object(), ["Mulch"]) == ([], [])     # graph without the layer
