"""Read-only queries over the knowledge graph — the P6b retriever's API.

Every function here reads the graph and returns plain dicts/lists. None of
them computes a new effect size: ``evidence_summary`` reports the
``REPORTS_EFFECT`` aggregates that ``build_graph.py`` derived from the
dataset rows, and nothing else in this module touches a number that the
model or the data did not already own (CLAUDE.md doctrine 1).

Functions degrade rather than raise when a layer is absent: with no
Technology nodes in the graph (the P6a default),
:func:`similar_context_technologies` returns ``[]``; with no validated
crosswalk, :func:`slm_measures_for` returns ``[]``.

Typical use::

    from rag.graph.query import GraphQuery
    gq = GraphQuery.load()                       # rag/graph/store/graph.json
    gq.evidence_summary("Mulch-Reduced Tillage", "yield")
"""
from __future__ import annotations

import json
import logging
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import networkx as nx

GRAPH_DIR = Path(__file__).resolve().parent
if str(GRAPH_DIR) not in sys.path:
    sys.path.insert(0, str(GRAPH_DIR))

from schema import (  # noqa: E402
    CONTEXT_CLASS_KINDS,
    EdgeType,
    NodeType,
    context_id,
    from_node_link,
    node_id,
)

logger = logging.getLogger(__name__)

DEFAULT_STORE = GRAPH_DIR / "store" / "graph.json"


class GraphQuery:
    """Read-only view over a built graph."""

    def __init__(self, graph: nx.MultiDiGraph) -> None:
        self.graph = graph

    # ------------------------------------------------------------- loading
    @classmethod
    def load(cls, path: Path | str = DEFAULT_STORE) -> GraphQuery:
        """Load a graph from node-link JSON written by ``build_graph.py``."""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(
                f"graph store not found: {path} — run rag/graph/build_graph.py"
            )
        return cls(from_node_link(json.loads(path.read_text(encoding="utf-8"))))

    # -------------------------------------------------------- small helpers
    def _attrs(self, nid: str) -> dict[str, Any]:
        return dict(self.graph.nodes[nid]) if self.graph.has_node(nid) else {}

    def _out(self, nid: str, edge_type: EdgeType):
        """Yield ``(target_id, edge_attrs)`` for one outgoing edge type."""
        if not self.graph.has_node(nid):
            return
        for _, dst, attrs in self.graph.out_edges(nid, data=True):
            if attrs.get("type") == edge_type.value:
                yield dst, attrs

    def _in(self, nid: str, edge_type: EdgeType):
        """Yield ``(source_id, edge_attrs)`` for one incoming edge type."""
        if not self.graph.has_node(nid):
            return
        for src, _, attrs in self.graph.in_edges(nid, data=True):
            if attrs.get("type") == edge_type.value:
                yield src, attrs

    def _nodes_of(self, node_type: NodeType) -> list[str]:
        return [
            nid for nid, attrs in self.graph.nodes(data=True)
            if attrs.get("type") == node_type.value
        ]

    def has_technologies(self) -> bool:
        """True once WOCAT Technology nodes have been ingested."""
        return bool(self._nodes_of(NodeType.TECHNOLOGY))

    # ------------------------------------------------------------- queries
    def evidence_summary(self, practice: str, indicator: str) -> dict[str, Any]:
        """Per-study evidence behind one (practice, indicator) pair.

        Returns the studies that report this practice for this indicator,
        each with its observation count, the dataset's own mean/median log
        response ratio, the AEZ belts and crop groups the observations came
        from, and how much of that study is in the retrieval corpus.

        The totals are aggregates of the same rows — no new estimate is
        produced, and nothing is re-weighted.
        """
        pid = node_id(NodeType.PRACTICE, practice)
        if not self.graph.has_node(pid):
            return {
                "practice": practice, "indicator": indicator, "found": False,
                "studies": [], "n_studies": 0, "n_obs": 0,
                "aez_belts": [], "crop_groups": [], "corpus_status": {},
            }
        practice_attrs = self._attrs(pid)
        studies: list[dict[str, Any]] = []
        belts: set[str] = set()
        crops: set[str] = set()
        corpus_status: dict[str, int] = defaultdict(int)
        for sid, attrs in self._in(pid, EdgeType.REPORTS_EFFECT):
            if attrs.get("indicator") != indicator:
                continue
            study = self._attrs(sid)
            belts.update(attrs.get("aez_belts") or [])
            crops.update(attrs.get("crop_groups") or [])
            corpus_status[study.get("corpus_status", "none")] += 1
            studies.append({
                "study_no": sid.split(":", 1)[1],
                "era_code": study.get("era_code"),
                "data_source": study.get("data_source"),
                "title": study.get("title"),
                "year": study.get("year"),
                "doi": study.get("doi"),
                "corpus_status": study.get("corpus_status"),
                "n_chunks": study.get("n_chunks", 0),
                "n_obs": attrs.get("n_obs"),
                "mean_log_rr": attrs.get("mean_log_rr"),
                "median_log_rr": attrs.get("median_log_rr"),
                "share_positive": attrs.get("share_positive"),
                "aez_belts": attrs.get("aez_belts") or [],
                "crop_groups": attrs.get("crop_groups") or [],
            })
        studies.sort(key=lambda s: (-(s["n_obs"] or 0), s["study_no"]))
        return {
            "practice": practice,
            "practice_family": practice_attrs.get("practice_family"),
            "indicator": indicator,
            "found": bool(studies),
            "n_studies": len(studies),
            "n_obs": sum(s["n_obs"] or 0 for s in studies),
            "aez_belts": sorted(belts),
            "crop_groups": sorted(crops),
            "corpus_status": dict(sorted(corpus_status.items())),
            "studies": studies,
        }

    def components_of(self, practice: str) -> list[str]:
        """Canonical components of a frozen practice label, in label order."""
        pid = node_id(NodeType.PRACTICE, practice)
        pairs = [
            (attrs.get("position", 0), dst.split(":", 1)[1])
            for dst, attrs in self._out(pid, EdgeType.COMPOSED_OF)
        ]
        return [name for _, name in sorted(pairs)]

    def slm_measures_for(self, practice: str) -> list[dict[str, Any]]:
        """WOCAT SLM measures for a practice, via VALIDATED crosswalk rows only.

        ``status=proposed`` rows are ignored here even when the graph was
        built with ``--include-proposed``: an unvalidated guess must never
        reach the advisory.
        """
        measures: dict[str, dict[str, Any]] = {}
        for component in self.components_of(practice):
            cid = node_id(NodeType.PRACTICE_COMPONENT, component)
            for dst, attrs in self._out(cid, EdgeType.MAPS_TO):
                if attrs.get("status") != "validated":
                    continue
                if self.graph.nodes[dst].get("type") != NodeType.SLM_MEASURE.value:
                    continue
                code = dst.split(":", 1)[1]
                entry = measures.setdefault(code, {
                    "code": code,
                    "label": self._attrs(dst).get("measure_label"),
                    "category": self._attrs(dst).get("category"),
                    "via_components": [],
                    "confidence": attrs.get("confidence"),
                })
                entry["via_components"].append(component)
        for entry in measures.values():
            entry["via_components"] = sorted(set(entry["via_components"]))
        return sorted(measures.values(), key=lambda m: m["code"])

    def slm_groups_for(self, practice: str) -> list[str]:
        """WOCAT SLM groups for a practice, via validated crosswalk rows only."""
        groups: set[str] = set()
        for component in self.components_of(practice):
            cid = node_id(NodeType.PRACTICE_COMPONENT, component)
            for dst, attrs in self._out(cid, EdgeType.MAPS_TO):
                if attrs.get("status") != "validated":
                    continue
                if self.graph.nodes[dst].get("type") == NodeType.SLM_GROUP.value:
                    groups.add(dst.split(":", 1)[1])
        return sorted(groups)

    def related_practices(self, practice: str, k: int = 5) -> list[dict[str, Any]]:
        """Practices related by shared components and/or shared studies.

        Score = (# shared components) + (# shared studies), components first
        on ties. Deterministic: ties break on the practice label.
        """
        pid = node_id(NodeType.PRACTICE, practice)
        if not self.graph.has_node(pid):
            return []
        own_components = set(self.components_of(practice))
        own_studies = {sid for sid, _ in self._in(pid, EdgeType.REPORTS_EFFECT)}

        shared_components: dict[str, set[str]] = defaultdict(set)
        for component in own_components:
            cid = node_id(NodeType.PRACTICE_COMPONENT, component)
            for other, _ in self._in(cid, EdgeType.COMPOSED_OF):
                if other != pid:
                    shared_components[other].add(component)
        shared_studies: dict[str, set[str]] = defaultdict(set)
        for sid in own_studies:
            for other, _ in self._out(sid, EdgeType.REPORTS_EFFECT):
                if other != pid:
                    shared_studies[other].add(sid)

        candidates = set(shared_components) | set(shared_studies)
        results = [
            {
                "practice": other.split(":", 1)[1],
                "practice_family": self._attrs(other).get("practice_family"),
                "shared_components": sorted(shared_components.get(other, ())),
                "n_shared_components": len(shared_components.get(other, ())),
                "n_shared_studies": len(shared_studies.get(other, ())),
                "score": len(shared_components.get(other, ()))
                + len(shared_studies.get(other, ())),
            }
            for other in candidates
        ]
        results.sort(
            key=lambda r: (-r["score"], -r["n_shared_components"], r["practice"])
        )
        return results[:k]

    def similar_context_technologies(
        self, context: dict[str, Any], practice: str | None = None, k: int = 5
    ) -> list[dict[str, Any]]:
        """WOCAT Technologies matching a biophysical context (and practice).

        ``context`` maps ``ContextClass`` kinds to a value or list of values,
        e.g. ``{"agroclimatic_zone": "sub-humid", "slope_class":
        "gentle (3-5%)"}``. Scoring:

        * ``context_jaccard`` — Jaccard overlap of ContextClass nodes;
        * ``measure_overlap`` — share of the practice's validated SLM
          measures the Technology also uses (0.0 when ``practice`` is None
          or has no validated crosswalk);
        * ``score`` — their mean, so neither dominates.

        Returns ``[]`` when the graph holds no Technology nodes, which is the
        P6a default: WOCAT records arrive in P6b.
        """
        technologies = self._nodes_of(NodeType.TECHNOLOGY)
        if not technologies:
            return []

        wanted: set[str] = set()
        for kind, values in (context or {}).items():
            if kind not in CONTEXT_CLASS_KINDS:
                logger.debug("ignoring non-node context kind %r", kind)
                continue
            for value in ([values] if isinstance(values, str) else values or []):
                wanted.add(context_id(kind, value))

        practice_measures = {
            m["code"] for m in self.slm_measures_for(practice)
        } if practice else set()

        results: list[dict[str, Any]] = []
        for tid in technologies:
            theirs = {dst for dst, _ in self._out(tid, EdgeType.HAS_CONTEXT)}
            union = wanted | theirs
            jaccard = len(wanted & theirs) / len(union) if union else 0.0
            their_measures = {
                dst.split(":", 1)[1] for dst, _ in self._out(tid, EdgeType.USES_MEASURE)
            }
            overlap = (
                len(practice_measures & their_measures) / len(practice_measures)
                if practice_measures else 0.0
            )
            attrs = self._attrs(tid)
            results.append({
                "wocat_id": attrs.get("wocat_id"),
                "title": attrs.get("label"),
                "country": attrs.get("country"),
                "url": attrs.get("url"),
                "licence": attrs.get("licence"),
                "synthetic": bool(attrs.get("synthetic")),
                "shared_context": sorted(
                    self._attrs(c).get("label", c) for c in (wanted & theirs)
                ),
                "context_jaccard": round(jaccard, 4),
                "measure_overlap": round(overlap, 4),
                "shared_measures": sorted(practice_measures & their_measures),
                "score": round((jaccard + overlap) / 2, 4),
            })
        results.sort(key=lambda r: (-r["score"], -r["context_jaccard"], str(r["wocat_id"])))
        return results[:k]

    def explain_paths(
        self, practice: str, indicator: str, max_paths: int = 5
    ) -> list[dict[str, Any]]:
        """Short provenance chains justifying a (practice, indicator) pairing.

        Each path is a list of ``{from, edge, to, source}`` hops so the
        advisory can state *why* a link exists and where it came from. Paths
        are ordered most-evidence-first and never invented: every hop is an
        edge that exists in the graph.
        """
        pid = node_id(NodeType.PRACTICE, practice)
        iid = node_id(NodeType.INDICATOR, indicator)
        if not self.graph.has_node(pid) or not self.graph.has_node(iid):
            return []

        def hop(src: str, etype: EdgeType, dst: str, attrs: dict[str, Any]) -> dict[str, Any]:
            return {
                "from": self._attrs(src).get("label", src),
                "from_type": self._attrs(src).get("type"),
                "edge": etype.value,
                "to": self._attrs(dst).get("label", dst),
                "to_type": self._attrs(dst).get("type"),
                "source": attrs.get("source"),
            }

        paths: list[dict[str, Any]] = []

        # 1. Study -> REPORTS_EFFECT -> Practice, for this indicator.
        effects = [
            (sid, attrs) for sid, attrs in self._in(pid, EdgeType.REPORTS_EFFECT)
            if attrs.get("indicator") == indicator
        ]
        effects.sort(key=lambda pair: (-(pair[1].get("n_obs") or 0), pair[0]))
        for sid, attrs in effects:
            study = self._attrs(sid)
            paths.append({
                "kind": "evidence",
                "n_obs": attrs.get("n_obs"),
                "hops": [hop(sid, EdgeType.REPORTS_EFFECT, pid, attrs)],
                "study": {
                    "study_no": sid.split(":", 1)[1],
                    "era_code": study.get("era_code"),
                    "doi": study.get("doi"),
                    "corpus_status": study.get("corpus_status"),
                },
            })

        # 2. Practice -> COMPOSED_OF -> Component -> MAPS_TO -> SLM measure
        #    (validated rows only).
        for component in self.components_of(practice):
            cid = node_id(NodeType.PRACTICE_COMPONENT, component)
            comp_attrs = next(
                (a for d, a in self._out(pid, EdgeType.COMPOSED_OF) if d == cid), {}
            )
            for dst, attrs in self._out(cid, EdgeType.MAPS_TO):
                if attrs.get("status") != "validated":
                    continue
                paths.append({
                    "kind": "crosswalk",
                    "n_obs": None,
                    "hops": [
                        hop(pid, EdgeType.COMPOSED_OF, cid, comp_attrs),
                        hop(cid, EdgeType.MAPS_TO, dst, attrs),
                    ],
                })

        # 3. Indicator -> MEASURES -> WOCAT impact variable.
        for dst, attrs in self._out(iid, EdgeType.MEASURES):
            paths.append({
                "kind": "indicator_mapping",
                "n_obs": None,
                "role": attrs.get("role"),
                "proxy": attrs.get("proxy"),
                "hops": [hop(iid, EdgeType.MEASURES, dst, attrs)],
            })

        paths.sort(key=lambda p: (
            {"evidence": 0, "crosswalk": 1, "indicator_mapping": 2}[p["kind"]],
            -(p.get("n_obs") or 0),
        ))
        return paths[:max_paths]


# -------------------------------------------------------- module-level API
_CACHED: GraphQuery | None = None


def default_query(path: Path | str = DEFAULT_STORE) -> GraphQuery:
    """Process-wide cached :class:`GraphQuery` over the default store."""
    global _CACHED
    if _CACHED is None:
        _CACHED = GraphQuery.load(path)
    return _CACHED


def evidence_summary(practice: str, indicator: str) -> dict[str, Any]:
    """Module-level shortcut for :meth:`GraphQuery.evidence_summary`."""
    return default_query().evidence_summary(practice, indicator)


def components_of(practice: str) -> list[str]:
    """Module-level shortcut for :meth:`GraphQuery.components_of`."""
    return default_query().components_of(practice)


def slm_measures_for(practice: str) -> list[dict[str, Any]]:
    """Module-level shortcut for :meth:`GraphQuery.slm_measures_for`."""
    return default_query().slm_measures_for(practice)


def related_practices(practice: str, k: int = 5) -> list[dict[str, Any]]:
    """Module-level shortcut for :meth:`GraphQuery.related_practices`."""
    return default_query().related_practices(practice, k)


def similar_context_technologies(
    context: dict[str, Any], practice: str | None = None, k: int = 5
) -> list[dict[str, Any]]:
    """Module-level shortcut for :meth:`GraphQuery.similar_context_technologies`."""
    return default_query().similar_context_technologies(context, practice, k)


def explain_paths(practice: str, indicator: str, max_paths: int = 5) -> list[dict[str, Any]]:
    """Module-level shortcut for :meth:`GraphQuery.explain_paths`."""
    return default_query().explain_paths(practice, indicator, max_paths)
