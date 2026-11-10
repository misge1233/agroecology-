"""Knowledge layer (E2 D1/D2): schema additions, validation, query functions, on fixture inputs."""
from __future__ import annotations

import csv
import json

import pytest

from rag.graph import schema as sch
from rag.graph.knowledge_layer import KnowledgeInputs, add_knowledge_layer, belts_in_text
from rag.graph.query import GraphQuery
from rag.graph.schema import EdgeType, NodeType, add_edge, add_node, new_graph, node_id

FAM = "Erosion control and water management"


def _write_csv(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


@pytest.fixture
def graph_and_inputs(tmp_path):
    g = new_graph()
    for belt in ("Dry Weyna Dega", "Moist Weyna Dega", "Moist Kolla"):
        add_node(g, NodeType.AEZ_BELT, belt)
    p = add_node(g, NodeType.PRACTICE, "Physical SWC measures", n_rows=10, practice_family=FAM)
    s = add_node(g, NodeType.STUDY, "CSA_1", data_source="CSA", corpus_status="none", n_chunks=0)
    add_edge(g, s, EdgeType.REPORTS_EFFECT, p, "csa_rows", key_suffix="soil loss", indicator="soil loss", n_obs=3,
             mean_log_rr=-0.5, median_log_rr=-0.5, share_positive=0.0, aez_belts=[], crop_groups=[])
    _write_csv(tmp_path / "practices.csv", [
        {"practice_id": "PHYSICAL_SWC_MEASURES", "name_en": "Physical SWC measures", "practice_family": FAM,
         "catalogue_ids": "", "status": "seed"},
        {"practice_id": "BENCH_TERRACE", "name_en": "Bench Terrace", "practice_family": FAM,
         "catalogue_ids": "CAT_01", "status": "seed"},
    ])
    _write_csv(tmp_path / "aliases.csv", [
        {"alias": "Physical SWC measures", "source": "CSA", "practice_id": "PHYSICAL_SWC_MEASURES", "accepted": ""},
        {"alias": "soil bund", "source": "HAB", "practice_id": "PHYSICAL_SWC_MEASURES", "accepted": ""},
        {"alias": "Bench Terrace", "source": "CAT", "practice_id": "BENCH_TERRACE", "accepted": ""},
    ])
    _write_csv(tmp_path / "challenges.csv", [
        {"challenge_id": "SOIL_EROSION", "name_en": "Soil erosion", "objective_groups": "water",
         "practice_families": FAM, "catalogue_problem_terms": "soil erosion", "outcome_ids": "SOIL_LOSS",
         "status": "seed"},
        {"challenge_id": "FEED_SHORTAGE", "name_en": "Feed", "objective_groups": "livestock", "practice_families": "",
         "catalogue_problem_terms": "feed shortage", "outcome_ids": "", "status": "seed"},
    ])
    (tmp_path / "cat.json").write_text(json.dumps([{
        "catalogue_id": "CAT_01", "number": 1, "name": "Bench Terrace", "category": "Soil and water conservation",
        "target_farming_system": "Crop-livestock mixed", "scaling_stage": "Widely scaled", "scale": "landscape",
        "suitable_land_use_and_agroecology": "Dry and moist Weyna Dega, cultivated land",
        "key_problems": ["soil erosion", "soil moisture stress"], "evidence_base": ["on-farm trial"],
        "limitations": "labour"}]), encoding="utf-8")
    _write_csv(tmp_path / "merges.csv", [
        {"practice_id_a": "BENCH_TERRACE", "practice_id_b": "PHYSICAL_SWC_MEASURES", "relation": "narrower_than",
         "accepted": ""}])
    _write_csv(tmp_path / "gl.csv", [
        {"doc_id": "DOC_A", "title": "Technical manual on soil bund construction", "publisher": "MoA", "year": "2014",
         "language": "en", "theme": "swc", "url": "u"},
        {"doc_id": "DOC_B", "title": "Irrigation agronomy", "publisher": "MoA", "year": "2011", "language": "en",
         "theme": "irrigation", "url": "u"}])
    chunks = [{"doc_id": "DOC_B", "text": "Bench terraces protect soil."} for _ in range(3)]
    chunks.append({"doc_id": "DOC_B", "text": "Irrigation scheduling"})
    (tmp_path / "gl.jsonl").write_text("\n".join(json.dumps(c) for c in chunks), encoding="utf-8")
    inputs = KnowledgeInputs(practices=tmp_path / "practices.csv", practice_aliases=tmp_path / "aliases.csv",
                             challenges=tmp_path / "challenges.csv", catalogue=tmp_path / "cat.json",
                             merges=tmp_path / "merges.csv", guidelines_manifest=tmp_path / "gl.csv",
                             guidelines_chunks=tmp_path / "gl.jsonl")
    return g, inputs


def test_layer_builds_and_validates(graph_and_inputs):
    g, inputs = graph_and_inputs
    stats = add_knowledge_layer(g, inputs)
    assert sch.validate_graph(g) == []
    assert stats["challenges"] == 2 and stats["catalogue_entries"] == 1 and stats["guidance_docs"] == 2
    assert stats["catalogue_practice_nodes"] == 1 and stats["described_by_alias"] == 1
    assert stats["described_by_narrower"] == 1 and stats["suitable_in"] == 2
    bench = node_id(NodeType.PRACTICE, "Bench Terrace")
    assert g.nodes[bench]["origin"] == "catalogue" and g.nodes[bench]["n_rows"] == 0
    assert not list(g.out_edges(bench, keys=True)) or all(
        a["type"] not in ("COMPOSED_OF", "IN_FAMILY") for _, _, a in g.out_edges(bench, data=True))
    doc_edges = {(u, v): a for u, v, a in g.edges(data=True) if a["type"] == "DOCUMENTED_IN"}
    assert doc_edges[(node_id(NodeType.PRACTICE, "Physical SWC measures"),
                      node_id(NodeType.GUIDANCE_DOC, "DOC_A"))]["title_match"] is True   # alias "soil bund" in title
    assert doc_edges[(bench, node_id(NodeType.GUIDANCE_DOC, "DOC_B"))]["n_chunks"] == 3
    assert all(a["source"] in sch.PROVENANCE_SOURCES for _, _, a in g.edges(data=True))


def test_validation_catches_bad_endpoints(graph_and_inputs):
    g, inputs = graph_and_inputs
    add_knowledge_layer(g, inputs)
    g.add_edge(node_id(NodeType.CHALLENGE, "SOIL_EROSION"), node_id(NodeType.GUIDANCE_DOC, "DOC_A"),
               key="x", type="DOCUMENTED_IN", source="guidelines_title_match", n_chunks=1, title_match=False)
    assert any("DOCUMENTED_IN" in p for p in sch.validate_graph(g))


def test_query_functions(graph_and_inputs):
    g, inputs = graph_and_inputs
    add_knowledge_layer(g, inputs)
    q = GraphQuery(g)
    rows = q.practices_for_challenge("SOIL_EROSION")
    by = {r["practice"]: r for r in rows}
    assert by["Physical SWC measures"]["sources"] == ["evidence"] and by["Physical SWC measures"]["n_studies"] == 1
    assert by["Bench Terrace"]["sources"] == ["catalogue"] and by["Bench Terrace"]["catalogue_ids"] == ["CAT_01"]
    assert q.practices_for_challenge("FEED_SHORTAGE") == [] and q.practices_for_challenge("NOPE") == []
    docs = q.documents_for_practice("Physical SWC measures")
    assert [c["catalogue_id"] for c in docs["catalogue"]] == ["CAT_01"] and docs["catalogue"][0]["relation"] == "narrower_than"
    assert [d["doc_id"] for d in docs["guideline_docs"]] == ["DOC_A"]
    assert q.catalogue_entry("BENCH_TERRACE")["name"] == "Bench Terrace"   # by practice_id
    assert q.documents_for_practice("Unknown") == {"catalogue": [], "guideline_docs": []}


@pytest.mark.parametrize("text, belts", [
    ("Dry and moist Weyna Dega", ["Dry Weyna Dega", "Moist Weyna Dega"]),
    ("suitable in Weyna Dega areas", ["Dry Weyna Dega", "Moist Weyna Dega"]),
    ("Moist Kolla and Dega", ["Moist Kolla"]),
    ("across all agro-ecologies", ["Dry Weyna Dega", "Moist Kolla", "Moist Weyna Dega"]),
    ("no belt named", []),
])
def test_belts_in_text(text, belts):
    known = {"Dry Weyna Dega", "Moist Weyna Dega", "Moist Kolla"}
    assert [b for b, _ in belts_in_text(text, known)] == belts
