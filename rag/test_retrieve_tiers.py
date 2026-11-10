"""Tier tags and tiered fusion in ``rag.retrieve`` (E2 C3); no index or network needed."""
from __future__ import annotations

import pytest

from rag import retrieve as rr


class FakeTier:
    def __init__(self, hits):
        self.hits = hits

    def retrieve(self, query, k=8):
        return self.hits[:k]


def _hit(cid, tier):
    return {"chunk_id": cid, "tier": tier, "text": cid}


def test_tiered_retriever_fuses_and_keeps_tier_tags():
    t2 = FakeTier([_hit("G_a", "guidance"), _hit("G_b", "guidance"), _hit("G_c", "guidance")])
    t2b = FakeTier([_hit("GL_x_p001_0", "guidelines"), _hit("GL_x_p002_0", "guidelines")])
    hits = rr.TieredRetriever([t2, t2b]).retrieve("soil bunds", k=4)
    assert [h["chunk_id"] for h in hits][:2] in (["G_a", "GL_x_p001_0"], ["GL_x_p001_0", "G_a"])
    assert {h["tier"] for h in hits} == {"guidance", "guidelines"}
    assert len(hits) == 4


def test_tiered_retrieve_for_recommendation_per_practice():
    t = rr.TieredRetriever([FakeTier([_hit("G_a", "guidance")]), FakeTier([_hit("GL_b", "guidelines")])])
    rec = {"query": {"indicator": "soil loss", "practice_family": "x"}, "details": {"context": {}},
           "recommendations": [{"practice": "Mulch"}, {"practice": "Physical SWC measures"}]}
    out = t.retrieve_for_recommendation(rec, k=4)
    assert {h["for_practice"] for h in out} == {"Mulch"}  # deduped ids: the second practice adds nothing new
    assert all("tier" in h for h in out)


def test_single_tier_hits_get_evidence_tag():
    r = rr.RagRetriever.__new__(rr.RagRetriever)
    r._by_id = {"A_000": {"chunk_id": "A_000", "text": "x"}, "G_1": {"chunk_id": "G_1", "tier": "guidance", "text": "y"}}
    r._dense = lambda q, n: ["A_000", "G_1"]
    r._lexical = lambda q, n: ["A_000"]
    hits = r.retrieve("q", k=2)
    assert [h["tier"] for h in hits] == ["evidence", "guidance"]
    assert "tier" not in r._by_id["A_000"]  # the stored chunk itself is not mutated


def test_guidelines_flag(monkeypatch):
    monkeypatch.setenv("RAG_GUIDELINES_ENABLED", "false")
    assert rr.guidelines_enabled() is False
    monkeypatch.setenv("RAG_GUIDELINES_ENABLED", "true")
    assert rr.guidelines_enabled() is True


def test_tiered_needs_a_tier():
    with pytest.raises(ValueError):
        rr.TieredRetriever([])
