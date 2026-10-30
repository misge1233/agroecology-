"""Evidence sufficiency and knowledge candidates (Phase P9).

Decides HOW MUCH field-trial evidence stands behind a request and, when it
is thin or absent, PROPOSES documented practices from knowledge sources —
graph relations, Tier-2 guidance documents and (from P6b-ii) WOCAT practice
records — each with provenance and a deterministic rationale.

Doctrine (CLAUDE.md as amended in P9):

* The ML model owns every effect number. Nothing here computes, copies or
  implies an effect size: the only numbers are counts of studies,
  observations, passages and documents, read from the knowledge graph and
  the retrieval results.
* Cite or stay silent: a candidate without at least one citation is dropped.
* Wrap, never fork: the candidate pool is the engine's own
  (``recommender_service.practices_by_family``), retrieval reuses
  ``rag.retrieve.build_query_text``, component decomposition reuses
  ``rag.graph.practice_components`` and the keyword table extends
  ``fetch_gardian.FAMILY_KEYWORDS``.

Every function takes its collaborators as arguments so tests run on
synthetic graphs and fixture passages, without chromadb, rasters or the model.
"""
from __future__ import annotations

import logging
import re
import sys
from collections import defaultdict
from typing import Any, Iterable

from app.config import get_settings
from app.i18n import t, term

logger = logging.getLogger(__name__)

Mode = str  # "model-led" | "hybrid" | "knowledge-led"
MODEL_LED, HYBRID, KNOWLEDGE_LED = "model-led", "hybrid", "knowledge-led"
MODES: tuple[str, ...] = (MODEL_LED, HYBRID, KNOWLEDGE_LED)

SOURCE_OTHER_OBJECTIVES = "evidence_other_objectives"
SOURCE_GUIDANCE = "documented_in_guidance"
SOURCE_PRACTICE_RECORD = "documented_practice_record"
#: Ranking order of sources (more direct evidence first) for tie-breaks.
SOURCE_ORDER: dict[str, int] = {SOURCE_OTHER_OBJECTIVES: 0, SOURCE_GUIDANCE: 1, SOURCE_PRACTICE_RECORD: 2}

#: Engine error texts that mean "no ranking possible" (recommend.py and
#: recommender_service.assert_supported_family_indicator), matched as prefixes.
NO_EVIDENCE_PREFIX = "No field evidence"
UNSUPPORTED_MARKER = "is not supported for challenge"


# ---------------------------------------------------------------- belt zones
#: Ethiopian traditional altitude belts → three broad altitude groups. The
#: 12 belts in the training data (and the 15 in aez_belt_lookup.csv) are all
#: "<moisture> <belt>" with moisture in Dry / Moist / Wet.
BELT_GROUPS: dict[str, str] = {
    "Berha": "lowland",
    "Kolla": "lowland",
    "Weyna Dega": "midland",
    "Dega": "highland",
    "High Dega": "highland",
    "Wurch": "highland",
}
MOISTURE_CLASSES: tuple[str, ...] = ("Dry", "Moist", "Wet")


def parse_belt(belt: Any) -> tuple[str, str] | None:
    """``"Dry Weyna Dega"`` → ``("Dry", "midland")``; unknown → ``None``."""
    if not isinstance(belt, str) or " " not in belt.strip():
        return None
    moisture, _, rest = belt.strip().partition(" ")
    if moisture not in MOISTURE_CLASSES:
        return None
    group = BELT_GROUPS.get(rest.strip())
    return (moisture, group) if group else None


def zone_of(belt: Any) -> str | None:
    """Moisture zone key, e.g. ``"Dry-lowland"``; ``None`` when unparseable."""
    parsed = parse_belt(belt)
    return f"{parsed[0]}-{parsed[1]}" if parsed else None


# ------------------------------------------------------------ sufficiency
def candidate_counts(graph_query: Any, practice: str, indicator: str, belt: Any) -> dict[str, Any]:
    """Counts behind one (practice, indicator) pair relative to the user's belt.

    Plain counts of dataset rows from the graph's ``evidence_summary``. When
    the store predates P9 (no ``obs_by_belt``), belt presence is still known
    from ``aez_belts``; the in-belt / in-zone counts then report ``1`` for a
    present belt (the minimum consistent with presence) and
    ``belt_counts_exact`` says so — never a guessed larger number.
    """
    summary = graph_query.evidence_summary(practice, indicator)
    aez_belts = list(summary.get("aez_belts") or [])
    per_belt = {k: int(v) for k, v in (summary.get("obs_by_belt") or {}).items()}
    exact = bool(summary.get("belt_counts_exact", True)) and (bool(per_belt) or not aez_belts)
    zone = zone_of(belt)
    if exact:
        in_belt = per_belt.get(belt, 0) if isinstance(belt, str) else 0
        in_zone = sum(n for b, n in per_belt.items() if zone and zone_of(b) == zone)
    else:
        in_belt = 1 if belt in aez_belts else 0
        in_zone = 1 if zone and any(zone_of(b) == zone for b in aez_belts) else 0
    counts = summary.get("corpus_status") or {}
    return {
        "practice": practice,
        "n_studies": int(summary.get("n_studies") or 0),
        "n_obs": int(summary.get("n_obs") or 0),
        "n_obs_in_belt": int(in_belt),
        "n_obs_in_zone": int(in_zone),
        "aez_belts": aez_belts,
        "corpus_status": {k: int(counts.get(k, 0)) for k in ("full_text", "abstract", "none")},
        "belt_counts_exact": exact,
    }


def thresholds(settings: Any = None) -> dict[str, int]:
    s = settings or get_settings()
    return {
        "min_studies": int(s.evidence_min_studies),
        "min_obs": int(s.evidence_min_obs),
        "min_obs_in_zone": int(s.evidence_min_obs_in_zone),
    }


def decide_mode(
    top_rows: list[dict[str, Any]],
    *,
    engine_error: str | None,
    user_zone: str | None,
    limits: dict[str, int],
    graph_available: bool = True,
) -> tuple[Mode, list[dict[str, Any]]]:
    """The mode plus its reasons (catalog keys + params, no prose).

    ``top_rows`` are :func:`candidate_counts` rows for the engine's top-3
    practices (empty when the engine produced no ranking).
    """
    reasons: list[dict[str, Any]] = []
    if engine_error == "no_evidence":
        return KNOWLEDGE_LED, [{"key": "mode.reason.engine_no_evidence", "params": {}}]
    if engine_error == "unsupported":
        return KNOWLEDGE_LED, [{"key": "mode.reason.engine_unsupported", "params": {}}]
    if not graph_available:
        return MODEL_LED, [{"key": "mode.reason.graph_unavailable", "params": {}}]
    if top_rows and all(r["n_studies"] == 0 for r in top_rows):
        return KNOWLEDGE_LED, [{"key": "mode.reason.no_studies", "params": {}}]

    strong = [r for r in top_rows if r["n_studies"] >= limits["min_studies"] and r["n_obs"] >= limits["min_obs"]]
    in_zone = [r for r in top_rows if r["n_obs_in_zone"] >= limits["min_obs_in_zone"]]
    best = max(top_rows, key=lambda r: (r["n_studies"], r["n_obs"]), default=None)
    zone_label = user_zone or ""

    if strong:
        s = max(strong, key=lambda r: (r["n_studies"], r["n_obs"]))
        reasons.append({"key": "mode.reason.strong_evidence",
                        "params": {"practice": s["practice"], "n_studies": s["n_studies"], "n_obs": s["n_obs"]}})
    elif best is not None:
        reasons.append({"key": "mode.reason.thin_evidence",
                        "params": {"practice": best["practice"], "n_studies": best["n_studies"], "n_obs": best["n_obs"],
                                   "min_studies": limits["min_studies"], "min_obs": limits["min_obs"]}})
    if in_zone:
        z = max(in_zone, key=lambda r: r["n_obs_in_zone"])
        reasons.append({"key": "mode.reason.in_zone",
                        "params": {"practice": z["practice"], "n_obs_in_zone": z["n_obs_in_zone"], "zone": zone_label}})
    elif user_zone:
        reasons.append({"key": "mode.reason.other_zones_only", "params": {"zone": zone_label}})
    else:
        reasons.append({"key": "mode.reason.zone_unknown", "params": {}})

    if strong and in_zone:
        return MODEL_LED, reasons
    return HYBRID, reasons


def evidence_sufficiency(
    model: dict[str, Any] | None,
    practice_family: str,
    indicator: str,
    context: dict[str, Any] | None,
    graph_query: Any,
    *,
    engine_error: str | None = None,
    settings: Any = None,
) -> dict[str, Any]:
    """Per-candidate counts + the mode decision for one request."""
    limits = thresholds(settings)
    belt = (context or {}).get("aez_belt")
    user_zone = zone_of(belt)
    ranked = [r.get("practice") for r in ((model or {}).get("details") or {}).get("ranked") or []]
    ranked = [p for p in ranked if p]
    rows: list[dict[str, Any]] = []
    if graph_query is not None:
        for practice in ranked:
            try:
                rows.append(candidate_counts(graph_query, practice, indicator, belt))
            except Exception as exc:  # one bad practice must not sink the request
                logger.warning("candidate counts failed for %r (%s)", practice, exc)
    top_rows = rows[:3]
    for i, row in enumerate(rows):
        row["in_top3"] = i < 3
    mode, reasons = decide_mode(
        top_rows, engine_error=engine_error, user_zone=user_zone, limits=limits,
        graph_available=graph_query is not None,
    )
    return {
        "mode": mode,
        "reasons": reasons,
        "user_belt": belt if isinstance(belt, str) else None,
        "user_zone": user_zone,
        "thresholds": limits,
        "candidates": rows,
        "graph_available": graph_query is not None,
    }


# ------------------------------------------------------ knowledge candidates
def _ensure_repo_root_on_path() -> None:
    repo_root = get_settings().backend_root.parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))


def _decompose(practice: str) -> tuple[str, ...]:
    _ensure_repo_root_on_path()
    from rag.graph.practice_components import decompose

    return decompose(practice)


def _components_in_text(text: str) -> dict[str, int]:
    _ensure_repo_root_on_path()
    from rag.graph.component_keywords import components_in_text

    return components_in_text(text)


def _chunk_quality_score(text: str) -> float:
    _ensure_repo_root_on_path()
    from rag.ingest.quality import chunk_quality

    return float(chunk_quality(text)["score"])


def _query_text(practice_family: str, indicator: str, context: dict[str, Any] | None, crop_type: str | None) -> str:
    _ensure_repo_root_on_path()
    from rag.retrieve import build_query_text

    pseudo = {
        "query": {"practice_family": practice_family, "indicator": indicator, "crop_type": crop_type},
        "recommendations": [],
        "details": {"context": context or {}},
    }
    return build_query_text(pseudo)


def _context_classes(context: dict[str, Any] | None) -> dict[str, str]:
    _ensure_repo_root_on_path()
    from rag.graph.context_classes import context_to_classes

    return context_to_classes(context or {})


class _Candidate:
    """Accumulator for one component (or one practice record)."""

    def __init__(self, key: str, component: str | None, label: str) -> None:
        self.key = key
        self.component = component
        self.label = label
        self.sources: set[str] = set()
        self.practices: set[str] = set()
        self.other_objectives: dict[str, int] = {}
        self.documents: set[str] = set()
        self.n_passages = 0
        self.citations: list[dict[str, Any]] = []
        self.record: dict[str, Any] | None = None

    def add_citation(self, citation: dict[str, Any]) -> None:
        """Keep one row per distinct source; refuse a row nothing can cite (doctrine 2)."""
        key = citation_identity(citation)
        if key is None or any(citation_identity(c) == key for c in self.citations):
            return
        self.citations.append(citation)

    def support_key(self) -> tuple[int, int, int, int, str]:
        return (
            len(self.sources),
            len(self.documents),
            self.n_passages,
            -min((SOURCE_ORDER.get(s, 9) for s in self.sources), default=9),
            self.key,
        )


def _practices_with_component(pool: Iterable[str]) -> dict[str, list[str]]:
    by_component: dict[str, list[str]] = defaultdict(list)
    for practice in pool:
        for component in _decompose(practice):
            by_component[component].append(practice)
    return dict(by_component)


def graph_other_objective_candidates(
    graph_query: Any, pool: list[str], indicator: str, indicators: Iterable[str], seeds: list[str] | None = None,
) -> dict[str, _Candidate]:
    """Source 1 — practices of the family with evidence for OTHER indicators."""
    out: dict[str, _Candidate] = {}
    if graph_query is None:
        return out
    pool_set = set(pool)
    practices = list(pool)
    for seed in seeds or []:
        try:
            for rel in graph_query.related_practices(seed, k=10):
                if rel.get("practice") in pool_set and rel["practice"] not in practices:
                    practices.append(rel["practice"])
        except Exception as exc:
            logger.debug("related_practices failed for %r (%s)", seed, exc)
    for practice in practices:
        for other in indicators:
            if other == indicator:
                continue
            try:
                summary = graph_query.evidence_summary(practice, other)
            except Exception as exc:
                logger.debug("evidence_summary failed for %r/%r (%s)", practice, other, exc)
                continue
            n_studies = int(summary.get("n_studies") or 0)
            if n_studies == 0:
                continue
            for component in _decompose(practice):
                cand = out.setdefault(component, _Candidate(component, component, component))
                cand.sources.add(SOURCE_OTHER_OBJECTIVES)
                cand.practices.add(practice)
                cand.other_objectives[other] = max(cand.other_objectives.get(other, 0), n_studies)
                for study in (summary.get("studies") or [])[:2]:
                    # A dataset-only study (no ERA code, no title) is still a
                    # real, numbered provenance: it is cited by its dataset id.
                    cand.add_citation({
                        "tier": "evidence",
                        "era_code": study.get("era_code"),
                        "study_no": study.get("study_no"),
                        "title": study.get("title"),
                        "year": study.get("year"),
                        "doi": study.get("doi"),
                        "url": None,
                        "indicator": other,
                        "practice": practice,
                    })
                    key = study.get("era_code") or study.get("study_no") or study.get("title")
                    if key:
                        cand.documents.add(f"study:{key}")
    return out


def guidance_candidates(
    passages: list[dict[str, Any]], allowed_components: set[str], min_quality: float,
) -> tuple[dict[str, _Candidate], dict[str, int]]:
    """Source 2 — components mentioned in quality-filtered guidance passages."""
    out: dict[str, _Candidate] = {}
    funnel = {"retrieved": len(passages), "kept": 0, "with_component": 0}
    for chunk in passages:
        text = chunk.get("text") or ""
        if _chunk_quality_score(text) < min_quality:
            continue
        funnel["kept"] += 1
        mentions = {c: n for c, n in _components_in_text(text).items() if c in allowed_components}
        if not mentions:
            continue
        funnel["with_component"] += 1
        doc_key = chunk.get("url") or chunk.get("doi") or chunk.get("title") or chunk.get("chunk_id")
        for component in mentions:
            cand = out.setdefault(component, _Candidate(component, component, component))
            cand.sources.add(SOURCE_GUIDANCE)
            cand.n_passages += 1
            if doc_key:
                cand.documents.add(f"doc:{doc_key}")
            cand.add_citation({
                "tier": "guidance",
                "era_code": None,
                "title": chunk.get("title"),
                "year": chunk.get("year"),
                "doi": chunk.get("doi"),
                "url": chunk.get("url"),
                "snippet": text[:240],
                "chunk_id": chunk.get("chunk_id"),
            })
    return out, funnel


def practice_record_candidates(graph_query: Any, context: dict[str, Any] | None, k: int = 5) -> dict[str, _Candidate]:
    """Source 3 — WOCAT practice records from a comparable context (P6b-ii fills it)."""
    out: dict[str, _Candidate] = {}
    if graph_query is None:
        return out
    try:
        records = graph_query.similar_context_technologies(_context_classes(context), practice=None, k=k)
    except Exception as exc:
        logger.debug("similar_context_technologies failed (%s)", exc)
        return out
    for rec in records:
        if rec.get("synthetic"):
            continue
        wocat_id = rec.get("wocat_id")
        title = rec.get("title") or f"WOCAT {wocat_id}"
        key = f"record:{wocat_id}"
        cand = out.setdefault(key, _Candidate(key, None, title))
        cand.sources.add(SOURCE_PRACTICE_RECORD)
        cand.documents.add(key)
        cand.record = {"wocat_id": wocat_id, "country": rec.get("country"), "shared_context": rec.get("shared_context") or []}
        cand.add_citation({
            "tier": "practice",
            "era_code": None,
            "title": title,
            "year": None,
            "doi": None,
            "url": rec.get("url"),
            "wocat_id": wocat_id,
            "country": rec.get("country"),
            "licence": rec.get("licence"),
        })
    return out


def _merge(*groups: dict[str, _Candidate]) -> dict[str, _Candidate]:
    merged: dict[str, _Candidate] = {}
    for group in groups:
        for key, cand in group.items():
            if key not in merged:
                merged[key] = cand
                continue
            m = merged[key]
            m.sources |= cand.sources
            m.practices |= cand.practices
            m.documents |= cand.documents
            m.n_passages += cand.n_passages
            for ind, n in cand.other_objectives.items():
                m.other_objectives[ind] = max(m.other_objectives.get(ind, 0), n)
            for c in cand.citations:
                m.add_citation(c)
            m.record = m.record or cand.record
    return merged


def citation_identity(c: dict[str, Any]) -> str | None:
    """What makes a citation citable: ERA code, dataset study id, URL, WOCAT id or title."""
    for key in ("era_code", "study_no", "url", "wocat_id", "doi", "title"):
        if c.get(key):
            return f"{key}:{c[key]}"
    return None


def _number_citations(candidates: list[dict[str, Any]]) -> None:
    """Global ``ref`` per response: evidence [n], guidance [Gn], records [Wn].

    One number per distinct source (a study cited for two objectives keeps one
    number). A citation with no identity at all cannot be cited and is dropped
    (doctrine 2); a candidate left without citations is dropped by the caller.
    """
    counters = {"evidence": 0, "guidance": 0, "practice": 0}
    prefix = {"evidence": "", "guidance": "G", "practice": "W"}
    seen: dict[tuple[str, str], str] = {}
    for cand in candidates:
        kept: list[dict[str, Any]] = []
        for c in cand["citations"]:
            tier = c.get("tier") or "evidence"
            identity = citation_identity(c)
            if identity is None:
                continue
            ident = (tier, identity)
            if ident not in seen:
                counters[tier] += 1
                seen[ident] = f"{prefix[tier]}{counters[tier]}"
            c["ref"] = seen[ident]
            kept.append(c)
        cand["citations"] = kept


def rationale(cand: dict[str, Any], practice_family: str, indicator: str, language: str) -> tuple[dict[str, Any], str]:
    """Deterministic template rationale — citation metadata and counts only."""
    label = cand["label"]
    family = term(language, "family", practice_family)
    objective = term(language, "indicator", indicator)
    parts: list[str] = []
    params: dict[str, Any] = {"label": label}
    support = cand["support"]
    if SOURCE_GUIDANCE in cand["sources"]:
        params["n_docs"] = support["n_guidance_documents"]
        params["n_passages"] = support["n_passages"]
        parts.append(t(language, "kc.rationale.guidance", label=label, family=family, objective=objective,
                       n_docs=support["n_guidance_documents"], n_passages=support["n_passages"],
                       docs_word=t(language, "kc.document" if support["n_guidance_documents"] == 1 else "kc.documents")))
    if SOURCE_OTHER_OBJECTIVES in cand["sources"] and support["other_objectives"]:
        items = t(language, "kc.join").join(
            t(language, "kc.objective_item", objective=term(language, "indicator", ind), n=n,
              studies_word=t(language, "kc.study" if n == 1 else "kc.studies"))
            for ind, n in sorted(support["other_objectives"].items(), key=lambda kv: (-kv[1], kv[0]))
        )
        params["other_objectives"] = items
        parts.append(t(language, "kc.rationale.other_objectives", label=label, objectives=items))
    if SOURCE_PRACTICE_RECORD in cand["sources"]:
        country = (cand.get("record") or {}).get("country") or ""
        params["country"] = country
        parts.append(t(language, "kc.rationale.record", label=label, country=country))
    text = " ".join(parts)
    key = "kc.rationale.combined"
    return {"key": key, "params": params}, text


def knowledge_candidates(
    *,
    practice_family: str,
    indicator: str,
    context: dict[str, Any] | None,
    pool: list[str],
    indicators: Iterable[str],
    graph_query: Any = None,
    guidance_retriever: Any = None,
    seeds: list[str] | None = None,
    crop_type: str | None = None,
    language: str = "en",
    settings: Any = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Up to N knowledge candidates for one request, ranked by support.

    Returns ``(candidates, funnel)``. Candidates are keyed by canonical
    component (practice records by ``record:<id>``), carry the frozen
    practice strings of the family that contain the component, every source
    label, support counts, numbered citations and a template rationale in
    ``language``. A candidate with no citation is dropped (doctrine 2).
    """
    s = settings or get_settings()
    by_component = _practices_with_component(pool)
    allowed = set(by_component)
    funnel: dict[str, Any] = {"graph": 0, "guidance": {"retrieved": 0, "kept": 0, "with_component": 0}, "records": 0}

    graph_group = graph_other_objective_candidates(graph_query, pool, indicator, indicators, seeds)
    funnel["graph"] = len(graph_group)

    guidance_group: dict[str, _Candidate] = {}
    if guidance_retriever is not None:
        try:
            passages = guidance_retriever.retrieve(
                _query_text(practice_family, indicator, context, crop_type), k=int(s.guidance_candidates_k)
            )
            guidance_group, funnel["guidance"] = guidance_candidates(passages, allowed, float(s.guidance_min_quality))
        except Exception as exc:  # optional layer — degrade, never fail
            logger.warning("guidance candidate retrieval failed (%s)", exc)

    record_group = practice_record_candidates(graph_query, context)
    funnel["records"] = len(record_group)

    merged = _merge(graph_group, guidance_group, record_group)
    ranked = sorted(merged.values(), key=lambda c: c.support_key(), reverse=True)

    out: list[dict[str, Any]] = []
    for cand in ranked:
        if not cand.citations:
            continue  # cite or stay silent
        n_guidance_docs = sum(1 for d in cand.documents if d.startswith("doc:"))
        n_studies_docs = sum(1 for d in cand.documents if d.startswith("study:"))
        item = {
            "key": cand.key,
            "component": cand.component,
            "label": cand.label,
            # Every frozen practice of the family that contains the component,
            # not only the ones that supplied evidence.
            "practices": sorted(set(cand.practices) | set(by_component.get(cand.component or "", []))),
            "sources": sorted(cand.sources, key=lambda x: SOURCE_ORDER.get(x, 9)),
            "support": {
                "n_sources": len(cand.sources),
                "n_documents": len(cand.documents),
                "n_guidance_documents": n_guidance_docs,
                "n_studies": n_studies_docs,
                "n_passages": cand.n_passages,
                "other_objectives": dict(sorted(cand.other_objectives.items())),
            },
            "record": cand.record,
            "citations": [dict(c) for c in cand.citations],
        }
        item["rationale"], item["rationale_text"] = rationale(item, practice_family, indicator, language)
        out.append(item)
        if len(out) >= int(s.knowledge_candidates_max):
            break
    _number_citations(out)
    return out, funnel


_COUNT_RE = re.compile(r"\d+(?:\.\d+)?")


def rationale_numbers_are_counts(candidate: dict[str, Any]) -> bool:
    """Guard: every number in a rationale is one of the candidate's counts."""
    support = candidate.get("support") or {}
    allowed = {float(v) for v in support.values() if isinstance(v, (int, float))}
    allowed |= {float(v) for v in (support.get("other_objectives") or {}).values()}
    for tok in _COUNT_RE.findall(candidate.get("rationale_text") or ""):
        if float(tok) not in allowed:
            return False
    return True
