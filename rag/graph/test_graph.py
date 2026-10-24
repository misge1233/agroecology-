"""Unit tests for the knowledge-graph layer (Phase P6a).

Everything runs on a SYNTHETIC dataset fixture written to ``tmp_path`` — no
network, no chromadb, no raster stack, no trained model. ``build_graph``
reaches ``rag.eval.build_queries`` for the canonical ``strip_era_prefix``
helper, which pulls ``requests`` (already in ``rag/requirements.txt``); the
heavier retrieval dependencies stay unimported.

Run from the repo root:
    python -m pytest rag/graph/test_graph.py -q
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

GRAPH_DIR = Path(__file__).resolve().parent
REPO_ROOT = GRAPH_DIR.parents[1]
for _path in (str(GRAPH_DIR), str(REPO_ROOT)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import build_graph as bg  # noqa: E402
import indicator_map as im  # noqa: E402
import practice_components as pc  # noqa: E402
import schema as sch  # noqa: E402
import wocat_taxonomy as wt  # noqa: E402
from query import GraphQuery  # noqa: E402

FIXTURE_DIR = REPO_ROOT / "rag" / "ingest" / "wocat" / "fixtures"

COLUMNS = (
    "source,Study_No_,latitude,longitude,CSA_practices,practice_family,"
    "Crop_group,crop_type,Rainfall,Altitude_r,slope,temp_mean_annual,"
    "precip_seasonality,lgp_days,soil_clay,soil_ph,soil_soc,land_cover,"
    "aez_belt,Indicator,response_ratio,log_response_ratio"
)

ECWM = "Erosion control and water management"
ISFM = "Integrated soil fertility management"

#: (Study_No_, source, CSA_practices, family, aez_belt, Crop_group, Indicator, log_rr)
ROWS: tuple[tuple[str, str, str, str, str, str, str, float], ...] = (
    # Hand-computable aggregate: ERA_T0001 x Mulch-Reduced Tillage x yield
    ("ERA_T0001", "ERA", "Mulch-Reduced Tillage", ECWM, "Dry Dega", "Cereal", "yield", 0.10),
    ("ERA_T0001", "ERA", "Mulch-Reduced Tillage", ECWM, "Dry Dega", "Cereal", "yield", 0.30),
    ("ERA_T0001", "ERA", "Mulch-Reduced Tillage", ECWM, "Wet Kolla", "Pulse", "yield", -0.20),
    ("ERA_T0001", "ERA", "Mulch", ECWM, "Dry Dega", "Cereal", "yield", 0.50),
    ("ERA_T0002", "ERA", "Mulch-Reduced Tillage", ECWM, "Dry Kolla", "Cereal", "soil loss", -0.40),
    ("ERA_T0003", "ERA", "Deficit Irrigation", ECWM, "Dry Kolla", "Vegetable", "yield", 0.15),
    ("CSA_9", "CSA", "Deficit irrigation", ECWM, "Dry Kolla", "Vegetable", "yield", 0.25),
    ("CSA_9", "CSA", "In-situ water harvesting", ECWM, "Dry Kolla", "Cereal", "runoff", -0.30),
    ("CSA_12", "CSA", "organic amedements", ISFM, "Moist Dega", "Cereal", "SOM content", 0.40),
)

#: Hand-computed from the three ERA_T0001 yield rows above.
EXPECTED_T0001_YIELD = {
    "n_obs": 3,
    "mean_log_rr": round((0.10 + 0.30 - 0.20) / 3, 6),   # 0.066667
    "median_log_rr": 0.1,
    "share_positive": round(2 / 3, 6),                    # 0.666667
    "aez_belts": ["Dry Dega", "Wet Kolla"],
    "crop_groups": ["Cereal", "Pulse"],
}


# ------------------------------------------------------------------ fixtures
@pytest.fixture
def dataset(tmp_path: Path) -> Path:
    """A synthetic dataset csv with the frozen column names."""
    lines = [COLUMNS]
    for study, source, practice, family, belt, crop, indicator, log_rr in ROWS:
        lines.append(
            f"{source},{study},9.0,39.0,{practice},{family},{crop},maize,"
            f"900,2000,5,19,70,180,30,6.1,1.2,40,{belt},{indicator},"
            f"{round(2.718281828 ** log_rr, 6)},{log_rr}"
        )
    path = tmp_path / "dataset.csv"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


@pytest.fixture
def manifest(tmp_path: Path) -> Path:
    path = tmp_path / "manifest.jsonl"
    path.write_text(
        "\n".join(
            json.dumps(r) for r in (
                {"era_code": "T0001", "title": "Mulch and tillage trial",
                 "year": 2019, "doi": "10.1000/t1", "container": "Soil & Tillage",
                 "oa_status": "gold"},
                {"era_code": "T0002", "title": "Erosion plots", "year": 2020,
                 "doi": "10.1000/t2", "container": "Catena", "oa_status": "closed"},
            )
        ) + "\n",
        encoding="utf-8",
    )
    return path


@pytest.fixture
def chunks(tmp_path: Path) -> Path:
    path = tmp_path / "chunks.jsonl"
    path.write_text(
        "\n".join(
            json.dumps(c) for c in (
                {"chunk_id": "T0001_000", "era_code": "T0001", "source": "pdf",
                 "text": "full text"},
                {"chunk_id": "T0001_001", "era_code": "T0001", "source": "pdf",
                 "text": "more full text"},
                {"chunk_id": "T0002_000", "era_code": "T0002", "source": "abstract",
                 "text": "abstract only"},
                # Tier-2 guidance chunks carry no era_code and must be ignored.
                {"chunk_id": "G_1", "era_code": None, "source": "pdf", "text": "guidance"},
            )
        ) + "\n",
        encoding="utf-8",
    )
    return path


@pytest.fixture
def crosswalk(tmp_path: Path) -> Path:
    """One validated row, one proposed row, one rejected row."""
    path = tmp_path / "crosswalk.csv"
    path.write_text(
        "component,aliases,families,n_rows,proposed_groups,proposed_measures,"
        "confidence,rationale,status,owner_decision,owner_note\n"
        f"Mulch,Mulch,{ECWM},4,improved ground/ vegetation cover,A1; A2,"
        "0.9,validated by owner,proposed,validated,looks right\n"
        f"Reduced Tillage,Reduced Tillage,{ECWM},3,minimal soil disturbance,A3,"
        "0.9,rule proposal,proposed,,\n"
        f"Deficit Irrigation,Deficit Irrigation,{ECWM},2,,S7,"
        "0.9,rule proposal,proposed,rejected,not an SLM measure here\n",
        encoding="utf-8",
    )
    return path


def _build(dataset, manifest, chunks, crosswalk, **kwargs):
    return bg.build(
        dataset_path=dataset, manifest_path=manifest, chunks_path=chunks,
        crosswalk_path=crosswalk, **kwargs,
    )


@pytest.fixture
def graph_and_report(dataset, manifest, chunks, crosswalk):
    return _build(dataset, manifest, chunks, crosswalk)


# -------------------------------------------------------------- decomposition
def test_split_protects_hyphenated_component_names():
    assert pc.split_practice("In-situ water harvesting") == ("In-situ water harvesting",)
    assert pc.split_practice("Biochar-Inorganic Fertilizer-Organic Fertilizer") == (
        "Biochar", "Inorganic Fertilizer", "Organic Fertilizer",
    )
    # No hyphen -> one component, even with a word that looks like a join.
    assert pc.split_practice("Intercropping or Rotation") == ("Intercropping or Rotation",)


def test_aliases_collapse_case_and_typos():
    assert pc.normalize_component("Deficit irrigation") == "Deficit Irrigation"
    assert pc.normalize_component("Deficit Irrigation") == "Deficit Irrigation"
    assert pc.normalize_component("organic amedements") == "Organic Amendments"
    assert pc.normalize_component("Drought tolerrant crops") == "Drought Tolerant Crops"
    assert pc.normalize_component("physical swc measures") == "Physical SWC Measures"


def test_alias_clusters_report_observed_spellings():
    clusters = pc.alias_clusters(["Deficit Irrigation", "Deficit irrigation", "Mulch"])
    assert clusters == {"Deficit Irrigation": ["Deficit Irrigation", "Deficit irrigation"]}


def test_decompose_dedupes_and_is_deterministic():
    assert pc.decompose("Mulch-Mulch-Reduced Tillage") == ("Mulch", "Reduced Tillage")
    assert pc.decompose("Mulch-Reduced Tillage") == pc.decompose(" Mulch - Reduced Tillage ")


def test_unknown_component_passes_through_cleaned():
    assert pc.normalize_component("  Brand  New  Practice ") == "Brand New Practice"
    assert pc.is_known("Brand New Practice") is False


# ------------------------------------------------------------------ taxonomy
def test_slm_measure_codes_are_unique_and_complete():
    codes = [m.code for m in wt.SLM_MEASURES]
    assert len(codes) == len(set(codes)) == 30
    assert {m.category for m in wt.SLM_MEASURES} == {
        "agronomic", "vegetative", "structural", "management"
    }
    assert wt.measure("A3").sub_options == wt.A3_TILLAGE_SYSTEMS


def test_taxonomy_expected_counts():
    assert len(wt.SLM_GROUPS) == 27
    assert len(wt.DEGRADATION_TYPES) == 32
    assert len(wt.ON_SITE_IMPACT_VARIABLES) == 69
    assert len(wt.IMPACT_BY_NAME) == 69
    degradation_codes = [d.code for d in wt.DEGRADATION_TYPES]
    assert len(degradation_codes) == len(set(degradation_codes))


def test_every_impact_variable_has_a_good_direction():
    for variable in wt.ON_SITE_IMPACT_VARIABLES:
        assert variable.good_direction in ("increase", "decrease"), variable.name
        assert variable.negative_pole and variable.positive_pole


def test_pests_diseases_discrepancy_is_documented_not_silently_fixed():
    pests = wt.impact_variable("pests/ diseases")
    # poles transcribed verbatim from the questionnaire...
    assert (pests.negative_pole, pests.positive_pole) == ("decreased", "increased")
    # ...but the substantive direction and a source note are recorded.
    assert pests.good_direction == "decrease"
    assert "inverted" in pests.source_note


def test_context_and_band_normalizers_absorb_live_database_spellings():
    assert wt.normalize_context_value("rainfall_band", "1 501 – 2 000 mm") == "1,501-2,000 mm"
    assert wt.normalize_context_value("altitude_zone", "0 – 100 m a.s.l.") == "< 100 m a.s.l."
    assert wt.normalize_context_value("slope_class", "not a slope") is None
    assert wt.normalize_adoption_band("11 – 50 %") == "10-50%"
    assert wt.normalize_spontaneous_band("91 – 100 %") == "90-100%"
    assert wt.normalize_rating("Very positive (+50-100%)") == "very positive"
    assert wt.normalize_impact_name("biomass/ above ground C") == "biomass/ above-ground C"


# ------------------------------------------------------------ indicator map
def test_indicator_map_matches_the_engine_exactly():
    assert im.validate() == []
    assert set(im.MAPPING_BY_INDICATOR) == set(im.direction_map())


def test_directions_come_from_recommend_not_from_this_module():
    # soil loss and runoff are the two lower-is-better indicators in the engine.
    assert im.model_direction("soil loss") == -1
    assert im.model_direction("runoff") == -1
    assert im.model_direction("yield") == 1
    assert "recommend" in im.direction_source()


def test_every_mapping_has_a_rationale_and_known_target():
    for mapping in im.INDICATOR_MAPPINGS:
        assert len(mapping.rationale) > 30
        assert mapping.wocat_variable in wt.IMPACT_BY_NAME
    assert im.MAPPING_BY_INDICATOR["water use efficiency"].proxy is True


# --------------------------------------------------------------- graph build
def test_graph_builds_and_validates(graph_and_report):
    graph, report = graph_and_report
    assert report["validation"] == []
    assert sch.validate_graph(graph) == []


def test_node_and_edge_counts(graph_and_report):
    graph, report = graph_and_report
    nodes = report["nodes_by_type"]
    # taxonomy layer is fixed
    assert nodes["SLMGroup"] == 27
    assert nodes["SLMMeasure"] == 30
    assert nodes["DegradationType"] == 32
    assert nodes["ImpactVariable"] == 69
    assert nodes["ContextClass"] == sum(
        len(wt.CONTEXT_CLASSES[k]) for k in sch.CONTEXT_CLASS_KINDS
    )
    assert nodes["Indicator"] == 7
    # dataset layer follows the fixture
    assert nodes["Practice"] == 6          # 6 distinct frozen CSA_practices
    assert nodes["Study"] == 5             # T0001-3, CSA_9, CSA_12
    assert nodes["PracticeFamily"] == 2
    # ...but "Deficit Irrigation" and "Deficit irrigation" are two distinct
    # FROZEN practice labels that collapse to ONE canonical component, so
    # there are fewer components than practices.
    assert nodes["PracticeComponent"] == 5
    assert report["components"]["raw_tokens"] == 6
    assert report["components"]["canonical"] == 5
    assert report["components"]["unknown_tokens"] == []
    assert report["components"]["alias_clusters"] == {
        "Deficit Irrigation": ["Deficit Irrigation", "Deficit irrigation"]
    }

    edges = report["edges_by_type"]
    assert edges["IN_FAMILY"] == 6         # one per practice
    assert edges["REPORTS_EFFECT"] == 7    # distinct (study, practice, indicator)
    assert edges["COMPOSED_OF"] == 7       # Mulch-Reduced Tillage contributes 2


def test_every_edge_carries_a_known_provenance(graph_and_report):
    graph, _ = graph_and_report
    assert graph.number_of_edges() > 0
    for src, dst, attrs in graph.edges(data=True):
        assert attrs.get("source") in sch.PROVENANCE_SOURCES, (src, dst, attrs)


def test_reports_effect_aggregate_equals_hand_computed_value(graph_and_report):
    graph, _ = graph_and_report
    attrs = graph.edges[
        sch.node_id(sch.NodeType.STUDY, "ERA_T0001"),
        sch.node_id(sch.NodeType.PRACTICE, "Mulch-Reduced Tillage"),
        "REPORTS_EFFECT:yield",
    ]
    for key, expected in EXPECTED_T0001_YIELD.items():
        assert attrs[key] == expected, key
    assert attrs["source"] == "era_rows"
    assert attrs["indicator"] == "yield"


def test_study_corpus_status_from_manifest_and_chunks(graph_and_report):
    graph, report = graph_and_report
    t1 = graph.nodes[sch.node_id(sch.NodeType.STUDY, "ERA_T0001")]
    assert (t1["corpus_status"], t1["n_chunks"]) == ("full_text", 2)
    assert t1["title"] == "Mulch and tillage trial" and t1["doi"] == "10.1000/t1"
    t2 = graph.nodes[sch.node_id(sch.NodeType.STUDY, "ERA_T0002")]
    assert (t2["corpus_status"], t2["n_chunks"]) == ("abstract", 1)
    # A CSA study has no era_code, so it is never matched to the Tier-1 corpus.
    csa = graph.nodes[sch.node_id(sch.NodeType.STUDY, "CSA_9")]
    assert csa["era_code"] is None and csa["corpus_status"] == "none"
    assert report["coverage"]["studies_with_chunks"] == 2
    assert report["coverage"]["studies_with_full_text"] == 1


def test_build_is_deterministic_and_idempotent(dataset, manifest, chunks, crosswalk, tmp_path):
    first, report_a = _build(dataset, manifest, chunks, crosswalk)
    second, report_b = _build(dataset, manifest, chunks, crosswalk)
    assert sch.to_node_link(first) == sch.to_node_link(second)
    path_a, _ = bg.write_store(first, report_a, tmp_path / "a")
    path_b, _ = bg.write_store(second, report_b, tmp_path / "b")
    assert path_a.read_bytes() == path_b.read_bytes()


def test_json_round_trip_preserves_nodes_edges_and_provenance(graph_and_report):
    graph, _ = graph_and_report
    payload = json.loads(json.dumps(sch.to_node_link(graph)))
    restored = sch.from_node_link(payload)
    assert restored.number_of_nodes() == graph.number_of_nodes()
    assert restored.number_of_edges() == graph.number_of_edges()
    assert sch.validate_graph(restored) == []
    assert sch.to_node_link(restored) == sch.to_node_link(graph)


# ----------------------------------------------------------- crosswalk gate
def test_only_validated_crosswalk_rows_enter_the_graph(graph_and_report):
    graph, report = graph_and_report
    maps_to = [
        (src, dst, attrs) for src, dst, attrs in graph.edges(data=True)
        if attrs["type"] == "MAPS_TO"
    ]
    # Only the Mulch row is owner-validated: 1 group + 2 measures.
    assert len(maps_to) == 3
    assert {src for src, _, _ in maps_to} == {
        sch.node_id(sch.NodeType.PRACTICE_COMPONENT, "Mulch")
    }
    assert {attrs["status"] for _, _, attrs in maps_to} == {"validated"}
    assert {attrs["source"] for _, _, attrs in maps_to} == {"crosswalk_validated"}
    assert report["coverage"]["crosswalk_rows_admitted"] == 1


def test_include_proposed_admits_proposed_but_never_rejected(
    dataset, manifest, chunks, crosswalk
):
    graph, report = _build(dataset, manifest, chunks, crosswalk, include_proposed=True)
    by_status: dict[str, set[str]] = {}
    for src, _, attrs in graph.edges(data=True):
        if attrs["type"] == "MAPS_TO":
            by_status.setdefault(attrs["status"], set()).add(src.split(":", 1)[1])
    assert by_status["validated"] == {"Mulch"}
    assert by_status["proposed"] == {"Reduced Tillage"}
    # The rejected Deficit Irrigation row is admitted under neither flag.
    assert "Deficit Irrigation" not in set().union(*by_status.values())
    proposed_sources = {
        attrs["source"] for _, _, attrs in graph.edges(data=True)
        if attrs["type"] == "MAPS_TO" and attrs["status"] == "proposed"
    }
    assert proposed_sources == {"crosswalk_auto"}
    assert report["validation"] == []


def test_missing_crosswalk_degrades_to_no_maps_to(dataset, manifest, chunks, tmp_path):
    graph, report = _build(dataset, manifest, chunks, tmp_path / "absent.csv")
    assert report["coverage"]["maps_to_edges"] == 0
    assert report["validation"] == []


# ---------------------------------------------------------------- queries
def test_evidence_summary_reports_the_aggregates_unchanged(graph_and_report):
    graph, _ = graph_and_report
    summary = GraphQuery(graph).evidence_summary("Mulch-Reduced Tillage", "yield")
    assert summary["found"] is True
    assert summary["n_studies"] == 1 and summary["n_obs"] == 3
    study = summary["studies"][0]
    assert study["mean_log_rr"] == EXPECTED_T0001_YIELD["mean_log_rr"]
    assert study["era_code"] == "T0001" and study["corpus_status"] == "full_text"
    assert summary["aez_belts"] == ["Dry Dega", "Wet Kolla"]


def test_evidence_summary_for_unknown_practice_is_empty_not_an_error(graph_and_report):
    graph, _ = graph_and_report
    summary = GraphQuery(graph).evidence_summary("No Such Practice", "yield")
    assert summary["found"] is False and summary["studies"] == []


def test_components_of_preserves_label_order(graph_and_report):
    graph, _ = graph_and_report
    assert GraphQuery(graph).components_of("Mulch-Reduced Tillage") == [
        "Mulch", "Reduced Tillage",
    ]


def test_slm_measures_for_uses_validated_rows_only(dataset, manifest, chunks, crosswalk):
    graph, _ = _build(dataset, manifest, chunks, crosswalk, include_proposed=True)
    gq = GraphQuery(graph)
    codes = [m["code"] for m in gq.slm_measures_for("Mulch-Reduced Tillage")]
    # A1/A2 come from the validated Mulch row; A3 from the merely PROPOSED
    # Reduced Tillage row and must not appear.
    assert codes == ["A1", "A2"]
    assert gq.slm_groups_for("Mulch-Reduced Tillage") == [
        "improved ground/ vegetation cover"
    ]


def test_related_practices_scores_shared_components_and_studies(graph_and_report):
    graph, _ = graph_and_report
    related = GraphQuery(graph).related_practices("Mulch-Reduced Tillage", k=5)
    assert related, "expected at least one related practice"
    top = related[0]
    assert top["practice"] == "Mulch"
    assert top["shared_components"] == ["Mulch"]
    assert top["n_shared_studies"] == 1   # both reported by ERA_T0001


def test_similar_context_technologies_is_empty_without_technology_nodes(graph_and_report):
    graph, _ = graph_and_report
    assert GraphQuery(graph).similar_context_technologies(
        {"agroclimatic_zone": "sub-humid"}, "Mulch"
    ) == []


def test_explain_paths_returns_real_edges_with_provenance(graph_and_report):
    graph, _ = graph_and_report
    paths = GraphQuery(graph).explain_paths("Mulch-Reduced Tillage", "yield", max_paths=5)
    assert paths
    assert paths[0]["kind"] == "evidence"
    kinds = {p["kind"] for p in paths}
    assert "crosswalk" in kinds        # the validated Mulch row
    for path in paths:
        for hop in path["hops"]:
            assert hop["source"] in sch.PROVENANCE_SOURCES
            assert hop["edge"] in {e.value for e in sch.EdgeType}


def test_explain_paths_unknown_pair_is_empty(graph_and_report):
    graph, _ = graph_and_report
    assert GraphQuery(graph).explain_paths("No Such Practice", "yield") == []


# ------------------------------------------------------ WOCAT fixture layer
@pytest.fixture
def graph_with_fixtures(dataset, manifest, chunks, crosswalk):
    return _build(dataset, manifest, chunks, crosswalk, wocat_path=FIXTURE_DIR)


def test_fixtures_ingest_as_technology_and_approach_nodes(graph_with_fixtures):
    graph, report = graph_with_fixtures
    assert report["validation"] == []
    assert report["wocat"]["technologies"] == 2
    assert report["wocat"]["approaches"] == 1
    tech = graph.nodes[sch.node_id(sch.NodeType.TECHNOLOGY, "6644")]
    assert tech["country"] == "Ethiopia"
    assert tech["licence"].startswith("CC BY-NC-SA")
    assert tech["url"].startswith("https://wocat.net/")
    assert tech["synthetic"] is False


def test_fixture_edges_carry_wocat_fixture_provenance(graph_with_fixtures):
    graph, _ = graph_with_fixtures
    tid = sch.node_id(sch.NodeType.TECHNOLOGY, "6644")
    kinds: dict[str, int] = {}
    for _, _, attrs in graph.out_edges(tid, data=True):
        assert attrs["source"] == "wocat_fixture"
        kinds[attrs["type"]] = kinds.get(attrs["type"], 0) + 1
    assert kinds["USES_MEASURE"] == 5          # A2 A3 A6 A7 M2
    assert kinds["IN_GROUP"] == 3
    assert kinds["ADDRESSES"] == 9
    assert kinds["HAS_CONTEXT"] == 9
    assert kinds["LINKED_APPROACH"] == 1
    assert kinds["REPORTS_IMPACT"] == 39


def test_reports_impact_edges_record_rating_and_direction(graph_with_fixtures):
    graph, _ = graph_with_fixtures
    attrs = graph.edges[
        sch.node_id(sch.NodeType.TECHNOLOGY, "6644"),
        sch.node_id(sch.NodeType.IMPACT_VARIABLE, "soil loss"),
        "REPORTS_IMPACT:soil loss",
    ]
    assert attrs["rating"] == "slightly positive"
    assert attrs["rating_index"] == wt.IMPACT_RATING_KEYS.index("slightly positive")
    assert attrs["good_direction"] == "decrease"


def test_similar_context_technologies_ranks_by_matching_context(graph_with_fixtures):
    graph, _ = graph_with_fixtures
    gq = GraphQuery(graph)
    assert gq.has_technologies() is True
    sub_humid = gq.similar_context_technologies(
        {"agroclimatic_zone": "sub-humid", "slope_class": "gentle (3-5%)"}, k=5
    )
    assert sub_humid[0]["wocat_id"] == "6644"
    assert sub_humid[0]["context_jaccard"] > 0
    steep = gq.similar_context_technologies(
        {"agroclimatic_zone": "semi-arid", "slope_class": "steep (31-60%)"}, k=5
    )
    assert steep[0]["wocat_id"] == "SYNTH-0001"
    assert steep[0]["synthetic"] is True


def test_measure_overlap_uses_validated_crosswalk(graph_with_fixtures):
    graph, _ = graph_with_fixtures
    # The validated Mulch row maps to A1+A2; Technology 6644 uses A2.
    results = GraphQuery(graph).similar_context_technologies(
        {"agroclimatic_zone": "sub-humid"}, practice="Mulch", k=5
    )
    by_id = {r["wocat_id"]: r for r in results}
    assert by_id["6644"]["shared_measures"] == ["A2"]
    assert by_id["6644"]["measure_overlap"] == 0.5
    assert by_id["SYNTH-0001"]["shared_measures"] == []


def test_unknown_context_kind_is_ignored_not_fatal(graph_with_fixtures):
    graph, _ = graph_with_fixtures
    results = GraphQuery(graph).similar_context_technologies(
        {"landform": "plateau/ plains", "agroclimatic_zone": "sub-humid"}, k=5
    )
    assert results[0]["wocat_id"] == "6644"


# ------------------------------------------------------------------ schema
def test_add_edge_rejects_unknown_provenance():
    graph = sch.new_graph()
    a = sch.add_node(graph, sch.NodeType.PRACTICE, "P", n_rows=1, practice_family="F")
    b = sch.add_node(graph, sch.NodeType.PRACTICE_FAMILY, "F", n_rows=1)
    with pytest.raises(ValueError, match="unknown edge provenance"):
        sch.add_edge(graph, a, sch.EdgeType.IN_FAMILY, b, source="made_up")


def test_validate_graph_catches_wrong_endpoints_and_bad_status():
    graph = sch.new_graph()
    a = sch.add_node(graph, sch.NodeType.PRACTICE, "P", n_rows=1, practice_family="F")
    b = sch.add_node(graph, sch.NodeType.AEZ_BELT, "Dry Dega")
    sch.add_edge(graph, a, sch.EdgeType.IN_FAMILY, b, source="era_rows")
    problems = sch.validate_graph(graph)
    assert any("expected" in p for p in problems)


def test_context_id_rejects_unknown_kind():
    with pytest.raises(ValueError, match="unknown ContextClass kind"):
        sch.context_id("landform", "ridges")


# ------------------------------------------- crosswalk re-run merge (P6a.1)
import csv as _csv  # noqa: E402

from crosswalk.propose_crosswalk import (  # noqa: E402
    COLUMNS as CW_COLUMNS,
    merge_row,
    read_existing,
    write_csv as cw_write_csv,
)
from crosswalk.propose_crosswalk import Proposal as CwProposal  # noqa: E402


def _cw_proposal(component="Mulch", groups=("improved ground/ vegetation cover",),
                 measures=("A1", "A2"), families=("Erosion control and water management",),
                 n_rows=326):
    return CwProposal(
        component=component, aliases=[component], families=list(families),
        n_rows=n_rows, groups=set(groups), measures=set(measures),
        confidence=0.9, rationales=["rule rationale"],
    )


def _read_rows(path):
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return {r["component"]: r for r in _csv.DictReader(fh)}


def test_crosswalk_first_run_writes_blank_owner_columns(tmp_path):
    path, preserved = cw_write_csv([_cw_proposal()], tmp_path / "cw.csv")
    assert preserved == {}
    row = _read_rows(path)["Mulch"]
    assert list(row) == list(CW_COLUMNS)
    assert row["status"] == "proposed"
    assert row["owner_decision"] == "" and row["owner_note"] == ""


def test_crosswalk_rerun_preserves_owner_decision_and_note(tmp_path):
    path = tmp_path / "cw.csv"
    cw_write_csv([_cw_proposal()], path)
    rows = _read_rows(path)
    rows["Mulch"].update(owner_decision="validated", owner_note="checked against QT")
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = _csv.DictWriter(fh, fieldnames=list(CW_COLUMNS))
        w.writeheader()
        w.writerow(rows["Mulch"])

    _, preserved = cw_write_csv([_cw_proposal()], path)
    row = _read_rows(path)["Mulch"]
    assert row["owner_decision"] == "validated"
    assert row["owner_note"] == "checked against QT"
    assert row["status"] == "validated"          # status follows the decision
    assert "owner_decision" in preserved["Mulch"]


def test_crosswalk_rerun_keeps_edited_targets_on_a_decided_row(tmp_path):
    path = tmp_path / "cw.csv"
    cw_write_csv([_cw_proposal()], path)
    rows = _read_rows(path)
    rows["Mulch"].update(owner_decision="validated", proposed_measures="A1")
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = _csv.DictWriter(fh, fieldnames=list(CW_COLUMNS))
        w.writeheader()
        w.writerow(rows["Mulch"])

    _, preserved = cw_write_csv([_cw_proposal()], path)   # rules still say A1; A2
    row = _read_rows(path)["Mulch"]
    assert row["proposed_measures"] == "A1"               # the owner's edit wins
    assert "proposed_measures" in preserved["Mulch"]


def test_crosswalk_rerun_refreshes_targets_on_an_undecided_row(tmp_path):
    """A row the owner never decided must track the rules, not freeze."""
    path = tmp_path / "cw.csv"
    cw_write_csv([_cw_proposal(measures=("A1",))], path)
    _, preserved = cw_write_csv([_cw_proposal(measures=("A1", "A2"))], path)
    assert _read_rows(path)["Mulch"]["proposed_measures"] == "A1; A2"
    assert "Mulch" not in preserved


def test_crosswalk_rerun_always_refreshes_the_measured_columns(tmp_path):
    """families/n_rows must move — that is what the P6a.1 fix changes."""
    path = tmp_path / "cw.csv"
    cw_write_csv([_cw_proposal(families=("Livestock production and management",),
                               n_rows=311)], path)
    rows = _read_rows(path)
    rows["Mulch"]["owner_decision"] = "validated"
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = _csv.DictWriter(fh, fieldnames=list(CW_COLUMNS))
        w.writeheader()
        w.writerow(rows["Mulch"])

    cw_write_csv([_cw_proposal(families=("Erosion control and water management",),
                               n_rows=326)], path)
    row = _read_rows(path)["Mulch"]
    assert row["families"] == "Erosion control and water management"
    assert row["n_rows"] == "326"
    assert row["owner_decision"] == "validated"      # decision still intact


def test_crosswalk_rerun_appends_new_components_and_drops_absent_ones(tmp_path):
    path = tmp_path / "cw.csv"
    cw_write_csv([_cw_proposal("Mulch"), _cw_proposal("Gone Away")], path)
    cw_write_csv([_cw_proposal("Mulch"), _cw_proposal("Brand New")], path)
    rows = _read_rows(path)
    assert set(rows) == {"Brand New", "Mulch"}
    assert list(rows) == sorted(rows)                 # still sorted by component


def test_crosswalk_no_merge_discards_owner_work(tmp_path):
    path = tmp_path / "cw.csv"
    cw_write_csv([_cw_proposal()], path)
    rows = _read_rows(path)
    rows["Mulch"]["owner_decision"] = "validated"
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = _csv.DictWriter(fh, fieldnames=list(CW_COLUMNS))
        w.writeheader()
        w.writerow(rows["Mulch"])

    _, preserved = cw_write_csv([_cw_proposal()], path, merge=False)
    assert preserved == {}
    assert _read_rows(path)["Mulch"]["owner_decision"] == ""


def test_merge_row_is_a_pure_function():
    fresh = {"component": "Mulch", "proposed_measures": "A1; A2",
             "owner_decision": "", "owner_note": "", "status": "proposed"}
    existing = {"component": "Mulch", "proposed_measures": "A1",
                "owner_decision": "validated", "owner_note": "note"}
    row, preserved = merge_row(fresh, existing)
    assert fresh["proposed_measures"] == "A1; A2"     # input untouched
    assert row["proposed_measures"] == "A1"
    assert row["status"] == "validated"
    assert set(preserved) >= {"proposed_measures", "owner_decision", "owner_note"}


def test_read_existing_returns_empty_for_a_missing_file(tmp_path):
    assert read_existing(tmp_path / "nope.csv") == {}
