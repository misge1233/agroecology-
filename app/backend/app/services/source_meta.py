"""Source metadata sidecars for citation display (U9: C2 + C3).

Two NON-destructive sidecar files improve how sources are cited; neither
changes retrieval, ranking or any number (doctrine 1 — metadata only):

* ``rag/corpus/guidance/doc_metadata.json`` — proper title / year / item
  page for Tier-2 guidance documents, backfilled from CGSpace by
  ``rag/ingest/backfill_guidance_metadata.py`` (chunks only carry the PDF's
  first line as title and a bitstream download URL).
* ``data/processed/csa_study_references.json`` — ``CSA_<n>`` study number ->
  bibliographic reference, built by
  ``pipelines/dataset/build_csa_references.py``; ``_compilation`` holds the
  Adimassu et al. compilation citation used as fallback.

Both are loaded lazily on first use and cached. Paths resolve against the
repo root (``settings.backend_root.parents[1]``). A missing or unreadable
file degrades to an empty map (logged once) — never an exception.
"""
from __future__ import annotations

import copy
import json
import logging
import re
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

GUIDANCE_META_REL = Path("rag") / "corpus" / "guidance" / "doc_metadata.json"
CSA_REFERENCES_REL = Path("data") / "processed" / "csa_study_references.json"
COMPILATION_KEY = "_compilation"

# Guidance chunk ids are "G_<doc_id>_<pos>" (rag/ingest/chunk_guidance.py).
_CHUNK_ID_RE = re.compile(r"^G_(?P<doc>.+)_\d+$")
_STUDY_NO_RE = re.compile(r"(\d+)")

_lock = threading.Lock()
_guidance_by_doc: dict[str, dict[str, Any]] | None = None
_guidance_by_url: dict[str, dict[str, Any]] | None = None
_csa_refs: dict[str, dict[str, Any]] | None = None


def _repo_root() -> Path:
    from app.config import get_settings  # deferred: keep import cheap/testable

    return Path(get_settings().backend_root).resolve().parents[1]


def _read_json(path: Path, label: str) -> dict[str, Any]:
    """Parsed JSON object, or {} (logged once per load) when unavailable."""
    if not path.exists():
        logger.info("%s sidecar not found at %s — using source chunk metadata",
                    label, path)
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning("%s sidecar unreadable (%s): %s — ignored", label, path, exc)
        return {}
    if not isinstance(data, dict):
        logger.warning("%s sidecar %s is not a JSON object — ignored", label, path)
        return {}
    return data


def _norm_url(url: str | None) -> str:
    return (url or "").strip().rstrip("/").lower()


def _load_guidance() -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    global _guidance_by_doc, _guidance_by_url
    if _guidance_by_doc is None or _guidance_by_url is None:
        with _lock:
            if _guidance_by_doc is None or _guidance_by_url is None:
                raw = _read_json(_repo_root() / GUIDANCE_META_REL, "Guidance metadata")
                docs = raw.get("documents", {}) if isinstance(raw.get("documents"), dict) else {}
                by_doc = {str(k): v for k, v in docs.items() if isinstance(v, dict)}
                by_url = {_norm_url(v.get("source_url")): v
                          for v in by_doc.values() if v.get("source_url")}
                _guidance_by_doc, _guidance_by_url = by_doc, by_url
    return _guidance_by_doc, _guidance_by_url


def _load_csa() -> dict[str, dict[str, Any]]:
    global _csa_refs
    if _csa_refs is None:
        with _lock:
            if _csa_refs is None:
                raw = _read_json(_repo_root() / CSA_REFERENCES_REL, "CSA study references")
                _csa_refs = {k: v for k, v in raw.items()
                             if isinstance(v, dict) and k != "_about"}
    return _csa_refs


def reset_cache() -> None:
    """Forget loaded sidecars (tests; or after regenerating the files)."""
    global _guidance_by_doc, _guidance_by_url, _csa_refs
    with _lock:
        _guidance_by_doc = _guidance_by_url = _csa_refs = None


# ---------------------------------------------------------------- guidance
def _doc_id_of(item: dict[str, Any]) -> str | None:
    for key in ("doc_id", "document_id"):
        if item.get(key):
            return str(item[key])
    m = _CHUNK_ID_RE.match(str(item.get("chunk_id") or ""))
    return m.group("doc") if m else None


def guidance_meta(chunk_or_citation: dict[str, Any]) -> dict[str, Any] | None:
    """Backfilled metadata for a guidance chunk/citation, or None.

    Matches by document id (``doc_id`` or the ``G_<doc_id>_<pos>`` chunk id)
    first, then by the original download URL (``url`` / ``source_url``).
    """
    if not isinstance(chunk_or_citation, dict):
        return None
    by_doc, by_url = _load_guidance()
    if not by_doc:
        return None
    doc_id = _doc_id_of(chunk_or_citation)
    if doc_id and doc_id in by_doc:
        return by_doc[doc_id]
    for key in ("source_url", "url"):
        hit = by_url.get(_norm_url(chunk_or_citation.get(key)))
        if hit:
            return hit
    return None


def apply_guidance_meta(citation: dict[str, Any]) -> dict[str, Any]:
    """COPY of ``citation`` with backfilled title/year and item-page link.

    ``url`` becomes the repository item (handle) page; the original link is
    kept under ``source_url``. Fields the sidecar lacks are left unchanged;
    a citation without a sidecar entry is returned as an unchanged copy.
    """
    out = copy.deepcopy(citation)
    meta = guidance_meta(citation)
    if not meta:
        return out
    if meta.get("title"):
        out["title"] = meta["title"]
    if meta.get("year"):
        out["year"] = meta["year"]
    if meta.get("handle_url"):
        if out.get("url") and out.get("url") != meta["handle_url"]:
            out.setdefault("source_url", out["url"])
        out["url"] = meta["handle_url"]
    return out


# --------------------------------------------------------------------- CSA
def _study_key(study_no: str) -> tuple[str, str] | None:
    """('CSA_18', '18') from 'CSA_18' / 'csa 18' / '18'; None if no number."""
    m = _STUDY_NO_RE.search(str(study_no or ""))
    if not m:
        return None
    n = str(int(m.group(1)))
    return f"CSA_{n}", n


def csa_reference(study_no: str) -> dict[str, Any] | None:
    """Bibliographic entry for a CSA dataset study, or None.

    Returns a copy of the study's own entry (``study_no``, ``study_number``,
    ``compilation: False`` and ``compilation_citation`` added) when the
    mapping has it; otherwise a copy of the ``_compilation`` entry with
    ``study_no`` set and ``"compilation": True`` so the UI can render
    "<compilation citation>, study <n>". None when neither is available.
    """
    key = _study_key(study_no)
    if not key:
        return None
    refs = _load_csa()
    full_key, n = key
    entry = refs.get(full_key)
    comp = refs.get(COMPILATION_KEY)
    if entry:
        out = copy.deepcopy(entry)
        out["study_no"] = full_key
        out["study_number"] = n
        out["compilation"] = False
        if comp and comp.get("citation"):
            # Short-form / truncated entries can still name the compilation.
            out.setdefault("compilation_citation", comp["citation"])
        return out
    if comp:
        out = copy.deepcopy(comp)
        out["study_no"] = full_key
        out["study_number"] = n
        out["compilation"] = True
        return out
    return None


def enrich_citation(citation: dict[str, Any]) -> dict[str, Any]:
    """COPY of a citation with the best bibliographic metadata on disk (U9, C2/C3).

    - Guidance: the CGSpace title, year and handle page (``apply_guidance_meta``).
    - A dataset study (``study_no`` without an ERA code): its reference from the
      CSA sheet: title, year, DOI and the full ``reference`` string; a study
      with no own entry is cited as "<compilation>, study <n>"
      (``compilation: True``).
    The identity fields (``era_code``, ``study_no``) never change, so the
    citation registry keys stay stable. Unknown sources come back unchanged.
    """
    tier = citation.get("tier") or "evidence"
    if tier == "guidance":
        return apply_guidance_meta(citation)
    out = copy.deepcopy(citation)
    study_no = out.get("study_no")
    if tier != "evidence" or out.get("era_code") or not study_no:
        return out
    ref = csa_reference(str(study_no))
    if not ref:
        return out
    if ref.get("compilation"):
        out["title"] = out.get("title") or ref.get("title")
        out["reference"] = f"{ref.get('citation') or ref.get('title')}, study {ref.get('study_number')}"
        out["compilation"] = True
        out["url"] = out.get("url") or ref.get("handle_url")
    else:
        out["title"] = out.get("title") or ref.get("title") or ref.get("citation")
        out["reference"] = ref.get("citation")
        out["compilation"] = False
        if ref.get("truncated"):
            out["reference_truncated"] = True
    out["year"] = out.get("year") or ref.get("year")
    out["doi"] = out.get("doi") or ref.get("doi")
    out["journal"] = out.get("journal") or ref.get("journal")
    return out
