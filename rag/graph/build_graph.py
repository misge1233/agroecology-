#!/usr/bin/env python3
"""Build the AgroAdvisor-ET knowledge graph (Phase P6a).

Sources, in the order they are layered into the graph:

1. **WOCAT taxonomy** (``wocat_taxonomy``) — SLM groups, SLM measures,
   degradation types, context classes, on-site impact variables, all
   transcribed from the 2019 questionnaire.
2. **Indicator crosswalk** (``indicator_map``) — the 7 model indicators and
   their ``MEASURES`` edges onto QT §6.1 impact variables. Direction
   semantics come from ``recommend.DIRECTION``.
3. **The dataset** ``data/processed/CSA_ERA_final_model_ready.csv`` —
   families, practices, components, studies, AEZ belts, crop groups, and the
   ``REPORTS_EFFECT`` aggregates. These numbers are plain aggregations of the
   rows the ML model was trained on; nothing here is generated.
4. **The Tier-1 corpus** ``rag/corpus/manifest.jsonl`` + ``chunks.jsonl`` —
   enriches ``Study`` nodes with title/year/DOI, ``corpus_status`` and
   ``n_chunks``.
5. **The WOCAT crosswalk** ``docs/decisions/wocat_crosswalk_proposal.csv`` —
   ``MAPS_TO`` edges. Only rows the owner marked ``validated`` are admitted
   unless ``--include-proposed`` is passed (which tags them
   ``crosswalk_auto`` so they can never be mistaken for validated ones).
6. **WOCAT records** (``--wocat``) — normalized Technologies/Approaches.
   Empty in P6a apart from the hand-built fixtures.

Outputs (both deterministic and idempotent — running twice over unchanged
inputs produces byte-identical files):

* ``rag/graph/store/graph.json``         — node-link JSON
* ``rag/graph/store/graph_report.json``  — counts and coverage

Usage::

    python rag/graph/build_graph.py
    python rag/graph/build_graph.py --wocat rag/ingest/wocat/fixtures
    python rag/graph/build_graph.py --include-proposed
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from . import practice_components as pc
from . import wocat_taxonomy as wt
from .indicator_map import (
    INDICATOR_MAPPINGS,
    direction_map,
    direction_source,
)
from .schema import (
    CONTEXT_CLASS_KINDS,
    SCHEMA_VERSION,
    EdgeType,
    NodeType,
    add_edge,
    add_node,
    context_id,
    new_graph,
    node_id,
    to_node_link,
    validate_graph,
)

# The era_code join key is defined once, in the eval harness — wrap, never fork.
from rag.eval.build_queries import strip_era_prefix

GRAPH_DIR = Path(__file__).resolve().parent
REPO_ROOT = GRAPH_DIR.parents[1]

logger = logging.getLogger(__name__)

DATASET_PATH = REPO_ROOT / "data" / "processed" / "CSA_ERA_final_model_ready.csv"
MANIFEST_PATH = REPO_ROOT / "rag" / "corpus" / "manifest.jsonl"
CHUNKS_PATH = REPO_ROOT / "rag" / "corpus" / "chunks.jsonl"
CROSSWALK_PATH = REPO_ROOT / "docs" / "decisions" / "wocat_crosswalk_proposal.csv"
STORE_DIR = GRAPH_DIR / "store"

#: The dataset is the ERA-Ethiopia + CSA evidence base; every study is Ethiopian.
DATASET_COUNTRY = "Ethiopia"

#: Chunk ``source`` values that count as full text rather than abstract only.
FULL_TEXT_CHUNK_SOURCES = frozenset({"pdf", "xml"})

ROUND = 6


# --------------------------------------------------------------- input layer
def load_rows(path: Path) -> list[dict[str, str]]:
    """All dataset rows, keyed by the frozen column names."""
    if not path.exists():
        raise FileNotFoundError(f"dataset not found: {path}")
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    """Read a .jsonl file; an absent file degrades to an empty list."""
    if not path.exists():
        logger.warning("optional input missing, skipping: %s", path)
        return []
    records: list[dict[str, Any]] = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def chunk_stats(chunks: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """era_code -> {n_chunks, corpus_status} from the Tier-1 chunk file."""
    counts: dict[str, int] = defaultdict(int)
    sources: dict[str, set[str]] = defaultdict(set)
    for chunk in chunks:
        code = chunk.get("era_code")
        if not code:  # Tier-2 guidance chunks never carry an era_code
            continue
        counts[code] += 1
        sources[code].add(str(chunk.get("source", "")))
    return {
        code: {
            "n_chunks": n,
            "corpus_status": (
                "full_text" if sources[code] & FULL_TEXT_CHUNK_SOURCES else "abstract"
            ),
        }
        for code, n in counts.items()
    }


def load_crosswalk(path: Path, include_proposed: bool) -> list[dict[str, str]]:
    """Crosswalk rows admitted into the graph.

    A row is admitted when ``owner_decision`` (preferred) or ``status`` says
    ``validated``. ``--include-proposed`` additionally admits ``proposed``
    rows, which are tagged ``crosswalk_auto`` so the two can never be
    confused. Rows marked ``rejected`` are never admitted.
    """
    if not path.exists():
        logger.warning(
            "crosswalk not found (%s) — the graph will have no MAPS_TO edges; "
            "run rag/graph/crosswalk/propose_crosswalk.py and have the owner "
            "validate it",
            path,
        )
        return []
    with open(path, encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    admitted: list[dict[str, str]] = []
    for row in rows:
        decision = (row.get("owner_decision") or "").strip().lower()
        status = decision or (row.get("status") or "").strip().lower()
        if status == "validated":
            row["_status"] = "validated"
            row["_provenance"] = "crosswalk_validated"
            admitted.append(row)
        elif status == "proposed" and include_proposed:
            row["_status"] = "proposed"
            row["_provenance"] = "crosswalk_auto"
            admitted.append(row)
    return admitted


def _split_codes(value: str) -> list[str]:
    """``"A1;A2 ; A3"`` -> ``['A1', 'A2', 'A3']``."""
    return [part.strip() for part in str(value or "").replace(",", ";").split(";") if part.strip()]


# ----------------------------------------------------------- taxonomy layer
def add_taxonomy(graph) -> None:
    """SLM groups/measures, degradation types, context classes, impact vars."""
    for group in wt.SLM_GROUPS:
        add_node(graph, NodeType.SLM_GROUP, group, source_doc="QT 2019 §3.5")
    for measure in wt.SLM_MEASURES:
        add_node(
            graph, NodeType.SLM_MEASURE, measure.code,
            label=f"{measure.code}: {measure.label}",
            category=measure.category, measure_label=measure.label,
            examples=measure.examples, sub_options=list(measure.sub_options),
            source_doc="QT 2019 §3.6",
        )
    for degradation in wt.DEGRADATION_TYPES:
        add_node(
            graph, NodeType.DEGRADATION_TYPE, degradation.code,
            label=f"{degradation.code}: {degradation.label}",
            category=degradation.category,
            category_label=degradation.category_label,
            source_doc="QT 2019 §3.7",
        )
    for kind in CONTEXT_CLASS_KINDS:
        for value in wt.CONTEXT_CLASSES[kind]:
            nid = context_id(kind, value)
            if not graph.has_node(nid):
                graph.add_node(
                    nid, type=NodeType.CONTEXT_CLASS.value,
                    label=f"{kind}: {value}", kind=kind, value=value,
                    source_doc="QT 2019 §5.1-§5.3",
                )
    for variable in wt.ON_SITE_IMPACT_VARIABLES:
        add_node(
            graph, NodeType.IMPACT_VARIABLE, variable.name,
            category=variable.category, subcategory=variable.subcategory,
            negative_pole=variable.negative_pole,
            positive_pole=variable.positive_pole,
            good_direction=variable.good_direction,
            source_note=variable.source_note, source_doc="QT 2019 §6.1",
        )


def add_indicators(graph, indicator_rows: dict[str, int]) -> None:
    """Indicator nodes and their MEASURES edges onto QT impact variables."""
    for indicator, direction in sorted(direction_map().items()):
        add_node(
            graph, NodeType.INDICATOR, indicator,
            direction_good=direction, n_rows=indicator_rows.get(indicator, 0),
        )
    for mapping in INDICATOR_MAPPINGS:
        src = node_id(NodeType.INDICATOR, mapping.indicator)
        for role, name in (
            ("primary", mapping.wocat_variable),
            *(("secondary", s) for s in mapping.secondary),
        ):
            add_edge(
                graph, src, EdgeType.MEASURES,
                node_id(NodeType.IMPACT_VARIABLE, name),
                source="wocat_taxonomy",
                direction_good=mapping.direction_good,
                proxy=bool(mapping.proxy), role=role, rationale=mapping.rationale,
            )


# ------------------------------------------------------------ dataset layer
def add_dataset(graph, rows: list[dict[str, str]]) -> dict[str, Any]:
    """Families, practices, components, studies, belts, crop groups, effects."""
    stats: dict[str, Any] = {}
    family_rows: dict[str, int] = defaultdict(int)
    practice_rows: dict[str, int] = defaultdict(int)
    component_rows: dict[str, int] = defaultdict(int)
    indicator_rows: dict[str, int] = defaultdict(int)
    practice_family: dict[str, str] = {}
    study_source: dict[str, str] = {}
    raw_tokens: set[str] = set()
    unknown_tokens: set[str] = set()

    for row in rows:
        family_rows[row["practice_family"]] += 1
        practice_rows[row["CSA_practices"]] += 1
        indicator_rows[row["Indicator"]] += 1
        practice_family[row["CSA_practices"]] = row["practice_family"]
        study_source[row["Study_No_"]] = row["source"]

    for practice in practice_rows:
        for token in pc.split_practice(practice):
            raw_tokens.add(token)
            if not pc.is_known(token):
                unknown_tokens.add(token)
        for component in pc.decompose(practice):
            component_rows[component] += practice_rows[practice]

    # ---- nodes
    add_node(graph, NodeType.COUNTRY, DATASET_COUNTRY)
    for family, n in sorted(family_rows.items()):
        add_node(graph, NodeType.PRACTICE_FAMILY, family, n_rows=n)
    for belt in sorted({r["aez_belt"] for r in rows}):
        add_node(graph, NodeType.AEZ_BELT, belt)
    for crop_group in sorted({r["Crop_group"] for r in rows}):
        add_node(graph, NodeType.CROP_GROUP, crop_group)

    component_aliases = pc.alias_clusters(raw_tokens)
    for component, n in sorted(component_rows.items()):
        add_node(
            graph, NodeType.PRACTICE_COMPONENT, component, n_rows=n,
            aliases=component_aliases.get(component, [component]),
            known=pc.is_known(component),
        )

    for practice, n in sorted(practice_rows.items()):
        family = practice_family[practice]
        components = pc.decompose(practice)
        pid = add_node(
            graph, NodeType.PRACTICE, practice, n_rows=n, practice_family=family,
            n_components=len(components),
        )
        provenance = "era_rows" if any(
            r["source"] == "ERA" for r in rows if r["CSA_practices"] == practice
        ) else "csa_rows"
        add_edge(
            graph, pid, EdgeType.IN_FAMILY,
            node_id(NodeType.PRACTICE_FAMILY, family), source=provenance,
        )
        for position, component in enumerate(components):
            add_edge(
                graph, pid, EdgeType.COMPOSED_OF,
                node_id(NodeType.PRACTICE_COMPONENT, component),
                source=provenance, position=position,
            )

    for study, data_source in sorted(study_source.items()):
        add_node(
            graph, NodeType.STUDY, study, data_source=data_source,
            era_code=strip_era_prefix(study) if data_source == "ERA" else None,
            corpus_status="none", n_chunks=0,
        )
        add_edge(
            graph, node_id(NodeType.STUDY, study), EdgeType.APPLIED_IN,
            node_id(NodeType.COUNTRY, DATASET_COUNTRY),
            source="era_rows" if data_source == "ERA" else "csa_rows",
        )

    # ---- REPORTS_EFFECT: one edge per (study, practice, indicator)
    groups: dict[tuple[str, str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        groups[(row["Study_No_"], row["CSA_practices"], row["Indicator"])].append(row)
    for (study, practice, indicator), group in sorted(groups.items()):
        values = [float(r["log_response_ratio"]) for r in group]
        add_edge(
            graph, node_id(NodeType.STUDY, study), EdgeType.REPORTS_EFFECT,
            node_id(NodeType.PRACTICE, practice),
            source="era_rows" if study_source[study] == "ERA" else "csa_rows",
            key_suffix=indicator,
            indicator=indicator,
            n_obs=len(values),
            mean_log_rr=round(statistics.fmean(values), ROUND),
            median_log_rr=round(statistics.median(values), ROUND),
            share_positive=round(sum(1 for v in values if v > 0) / len(values), ROUND),
            aez_belts=sorted({r["aez_belt"] for r in group}),
            crop_groups=sorted({r["Crop_group"] for r in group}),
            # P9: plain per-belt observation counts of the same rows, so the
            # advisory can say how much of a practice's evidence for THIS
            # indicator was measured in the user's belt / moisture zone.
            obs_by_belt=dict(sorted(Counter(r["aez_belt"] for r in group).items())),
        )

    # ---- STUDIED_IN: one edge per (study, belt)
    belts: dict[tuple[str, str], int] = defaultdict(int)
    for row in rows:
        belts[(row["Study_No_"], row["aez_belt"])] += 1
    for (study, belt), n in sorted(belts.items()):
        add_edge(
            graph, node_id(NodeType.STUDY, study), EdgeType.STUDIED_IN,
            node_id(NodeType.AEZ_BELT, belt),
            source="era_rows" if study_source[study] == "ERA" else "csa_rows",
            key_suffix=belt, n_obs=n,
        )

    stats.update(
        n_rows=len(rows),
        n_practices=len(practice_rows),
        n_components=len(component_rows),
        n_raw_component_tokens=len(raw_tokens),
        unknown_component_tokens=sorted(unknown_tokens),
        alias_clusters=component_aliases,
        indicator_rows=dict(sorted(indicator_rows.items())),
    )
    return stats


def enrich_studies(graph, manifest: list[dict[str, Any]], chunks_by_code: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Add title/year/DOI, corpus_status and n_chunks to Study nodes."""
    by_code = {record["era_code"]: record for record in manifest}
    matched = with_chunks = full_text = 0
    for nid, attrs in graph.nodes(data=True):
        if attrs.get("type") != NodeType.STUDY.value:
            continue
        code = attrs.get("era_code")
        if not code:
            continue
        record = by_code.get(code)
        if record:
            matched += 1
            attrs.update(
                title=record.get("title"),
                year=record.get("year"),
                doi=record.get("doi"),
                journal=record.get("container") or record.get("journal"),
                oa_status=record.get("oa_status"),
                manifest_source="manifest",
            )
        stats = chunks_by_code.get(code)
        if stats:
            with_chunks += 1
            attrs["n_chunks"] = stats["n_chunks"]
            attrs["corpus_status"] = stats["corpus_status"]
            if stats["corpus_status"] == "full_text":
                full_text += 1
    return {
        "studies_matched_to_manifest": matched,
        "studies_with_chunks": with_chunks,
        "studies_with_full_text": full_text,
    }


# ---------------------------------------------------------- crosswalk layer
def add_crosswalk(graph, rows: list[dict[str, str]]) -> dict[str, Any]:
    """MAPS_TO edges from component to SLM measures and SLM groups."""
    added = skipped_unknown_component = skipped_unknown_target = 0
    for row in rows:
        component = (row.get("component") or "").strip()
        src = node_id(NodeType.PRACTICE_COMPONENT, component)
        if not graph.has_node(src):
            skipped_unknown_component += 1
            continue
        confidence = row.get("confidence") or ""
        try:
            confidence_value: float | str = round(float(confidence), 3)
        except (TypeError, ValueError):
            confidence_value = str(confidence)
        for code in _split_codes(row.get("proposed_measures", "")):
            target = node_id(NodeType.SLM_MEASURE, code)
            if not graph.has_node(target):
                skipped_unknown_target += 1
                continue
            add_edge(
                graph, src, EdgeType.MAPS_TO, target, source=row["_provenance"],
                confidence=confidence_value, status=row["_status"],
                rationale=row.get("rationale", ""),
                owner_note=row.get("owner_note", ""),
            )
            added += 1
        for group in _split_codes(row.get("proposed_groups", "")):
            target = node_id(NodeType.SLM_GROUP, group)
            if not graph.has_node(target):
                skipped_unknown_target += 1
                continue
            add_edge(
                graph, src, EdgeType.MAPS_TO, target, source=row["_provenance"],
                confidence=confidence_value, status=row["_status"],
                rationale=row.get("rationale", ""),
                owner_note=row.get("owner_note", ""),
            )
            added += 1
    return {
        "maps_to_edges": added,
        "crosswalk_rows_admitted": len(rows),
        "crosswalk_skipped_unknown_component": skipped_unknown_component,
        "crosswalk_skipped_unknown_target": skipped_unknown_target,
    }


# -------------------------------------------------------------- WOCAT layer
def add_wocat_records(graph, records: list[dict[str, Any]]) -> dict[str, Any]:
    """Technology/Approach nodes and their record edges.

    ``records`` are normalized dicts as written by
    ``rag/ingest/wocat/normalize_wocat.py`` (fixtures in P6a, the research
    data export in P6b). Edge provenance follows each record's
    ``provenance`` field.
    """
    technologies = approaches = impacts = contexts = 0
    for record in records:
        provenance = record.get("provenance", "wocat_fixture")
        record_type = record.get("record_type", "technology")
        wocat_id = str(record["wocat_id"])
        country = record.get("country") or ""
        if record_type == "approach":
            approaches += 1
            nid = add_node(
                graph, NodeType.APPROACH, wocat_id,
                label=record.get("title", wocat_id), wocat_id=wocat_id,
                country=country, region=record.get("region"),
                licence=record.get("licence"), url=record.get("url"),
                compiler=record.get("compiler"), synthetic=bool(record.get("synthetic")),
                short_description=record.get("short_description"),
            )
        else:
            technologies += 1
            nid = add_node(
                graph, NodeType.TECHNOLOGY, wocat_id,
                label=record.get("title", wocat_id), wocat_id=wocat_id,
                country=country, region=record.get("region"),
                licence=record.get("licence"), url=record.get("url"),
                compiler=record.get("compiler"), synthetic=bool(record.get("synthetic")),
                short_description=record.get("short_description"),
                land_use=record.get("land_use") or [],
                water_supply=record.get("water_supply"),
                rainfall_mm=record.get("rainfall_mm"),
                landform=record.get("landform") or [],
                cost_benefit=record.get("cost_benefit") or {},
                adoption=record.get("adoption") or {},
                strengths=record.get("strengths") or [],
                weaknesses=record.get("weaknesses") or [],
                activities=record.get("activities") or [],
                costs=record.get("costs") or {},
                references=record.get("references") or [],
            )
        if country:
            add_node(graph, NodeType.COUNTRY, country)
            add_edge(graph, nid, EdgeType.APPLIED_IN,
                     node_id(NodeType.COUNTRY, country), source=provenance)
        if record_type == "approach":
            continue

        for code in record.get("measures") or []:
            target = node_id(NodeType.SLM_MEASURE, str(code).strip())
            if graph.has_node(target):
                add_edge(graph, nid, EdgeType.USES_MEASURE, target,
                         source=provenance, key_suffix=str(code).strip())
            else:
                logger.warning("%s: unknown SLM measure %r", wocat_id, code)
        for group in record.get("slm_groups") or []:
            target = node_id(NodeType.SLM_GROUP, str(group).strip())
            if graph.has_node(target):
                add_edge(graph, nid, EdgeType.IN_GROUP, target,
                         source=provenance, key_suffix=str(group).strip())
            else:
                logger.warning("%s: unknown SLM group %r", wocat_id, group)
        for code in record.get("degradation") or []:
            target = node_id(NodeType.DEGRADATION_TYPE, str(code).strip())
            if graph.has_node(target):
                add_edge(graph, nid, EdgeType.ADDRESSES, target,
                         source=provenance, key_suffix=str(code).strip())
            else:
                logger.warning("%s: unknown degradation type %r", wocat_id, code)
        for kind, values in (record.get("context") or {}).items():
            if kind not in CONTEXT_CLASS_KINDS:
                logger.warning("%s: context kind %r is not a graph node kind",
                               wocat_id, kind)
                continue
            for value in values:
                target = context_id(kind, value)
                if graph.has_node(target):
                    add_edge(graph, nid, EdgeType.HAS_CONTEXT, target,
                             source=provenance, key_suffix=f"{kind}={value}", kind=kind)
                    contexts += 1
                else:
                    logger.warning("%s: unknown %s value %r", wocat_id, kind, value)
        for variable, rating in (record.get("impacts") or {}).items():
            target = node_id(NodeType.IMPACT_VARIABLE, variable)
            key = wt.normalize_rating(str(rating))
            if not graph.has_node(target) or key is None:
                logger.warning("%s: unusable impact %r=%r", wocat_id, variable, rating)
                continue
            add_edge(
                graph, nid, EdgeType.REPORTS_IMPACT, target, source=provenance,
                key_suffix=variable, rating=key,
                rating_index=wt.IMPACT_RATING_KEYS.index(key),
                good_direction=wt.IMPACT_BY_NAME[variable].good_direction,
            )
            impacts += 1
        for approach_id in record.get("linked_approaches") or []:
            target = node_id(NodeType.APPROACH, str(approach_id).strip())
            if not graph.has_node(target):
                add_node(graph, NodeType.APPROACH, str(approach_id).strip(),
                         wocat_id=str(approach_id).strip(), country=country,
                         licence=record.get("licence"), url=None)
            add_edge(graph, nid, EdgeType.LINKED_APPROACH, target,
                     source=provenance, key_suffix=str(approach_id).strip())
    return {
        "technologies": technologies,
        "approaches": approaches,
        "reports_impact_edges": impacts,
        "has_context_edges": contexts,
    }


def load_wocat(path: Path | None, allow_synthetic: bool = False) -> list[dict[str, Any]]:
    """Load WOCAT records from a .jsonl file or a fixture directory.

    Every record is passed through ``rag.ingest.wocat.schema.parse_record``
    before it reaches the graph, so raw hand-written fixtures and the
    already-normalized ``technologies.jsonl`` behave identically: controlled
    vocabularies are normalized to their questionnaire spelling and anything
    outside them is dropped with a warning rather than inserted as an
    invented code.

    **Records flagged ``synthetic: true`` are refused** unless
    ``allow_synthetic`` is set (P6a review decision 2). The fixture directory
    keeps one synthetic Technology so the context-similarity code path can be
    tested; it must never reach a build that feeds the app or an evaluation.
    """
    if path is None:
        return []
    if not path.exists():
        logger.warning("--wocat path missing, skipping: %s", path)
        return []

    raw: list[dict[str, Any]] = []
    if path.is_file():
        if path.suffix == ".jsonl":
            raw = load_jsonl(path)
        else:
            raw = [json.loads(path.read_text(encoding="utf-8"))]
    else:
        for child in sorted(path.iterdir()):
            if child.suffix == ".jsonl":
                raw.extend(load_jsonl(child))
            elif child.suffix == ".json":
                raw.append(json.loads(child.read_text(encoding="utf-8")))

    try:
        from rag.ingest.wocat.schema import parse_record
    except ImportError as exc:  # pydantic absent: the core graph still builds
        logger.error(
            "--wocat needs the WOCAT record schema (%s); install pydantic>=2 "
            "(rag/requirements.txt). Skipping %d record(s).", exc, len(raw)
        )
        return []

    records: list[dict[str, Any]] = []
    refused: list[str] = []
    for payload in raw:
        try:
            record = parse_record(payload).model_dump(mode="json")
        except Exception as exc:
            logger.error("skipping WOCAT record %r: %s", payload.get("wocat_id"), exc)
            continue
        if record.get("synthetic") and not allow_synthetic:
            refused.append(str(record.get("wocat_id")))
            continue
        records.append(record)
    if refused:
        logger.warning(
            "refused %d SYNTHETIC record(s) (%s) — they are test scaffolding, "
            "not WOCAT data; pass --allow-synthetic only when building a graph "
            "for tests", len(refused), ", ".join(refused),
        )
    if allow_synthetic and any(r.get("synthetic") for r in records):
        logger.warning(
            "--allow-synthetic: this graph CONTAINS synthetic records and must "
            "not be used for the app or for any evaluation"
        )
    return records


# ------------------------------------------------------------------- driver
def _relative(path: Path) -> str:
    """Repo-relative path for the report, or the absolute one if outside it."""
    try:
        return str(Path(path).resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def build(
    dataset_path: Path = DATASET_PATH,
    manifest_path: Path = MANIFEST_PATH,
    chunks_path: Path = CHUNKS_PATH,
    crosswalk_path: Path = CROSSWALK_PATH,
    wocat_path: Path | None = None,
    include_proposed: bool = False,
    allow_synthetic: bool = False,
):
    """Build the graph and its report. Returns ``(graph, report)``."""
    graph = new_graph()
    rows = load_rows(dataset_path)

    add_taxonomy(graph)
    dataset_stats = add_dataset(graph, rows)
    add_indicators(graph, dataset_stats["indicator_rows"])
    corpus_stats = enrich_studies(
        graph, load_jsonl(manifest_path), chunk_stats(load_jsonl(chunks_path))
    )
    crosswalk_stats = add_crosswalk(
        graph, load_crosswalk(crosswalk_path, include_proposed)
    )
    wocat_stats = add_wocat_records(
        graph, load_wocat(wocat_path, allow_synthetic)
    )

    node_counts: dict[str, int] = defaultdict(int)
    for _, attrs in graph.nodes(data=True):
        node_counts[attrs["type"]] += 1
    edge_counts: dict[str, int] = defaultdict(int)
    for _, _, attrs in graph.edges(data=True):
        edge_counts[attrs["type"]] += 1
    provenance_counts: dict[str, int] = defaultdict(int)
    for _, _, attrs in graph.edges(data=True):
        provenance_counts[attrs["source"]] += 1

    practices_with_study = len({
        dst for _, dst, attrs in graph.edges(data=True)
        if attrs["type"] == EdgeType.REPORTS_EFFECT.value
    })
    components_mapped = len({
        src for src, _, attrs in graph.edges(data=True)
        if attrs["type"] == EdgeType.MAPS_TO.value
    })

    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "inputs": {
            "dataset": _relative(dataset_path),
            "manifest": _relative(manifest_path),
            "chunks": _relative(chunks_path),
            "crosswalk": _relative(crosswalk_path),
            "wocat": _relative(wocat_path) if wocat_path else None,
            "include_proposed": include_proposed,
            "allow_synthetic": allow_synthetic,
        },
        "direction_source": direction_source(),
        "nodes_total": graph.number_of_nodes(),
        "edges_total": graph.number_of_edges(),
        "nodes_by_type": dict(sorted(node_counts.items())),
        "edges_by_type": dict(sorted(edge_counts.items())),
        "edges_by_provenance": dict(sorted(provenance_counts.items())),
        "coverage": {
            "practices": dataset_stats["n_practices"],
            "practices_with_evidence": practices_with_study,
            "components": dataset_stats["n_components"],
            "components_mapped_to_wocat": components_mapped,
            **corpus_stats,
            **crosswalk_stats,
        },
        "components": {
            "raw_tokens": dataset_stats["n_raw_component_tokens"],
            "canonical": dataset_stats["n_components"],
            "alias_clusters": dataset_stats["alias_clusters"],
            "unknown_tokens": dataset_stats["unknown_component_tokens"],
        },
        "wocat": wocat_stats,
        "validation": validate_graph(graph),
    }
    return graph, report


def write_store(graph, report: dict[str, Any], out_dir: Path) -> tuple[Path, Path]:
    """Write ``graph.json`` and ``graph_report.json``; return their paths."""
    out_dir.mkdir(parents=True, exist_ok=True)
    graph_path = out_dir / "graph.json"
    report_path = out_dir / "graph_report.json"
    graph_path.write_text(
        json.dumps(to_node_link(graph), indent=1, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    report_path.write_text(
        json.dumps(report, indent=1, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return graph_path, report_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--dataset", type=Path, default=DATASET_PATH)
    parser.add_argument("--manifest", type=Path, default=MANIFEST_PATH)
    parser.add_argument("--chunks", type=Path, default=CHUNKS_PATH)
    parser.add_argument("--crosswalk", type=Path, default=CROSSWALK_PATH)
    parser.add_argument(
        "--wocat", type=Path, default=None,
        help="normalized WOCAT records: a .jsonl file or a directory of them",
    )
    parser.add_argument(
        "--include-proposed", action="store_true",
        help="also admit status=proposed crosswalk rows (tagged crosswalk_auto)",
    )
    parser.add_argument(
        "--allow-synthetic", action="store_true",
        help="admit records flagged synthetic:true — TESTS ONLY; such a graph "
             "must never feed the app or an evaluation",
    )
    parser.add_argument("--out-dir", type=Path, default=STORE_DIR)
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    graph, report = build(
        args.dataset, args.manifest, args.chunks, args.crosswalk,
        args.wocat, args.include_proposed, args.allow_synthetic,
    )
    graph_path, report_path = write_store(graph, report, args.out_dir)
    logger.info("graph  -> %s (%d nodes, %d edges)",
                graph_path, report["nodes_total"], report["edges_total"])
    logger.info("report -> %s", report_path)
    if report["validation"]:
        for problem in report["validation"][:20]:
            logger.error("schema violation: %s", problem)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
