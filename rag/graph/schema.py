"""Node and edge contract for the AgroAdvisor-ET knowledge graph (P6a).

The graph is a ``networkx.MultiDiGraph`` serialized as node-link JSON. This
module is the single statement of what may appear in it; ``build_graph.py``
constructs only these types and :func:`validate_graph` rejects anything else.

Two rules are enforced here rather than left to convention:

1. **Every edge carries a ``source``** from :data:`PROVENANCE_SOURCES`, so
   any downstream claim can be traced to the rows, manifest, questionnaire,
   crosswalk or WOCAT record it came from.
2. **Numbers on edges are aggregates, never generations.** The only numeric
   edge attributes are on ``REPORTS_EFFECT`` and ``REPORTS_IMPACT``;
   ``REPORTS_EFFECT`` holds plain aggregations of dataset rows (the ML
   model's own evidence base) and ``REPORTS_IMPACT`` holds the rating a
   WOCAT compiler recorded. Neither is produced by a language model
   (CLAUDE.md doctrine 1).

Node ids are ``"<NodeType>:<key>"`` so the id space of the types is disjoint
and the graph round-trips through JSON without a separate index.
"""
from __future__ import annotations

from enum import StrEnum
from typing import Any

import networkx as nx

SCHEMA_VERSION = "p6a.1"


class NodeType(StrEnum):
    """Every node kind the graph may contain."""

    PRACTICE_FAMILY = "PracticeFamily"
    PRACTICE = "Practice"
    PRACTICE_COMPONENT = "PracticeComponent"
    INDICATOR = "Indicator"
    STUDY = "Study"
    AEZ_BELT = "AEZBelt"
    CROP_GROUP = "CropGroup"
    COUNTRY = "Country"
    SLM_GROUP = "SLMGroup"
    SLM_MEASURE = "SLMMeasure"
    DEGRADATION_TYPE = "DegradationType"
    CONTEXT_CLASS = "ContextClass"
    IMPACT_VARIABLE = "ImpactVariable"
    TECHNOLOGY = "Technology"
    APPROACH = "Approach"
    GUIDANCE_DOC = "GuidanceDoc"


class EdgeType(StrEnum):
    """Every edge kind the graph may contain."""

    IN_FAMILY = "IN_FAMILY"
    COMPOSED_OF = "COMPOSED_OF"
    REPORTS_EFFECT = "REPORTS_EFFECT"
    STUDIED_IN = "STUDIED_IN"
    MEASURES = "MEASURES"
    MAPS_TO = "MAPS_TO"
    # WOCAT practice-record edges: defined now, populated from the export in P6b
    # (and from the hand-built fixtures in P6a).
    USES_MEASURE = "USES_MEASURE"
    IN_GROUP = "IN_GROUP"
    ADDRESSES = "ADDRESSES"
    APPLIED_IN = "APPLIED_IN"
    HAS_CONTEXT = "HAS_CONTEXT"
    REPORTS_IMPACT = "REPORTS_IMPACT"
    LINKED_APPROACH = "LINKED_APPROACH"


#: Allowed values of the mandatory ``source`` attribute on every edge.
PROVENANCE_SOURCES: frozenset[str] = frozenset(
    {
        "era_rows",            # aggregated from ERA-source dataset rows
        "csa_rows",            # aggregated from CSA-source dataset rows
        "manifest",            # rag/corpus/manifest.jsonl + chunks.jsonl
        "wocat_taxonomy",      # transcribed from the QT (2019)
        "crosswalk_auto",      # rule/LLM proposal, NOT admitted to the graph
        "crosswalk_validated",  # owner-validated crosswalk row
        "wocat_fixture",       # hand-built fixture record
        "wocat_export",        # the WOCAT research data export (P6b)
    }
)

#: ``ContextClass`` node kinds materialized in the graph. These are the seven
#: QT §5.1-§5.3 vocabularies named in the P6a brief; ``landform`` is a real QT
#: vocabulary too (see ``wocat_taxonomy.CONTEXT_CLASSES``) but is kept as a
#: Technology attribute rather than a node — see ``rag/graph/README.md``.
CONTEXT_CLASS_KINDS: tuple[str, ...] = (
    "rainfall_band",
    "agroclimatic_zone",
    "slope_class",
    "altitude_zone",
    "soil_texture",
    "soil_depth",
    "topsoil_om",
)

#: Corpus coverage of a ``Study`` node.
CORPUS_STATUSES: frozenset[str] = frozenset({"full_text", "abstract", "none"})

#: Lifecycle of a ``MAPS_TO`` crosswalk row.
CROSSWALK_STATUSES: frozenset[str] = frozenset({"proposed", "validated", "rejected"})

#: edge type -> (allowed source node types, allowed target node types).
EDGE_ENDPOINTS: dict[EdgeType, tuple[frozenset[NodeType], frozenset[NodeType]]] = {
    EdgeType.IN_FAMILY: (
        frozenset({NodeType.PRACTICE}),
        frozenset({NodeType.PRACTICE_FAMILY}),
    ),
    EdgeType.COMPOSED_OF: (
        frozenset({NodeType.PRACTICE}),
        frozenset({NodeType.PRACTICE_COMPONENT}),
    ),
    EdgeType.REPORTS_EFFECT: (
        frozenset({NodeType.STUDY}),
        frozenset({NodeType.PRACTICE}),
    ),
    EdgeType.STUDIED_IN: (
        frozenset({NodeType.STUDY}),
        frozenset({NodeType.AEZ_BELT}),
    ),
    EdgeType.MEASURES: (
        frozenset({NodeType.INDICATOR}),
        frozenset({NodeType.IMPACT_VARIABLE}),
    ),
    EdgeType.MAPS_TO: (
        frozenset({NodeType.PRACTICE_COMPONENT}),
        frozenset({NodeType.SLM_MEASURE, NodeType.SLM_GROUP}),
    ),
    EdgeType.USES_MEASURE: (
        frozenset({NodeType.TECHNOLOGY}),
        frozenset({NodeType.SLM_MEASURE}),
    ),
    EdgeType.IN_GROUP: (
        frozenset({NodeType.TECHNOLOGY}),
        frozenset({NodeType.SLM_GROUP}),
    ),
    EdgeType.ADDRESSES: (
        frozenset({NodeType.TECHNOLOGY}),
        frozenset({NodeType.DEGRADATION_TYPE}),
    ),
    EdgeType.APPLIED_IN: (
        frozenset({NodeType.TECHNOLOGY, NodeType.APPROACH, NodeType.STUDY}),
        frozenset({NodeType.COUNTRY}),
    ),
    EdgeType.HAS_CONTEXT: (
        frozenset({NodeType.TECHNOLOGY}),
        frozenset({NodeType.CONTEXT_CLASS}),
    ),
    EdgeType.REPORTS_IMPACT: (
        frozenset({NodeType.TECHNOLOGY}),
        frozenset({NodeType.IMPACT_VARIABLE}),
    ),
    EdgeType.LINKED_APPROACH: (
        frozenset({NodeType.TECHNOLOGY}),
        frozenset({NodeType.APPROACH}),
    ),
}

#: edge type -> attribute names that must be present (besides ``source``).
EDGE_REQUIRED_ATTRS: dict[EdgeType, tuple[str, ...]] = {
    EdgeType.IN_FAMILY: (),
    EdgeType.COMPOSED_OF: ("position",),
    EdgeType.REPORTS_EFFECT: (
        "indicator", "n_obs", "mean_log_rr", "median_log_rr", "share_positive",
        "aez_belts", "crop_groups",
    ),
    EdgeType.STUDIED_IN: ("n_obs",),
    EdgeType.MEASURES: ("direction_good", "proxy"),
    EdgeType.MAPS_TO: ("confidence", "status"),
    EdgeType.USES_MEASURE: (),
    EdgeType.IN_GROUP: (),
    EdgeType.ADDRESSES: (),
    EdgeType.APPLIED_IN: (),
    EdgeType.HAS_CONTEXT: ("kind",),
    EdgeType.REPORTS_IMPACT: ("rating", "rating_index", "good_direction"),
    EdgeType.LINKED_APPROACH: (),
}

#: node type -> attribute names that must be present (besides ``type``/``label``).
NODE_REQUIRED_ATTRS: dict[NodeType, tuple[str, ...]] = {
    NodeType.PRACTICE_FAMILY: ("n_rows",),
    NodeType.PRACTICE: ("n_rows", "practice_family"),
    NodeType.PRACTICE_COMPONENT: ("n_rows", "aliases"),
    NodeType.INDICATOR: ("direction_good", "n_rows"),
    NodeType.STUDY: ("data_source", "corpus_status", "n_chunks"),
    NodeType.AEZ_BELT: (),
    NodeType.CROP_GROUP: (),
    NodeType.COUNTRY: (),
    NodeType.SLM_GROUP: (),
    NodeType.SLM_MEASURE: ("category",),
    NodeType.DEGRADATION_TYPE: ("category",),
    NodeType.CONTEXT_CLASS: ("kind", "value"),
    NodeType.IMPACT_VARIABLE: ("category", "good_direction"),
    NodeType.TECHNOLOGY: ("wocat_id", "country", "licence", "url"),
    NodeType.APPROACH: ("wocat_id", "country", "licence", "url"),
    NodeType.GUIDANCE_DOC: (),
}


def node_id(node_type: NodeType | str, key: str) -> str:
    """Build the canonical node id ``"<NodeType>:<key>"``.

    >>> node_id(NodeType.PRACTICE, "Mulch")
    'Practice:Mulch'
    """
    return f"{NodeType(node_type).value}:{key}"


def context_id(kind: str, value: str) -> str:
    """Node id of a ``ContextClass``: ``"ContextClass:<kind>=<value>"``."""
    if kind not in CONTEXT_CLASS_KINDS:
        raise ValueError(f"unknown ContextClass kind: {kind!r}")
    return node_id(NodeType.CONTEXT_CLASS, f"{kind}={value}")


def new_graph() -> nx.MultiDiGraph:
    """An empty graph stamped with the schema version."""
    return nx.MultiDiGraph(schema_version=SCHEMA_VERSION)


def add_node(
    graph: nx.MultiDiGraph,
    node_type: NodeType,
    key: str,
    label: str | None = None,
    **attrs: Any,
) -> str:
    """Add (or update) a typed node and return its id."""
    nid = node_id(node_type, key)
    if graph.has_node(nid):
        graph.nodes[nid].update(attrs)
    else:
        graph.add_node(nid, type=node_type.value, label=label if label is not None else key, **attrs)
    return nid


def add_edge(
    graph: nx.MultiDiGraph,
    source_id: str,
    edge_type: EdgeType,
    target_id: str,
    source: str,
    key_suffix: str = "",
    **attrs: Any,
) -> str:
    """Add a typed edge and return its multigraph key.

    ``source`` is the mandatory provenance tag. ``key_suffix`` distinguishes
    parallel edges of the same type between the same two nodes — used by
    ``REPORTS_EFFECT``, which carries one edge per indicator.
    """
    if source not in PROVENANCE_SOURCES:
        raise ValueError(f"unknown edge provenance: {source!r}")
    key = f"{edge_type.value}:{key_suffix}" if key_suffix else edge_type.value
    graph.add_edge(
        source_id, target_id, key=key, type=edge_type.value, source=source, **attrs,
    )
    return key


def validate_graph(graph: nx.MultiDiGraph) -> list[str]:
    """Return every contract violation found (empty list when the graph is valid)."""
    problems: list[str] = []
    for nid, attrs in graph.nodes(data=True):
        raw_type = attrs.get("type")
        if raw_type not in set(NodeType):
            problems.append(f"node {nid}: unknown type {raw_type!r}")
            continue
        ntype = NodeType(raw_type)
        if not nid.startswith(f"{ntype.value}:"):
            problems.append(f"node {nid}: id does not match its type {ntype.value}")
        for required in NODE_REQUIRED_ATTRS[ntype]:
            if required not in attrs:
                problems.append(f"node {nid}: missing attribute {required!r}")
        if ntype is NodeType.CONTEXT_CLASS and attrs.get("kind") not in CONTEXT_CLASS_KINDS:
            problems.append(f"node {nid}: bad ContextClass kind {attrs.get('kind')!r}")
        if ntype is NodeType.STUDY and attrs.get("corpus_status") not in CORPUS_STATUSES:
            problems.append(f"node {nid}: bad corpus_status {attrs.get('corpus_status')!r}")

    for src, dst, attrs in graph.edges(data=True):
        raw_type = attrs.get("type")
        if raw_type not in set(EdgeType):
            problems.append(f"edge {src} -> {dst}: unknown type {raw_type!r}")
            continue
        etype = EdgeType(raw_type)
        if attrs.get("source") not in PROVENANCE_SOURCES:
            problems.append(
                f"edge {etype.value} {src} -> {dst}: bad/absent provenance "
                f"{attrs.get('source')!r}"
            )
        for required in EDGE_REQUIRED_ATTRS[etype]:
            if required not in attrs:
                problems.append(
                    f"edge {etype.value} {src} -> {dst}: missing attribute {required!r}"
                )
        allowed_src, allowed_dst = EDGE_ENDPOINTS[etype]
        src_type = graph.nodes[src].get("type")
        dst_type = graph.nodes[dst].get("type")
        if src_type not in {t.value for t in allowed_src}:
            problems.append(
                f"edge {etype.value}: source {src} is a {src_type}, expected "
                f"{sorted(t.value for t in allowed_src)}"
            )
        if dst_type not in {t.value for t in allowed_dst}:
            problems.append(
                f"edge {etype.value}: target {dst} is a {dst_type}, expected "
                f"{sorted(t.value for t in allowed_dst)}"
            )
        if etype is EdgeType.MAPS_TO and attrs.get("status") not in CROSSWALK_STATUSES:
            problems.append(
                f"edge MAPS_TO {src} -> {dst}: bad status {attrs.get('status')!r}"
            )
    return problems


#: Node-link endpoint key names. They are deliberately NOT "source"/"target":
#: every edge carries its own mandatory ``source`` provenance attribute, which
#: networkx's default endpoint key would silently overwrite on serialization.
LINK_FROM_KEY = "from"
LINK_TO_KEY = "to"


def to_node_link(graph: nx.MultiDiGraph) -> dict[str, Any]:
    """Serialize to node-link JSON (sorted, so the output is deterministic)."""
    data = nx.node_link_data(
        graph, source=LINK_FROM_KEY, target=LINK_TO_KEY, edges="links"
    )
    data["nodes"] = sorted(data["nodes"], key=lambda n: n["id"])
    data["links"] = sorted(
        data["links"],
        key=lambda e: (
            e[LINK_FROM_KEY], e["type"], e[LINK_TO_KEY],
            repr(sorted((k, repr(v)) for k, v in e.items())),
        ),
    )
    return data


def from_node_link(data: dict[str, Any]) -> nx.MultiDiGraph:
    """Rebuild a graph from :func:`to_node_link` output."""
    return nx.node_link_graph(
        data, directed=True, multigraph=True,
        source=LINK_FROM_KEY, target=LINK_TO_KEY, edges="links",
    )
