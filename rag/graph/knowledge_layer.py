"""Knowledge layer of the graph: challenges, catalogue entries, guideline documents (Phase E2, D1).

Additive to the P6a graph; called by ``build_graph.build`` when knowledge
inputs are given (``build_graph.main`` passes the repository files).

Nodes
  * ``Challenge`` from ``data/taxonomy/challenges.csv``;
  * ``CatalogueEntry`` (``CAT_01..30``) from ``data/taxonomy/catalogue_entries.json``;
  * ``GuidanceDoc`` for the 62 government guidelines (``rag/corpus/guidelines/manifest.csv``);
  * ``Practice`` nodes for the catalogue's canonical practices (``origin = catalogue``,
    ``n_rows = 0``). They carry no ``COMPOSED_OF``/``IN_FAMILY`` edges and no
    evidence, so the P6a queries and the advisory candidate pool never see them.

Edges (rules only; provenance in brackets)
  * ``ADDRESSES_PROBLEM`` CatalogueEntry/Practice -> Challenge when an entry's
    normalised key problems meet the challenge's ``catalogue_problem_terms`` [catalogue];
  * ``DESCRIBED_BY`` Practice -> CatalogueEntry: the entry's own practice
    (``relation = alias``) and the frozen category it was proposed narrower than in
    ``review/practice_merges.csv`` (``relation = narrower_than``, with the review
    state ``accepted``) [catalogue];
  * ``DOCUMENTED_IN`` Practice -> GuidanceDoc when the practice name or one of its
    aliases occurs in the document title or in at least 3 of its chunks
    (``n_chunks`` and ``title_match`` attributes) [guidelines_title_match];
  * ``SUITABLE_IN`` CatalogueEntry -> AEZBelt from the entry's "suitable land use and
    agroecology" text (belt names with moisture prefixes; "all agro-ecologies") [catalogue_text].
"""
from __future__ import annotations

import csv
import json
import logging
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .schema import EdgeType, NodeType, add_edge, add_node, node_id

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
TAXONOMY = REPO_ROOT / "data" / "taxonomy"
GUIDELINES = REPO_ROOT / "rag" / "corpus" / "guidelines"
MIN_DOC_CHUNKS = 3
MIN_NAME_CHARS = 5
_MOISTURE = ("Dry", "Moist", "Wet")
_ZONES = {"weyna dega": "Weyna Dega", "woina dega": "Weyna Dega", "kolla": "Kolla", "qolla": "Kolla",
          "dega": "Dega", "wurch": "Wurch", "berha": "Berha", "bereha": "Berha"}


@dataclass
class KnowledgeInputs:
    """Paths of the knowledge-layer inputs (all optional; missing files are skipped)."""

    practices: Path = TAXONOMY / "practices.csv"
    practice_aliases: Path = TAXONOMY / "practice_aliases.csv"
    challenges: Path = TAXONOMY / "challenges.csv"
    catalogue: Path = TAXONOMY / "catalogue_entries.json"
    merges: Path = TAXONOMY / "review" / "practice_merges.csv"
    guidelines_manifest: Path = GUIDELINES / "manifest.csv"
    guidelines_chunks: Path = GUIDELINES / "chunks.jsonl"


def _csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _split(v: str | None) -> list[str]:
    return [x.strip() for x in str(v or "").split(";") if x.strip()]


def belts_in_text(text: str, known: set[str]) -> list[tuple[str, str]]:
    """``(belt, rule)`` named in a suitability text, restricted to the graph's ``known`` belts.

    "Dry and moist Weyna Dega" -> Dry/Moist Weyna Dega; a bare "Weyna Dega" -> every
    moisture variant present; "all agro-ecologies" -> every known belt.
    """
    low = " ".join(str(text or "").lower().split())
    out: dict[str, str] = {}
    if re.search(r"\ball (?:the )?agro-?ecolog", low):
        for b in known:
            out[b] = "all_agroecologies"
    pat = re.compile(r"((?:(?:dry|moist|wet)(?:\s*(?:,|and|or|/)\s*)?)*)\s*\b(weyna\s*dega|woina\s*dega|kolla|qolla|"
                     r"dega|wurch|berha|bereha)\b")
    for m in pat.finditer(low):
        if m.group(2) == "dega" and low[max(0, m.start(2) - 6):m.start(2)].strip().endswith(("weyna", "woina")):
            continue
        zone = _ZONES[" ".join(m.group(2).split())]
        moist = [w.capitalize() for w in re.findall(r"dry|moist|wet", m.group(1) or "")]
        names = [f"{w} {zone}" for w in moist] if moist else [f"{w} {zone}" for w in _MOISTURE]
        for n in names:
            if n in known:
                out.setdefault(n, "belt_name")
    return sorted(out.items())


def _name_patterns(names: set[str]) -> list[re.Pattern]:
    pats = []
    for n in sorted(names, key=len, reverse=True):
        n = " ".join(n.lower().split())
        if len(n) >= MIN_NAME_CHARS:
            pats.append(re.compile(r"(?<![a-z])" + re.escape(n).replace(r"\ ", r"[\s-]+") + r"s?(?![a-z])"))
    return pats


def add_knowledge_layer(graph, inputs: KnowledgeInputs | None = None) -> dict[str, Any]:
    """Add the E2 nodes and edges to ``graph``; returns counts for the report."""
    inp = inputs or KnowledgeInputs()
    stats: dict[str, Any] = defaultdict(int)
    practices = {r["practice_id"]: r for r in _csv(inp.practices) if r.get("status") != "merged"}
    aliases: dict[str, set[str]] = defaultdict(set)
    for r in _csv(inp.practice_aliases):
        if r.get("accepted", "").lower() != "no" and r.get("practice_id"):
            aliases[r["practice_id"]].add(r["alias"])

    # practice_id -> Practice node id (frozen labels exist already; catalogue practices are added)
    pnode: dict[str, str] = {}
    for pid, p in practices.items():
        nid = node_id(NodeType.PRACTICE, p["name_en"])
        if graph.has_node(nid):
            graph.nodes[nid]["practice_id"] = pid
            pnode[pid] = nid
        elif p.get("catalogue_ids"):
            add_node(graph, NodeType.PRACTICE, p["name_en"], n_rows=0, practice_family=p["practice_family"],
                     practice_id=pid, origin="catalogue")
            pnode[pid] = node_id(NodeType.PRACTICE, p["name_en"])
            stats["catalogue_practice_nodes"] += 1

    # challenges
    terms_of: dict[str, set[str]] = {}
    for c in _csv(inp.challenges):
        add_node(graph, NodeType.CHALLENGE, c["challenge_id"], label=c["name_en"], name_en=c["name_en"],
                 objective_groups=_split(c["objective_groups"]), status=c.get("status", "seed"),
                 practice_families=_split(c.get("practice_families")), outcome_ids=_split(c.get("outcome_ids")))
        terms_of[c["challenge_id"]] = set(_split(c.get("catalogue_problem_terms")))
        stats["challenges"] += 1

    # catalogue entries
    catalogue = json.loads(inp.catalogue.read_text(encoding="utf-8")) if inp.catalogue.exists() else []
    cat_practice = {a: pid for pid, names in aliases.items() for a in names}
    known_belts = {attrs["label"] for _, attrs in graph.nodes(data=True) if attrs.get("type") == NodeType.AEZ_BELT.value}
    for e in catalogue:
        cid = e["catalogue_id"]
        nid = add_node(graph, NodeType.CATALOGUE_ENTRY, cid, label=e["name"], name=e["name"],
                       category=e.get("category") or "", farming_system=e.get("target_farming_system") or "",
                       scaling_stage=e.get("scaling_stage") or "", scale=e.get("scale") or "",
                       evidence_base=e.get("evidence_base") or [], limitations=e.get("limitations") or "",
                       key_problems=e.get("key_problems") or [], number=e.get("number"))
        stats["catalogue_entries"] += 1
        pid = cat_practice.get(e["name"])
        for ch, terms in terms_of.items():
            hit = sorted(set(e.get("key_problems") or []) & terms)
            if hit:
                add_edge(graph, nid, EdgeType.ADDRESSES_PROBLEM, node_id(NodeType.CHALLENGE, ch), "catalogue", terms=hit)
                stats["addresses_problem_catalogue"] += 1
                if pid in pnode:
                    add_edge(graph, pnode[pid], EdgeType.ADDRESSES_PROBLEM, node_id(NodeType.CHALLENGE, ch),
                             "catalogue", terms=hit, via=cid)
                    stats["addresses_problem_practice"] += 1
        if pid in pnode:
            add_edge(graph, pnode[pid], EdgeType.DESCRIBED_BY, nid, "catalogue", relation="alias", accepted="")
            stats["described_by_alias"] += 1
        for belt, rule in belts_in_text(e.get("suitable_land_use_and_agroecology") or "", known_belts):
            add_edge(graph, nid, EdgeType.SUITABLE_IN, node_id(NodeType.AEZ_BELT, belt), "catalogue_text",
                     key_suffix=belt, rule=rule, quote=(e.get("suitable_land_use_and_agroecology") or "")[:300])
            stats["suitable_in"] += 1
    cat_by_pid = {pid: e["catalogue_id"] for e in catalogue if (pid := cat_practice.get(e["name"]))}
    for m in _csv(inp.merges):
        if m.get("relation") != "narrower_than" or m.get("accepted", "").lower() == "no":
            continue
        cid, parent = cat_by_pid.get(m["practice_id_a"]), pnode.get(m["practice_id_b"])
        if cid and parent:
            add_edge(graph, parent, EdgeType.DESCRIBED_BY, node_id(NodeType.CATALOGUE_ENTRY, cid), "catalogue",
                     key_suffix=cid, relation="narrower_than", accepted=m.get("accepted", ""))
            stats["described_by_narrower"] += 1

    # guideline documents
    docs = _csv(inp.guidelines_manifest)
    chunks_by_doc: dict[str, list[str]] = defaultdict(list)
    if inp.guidelines_chunks.exists():
        for line in inp.guidelines_chunks.read_text(encoding="utf-8").splitlines():
            if line.strip():
                c = json.loads(line)
                chunks_by_doc[c["doc_id"]].append(c["text"].lower())
    for d in docs:
        add_node(graph, NodeType.GUIDANCE_DOC, d["doc_id"], label=d["title"], doc_id=d["doc_id"], title=d["title"],
                 publisher=d.get("publisher", ""), year=int(d["year"]) if d.get("year", "").isdigit() else 0,
                 language=d.get("language", "en"), theme=d.get("theme", ""), tier="guidelines",
                 url=d.get("url", ""), n_chunks=len(chunks_by_doc.get(d["doc_id"], [])))
        stats["guidance_docs"] += 1
    for pid, nid in pnode.items():
        pats = _name_patterns({practices[pid]["name_en"], *aliases.get(pid, set())})
        if not pats:
            continue
        for d in docs:
            title_match = any(p.search(d["title"].lower()) for p in pats)
            n = sum(1 for t in chunks_by_doc.get(d["doc_id"], []) if any(p.search(t) for p in pats))
            if title_match or n >= MIN_DOC_CHUNKS:
                add_edge(graph, nid, EdgeType.DOCUMENTED_IN, node_id(NodeType.GUIDANCE_DOC, d["doc_id"]),
                         "guidelines_title_match", n_chunks=n, title_match=title_match)
                stats["documented_in"] += 1
    logger.info("knowledge layer: %s", dict(stats))
    return dict(stats)
