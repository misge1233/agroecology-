"""U9 (C2/C3): citations carry real titles, handle pages and dataset references.

Runs against the committed sidecars (rag/corpus/guidance/doc_metadata.json,
data/processed/csa_study_references.json); skips cleanly if they are absent.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app.services import source_meta
from app.services.evidence_service import citation_identity
from app.services.source_meta import enrich_citation

REPO = Path(__file__).resolve().parents[3]
GUIDANCE_META = REPO / "rag" / "corpus" / "guidance" / "doc_metadata.json"
CSA_REFS = REPO / "data" / "processed" / "csa_study_references.json"
HANDLE = re.compile(r"^https://[a-z.]+/handle/[\d.]+/\d+$")


@pytest.fixture(autouse=True)
def _fresh():
    source_meta.reset_cache()
    yield
    source_meta.reset_cache()


@pytest.mark.skipif(not GUIDANCE_META.exists(), reason="guidance metadata sidecar not built")
def test_guidance_citations_get_titles_and_handles():
    docs = json.loads(GUIDANCE_META.read_text(encoding="utf-8"))["documents"]
    sample = [d for d in docs.values() if d.get("handle_url")][:25]
    assert sample, "no resolved guidance document"
    for d in sample:
        raw = {"tier": "guidance", "title": "CONTENTS LISTS AVAILABLE AT", "url": d["source_url"], "ref": "G1"}
        out = enrich_citation(raw)
        assert out["title"] == d["title"] and out["title"].strip()
        assert HANDLE.match(out["url"]), out["url"]
        assert out["source_url"] == d["source_url"]
        assert out["ref"] == "G1"


@pytest.mark.skipif(not CSA_REFS.exists(), reason="CSA reference sidecar not built")
def test_every_dataset_study_has_a_reference():
    refs = json.loads(CSA_REFS.read_text(encoding="utf-8"))
    ids = [k for k in refs if k.startswith("CSA_")]
    assert len(ids) >= 133
    for sid in ids:
        out = enrich_citation({"tier": "evidence", "study_no": sid, "era_code": None, "title": None})
        assert out["reference"], sid
        assert out["title"], sid
        # The registry identity of a source never changes with enrichment.
        assert citation_identity(out) == citation_identity({"tier": "evidence", "study_no": sid})


@pytest.mark.skipif(not CSA_REFS.exists(), reason="CSA reference sidecar not built")
def test_unmapped_study_cites_the_compilation_with_its_number():
    out = enrich_citation({"tier": "evidence", "study_no": "CSA_99999"})
    assert out["compilation"] is True
    assert out["reference"].endswith(", study 99999")


def test_era_studies_and_unknown_sources_pass_through():
    era = {"tier": "evidence", "era_code": "NN0123", "study_no": "CSA_18", "title": "ERA title"}
    assert enrich_citation(era) == era
    rec = {"tier": "practice", "wocat_id": "T_1", "title": "Stone bunds"}
    assert enrich_citation(rec) == rec


@pytest.mark.skipif(not GUIDANCE_META.exists(), reason="guidance metadata sidecar not built")
def test_two_pdfs_of_one_cgspace_item_are_one_source():
    """Two PDFs of one CGSpace item share its handle page: one citation, one document."""
    from collections import defaultdict

    from app.services.evidence_service import _Candidate

    docs = json.loads(GUIDANCE_META.read_text(encoding="utf-8"))["documents"]
    by_handle: dict[str, list[dict]] = defaultdict(list)
    for d in docs.values():
        if d.get("handle_url") and d.get("source_url"):
            by_handle[d["handle_url"]].append(d)
    shared = [v for v in by_handle.values() if len(v) > 1]
    if not shared:
        pytest.skip("no CGSpace item with two PDFs in the sidecar")
    a, b = shared[0][:2]
    cand = _Candidate("Mulch", "Mulch", "Mulch")
    for d in (a, b):
        cand.add_citation({"tier": "guidance", "title": "x", "url": d["source_url"]})
    assert len(cand.citations) == 1
    assert cand.citations[0]["url"] == a["handle_url"]
