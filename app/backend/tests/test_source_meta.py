"""source_meta: guidance title/link backfill + CSA study references (U9 C2/C3).

Hermetic: sidecars are written to tmp_path and the repo root is monkeypatched;
no network, no index, no real corpus files.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pytest

from app.services import source_meta as sm

DOWNLOAD = "https://cgspace.cgiar.org/rest/bitstreams/7e31ad1f-64f1-4cf3-b303-2c68c17629f1/retrieve"
HANDLE = "https://cgspace.cgiar.org/handle/10568/69989"
DOC_ID = "5205be27-1f1b-4a6b-b71d-d52c441fa8d3"


def _write(root: Path, rel: Path, payload: dict[str, Any]) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(sm, "_repo_root", lambda: tmp_path)
    sm.reset_cache()
    yield tmp_path
    sm.reset_cache()


@pytest.fixture
def sidecars(root: Path) -> Path:
    _write(root, sm.GUIDANCE_META_REL, {
        "_about": {"generator": "test"},
        "documents": {
            DOC_ID: {
                "doc_id": DOC_ID,
                "title": "Report of a working group on tropical forage genetic resources",
                "year": 1994,
                "handle_url": HANDLE,
                "source_url": DOWNLOAD,
                "language": "en",
                "region": None,
                "retrieved_at": "2026-11-01T00:00:00+00:00",
            },
            "no-handle-doc": {"doc_id": "no-handle-doc", "title": "Only a title",
                              "year": None, "handle_url": None,
                              "source_url": "https://example.org/x.pdf"},
        },
    })
    _write(root, sm.CSA_REFERENCES_REL, {
        "_about": {"counts": {}},
        "_compilation": {"authors": "Adimassu, Z.; Tamene, L.", "year": 2024,
                         "title": "Identification and prioritization of CSA practices",
                         "journal": "Environ. Res. Commun.",
                         "doi": "10.1088/2515-7620/ad54a1",
                         "citation": "Adimassu et al. (2024) ..."},
        "CSA_6": {"authors": "Temesgen, M.", "year": 2009,
                  "title": "Conservation tillage implements", "journal": "Soil and Tillage Research",
                  "doi": "10.1016/j.still.2008.10.026", "citation": "Temesgen ... 2009"},
    })
    return root


# ------------------------------------------------------------------ guidance
def test_guidance_meta_matches_by_chunk_id_and_url(sidecars: Path) -> None:
    by_chunk = sm.guidance_meta({"chunk_id": f"G_{DOC_ID}_004"})
    by_url = sm.guidance_meta({"url": DOWNLOAD + "/"})
    by_doc = sm.guidance_meta({"doc_id": DOC_ID})
    assert by_chunk and by_url and by_doc
    assert by_chunk["handle_url"] == by_url["handle_url"] == HANDLE
    assert sm.guidance_meta({"url": "https://elsewhere.org/a.pdf"}) is None
    assert sm.guidance_meta({}) is None


def test_apply_guidance_meta_returns_copy_with_handle(sidecars: Path) -> None:
    citation = {"title": "SS .tf13 ,J/33 (.2 COlECClON", "year": None,
                "url": DOWNLOAD, "chunk_id": f"G_{DOC_ID}_004", "tier": "guidance"}
    out = sm.apply_guidance_meta(citation)
    assert out is not citation
    assert citation["url"] == DOWNLOAD and citation["year"] is None  # original untouched
    assert out["title"].startswith("Report of a working group")
    assert out["year"] == 1994
    assert out["url"] == HANDLE
    assert out["source_url"] == DOWNLOAD
    assert out["tier"] == "guidance"


def test_apply_guidance_meta_partial_and_unknown(sidecars: Path) -> None:
    partial = sm.apply_guidance_meta({"title": "x", "url": "https://example.org/x.pdf"})
    assert partial["title"] == "Only a title"
    assert partial["url"] == "https://example.org/x.pdf"  # no handle -> link kept
    assert "source_url" not in partial
    unknown = {"title": "keep", "url": "https://nowhere.org/y"}
    assert sm.apply_guidance_meta(unknown) == unknown


# ----------------------------------------------------------------------- CSA
def test_csa_reference_direct_hit(sidecars: Path) -> None:
    ref = sm.csa_reference("CSA_6")
    assert ref is not None
    assert ref["doi"] == "10.1016/j.still.2008.10.026"
    assert ref["study_no"] == "CSA_6" and ref["compilation"] is False
    assert ref["compilation_citation"].startswith("Adimassu")
    assert sm.csa_reference("csa 06")["title"] == "Conservation tillage implements"


def test_csa_reference_falls_back_to_compilation(sidecars: Path) -> None:
    ref = sm.csa_reference("CSA_18")
    assert ref is not None and ref["compilation"] is True
    assert ref["study_no"] == "CSA_18" and ref["study_number"] == "18"
    assert ref["doi"] == "10.1088/2515-7620/ad54a1"
    assert sm.csa_reference("not-a-study") is None


def test_mutating_result_does_not_leak_into_cache(sidecars: Path) -> None:
    sm.csa_reference("CSA_6")["title"] = "mutated"
    assert sm.csa_reference("CSA_6")["title"] == "Conservation tillage implements"


# ------------------------------------------------------------- degradation
def test_missing_files_degrade_to_empty(root: Path, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger=sm.__name__):
        assert sm.guidance_meta({"url": DOWNLOAD}) is None
        assert sm.guidance_meta({"url": DOWNLOAD}) is None  # cached, no re-log
        assert sm.csa_reference("CSA_6") is None
        c = {"title": "t", "url": DOWNLOAD}
        assert sm.apply_guidance_meta(c) == c
    assert sum("not found" in r.getMessage() for r in caplog.records) == 2


def test_corrupt_file_never_raises(root: Path) -> None:
    for rel in (sm.GUIDANCE_META_REL, sm.CSA_REFERENCES_REL):
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{not json", encoding="utf-8")
    assert sm.guidance_meta({"url": DOWNLOAD}) is None
    assert sm.csa_reference("CSA_6") is None
