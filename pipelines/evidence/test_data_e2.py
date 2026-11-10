"""Data-dependent E2 acceptance tests (skipped when the inputs are absent).

* store rebuild after the reviews keeps 19,753 rows and validates (schema v1.1);
* registry counts change only in the allowed direction (more counted rows, never fewer
  unless an exclusion removed them; the diff is printed);
* the 62 guideline documents are ingested with page texts and chunks;
* the knowledge graph validates with the E2 node and edge types;
* the geocoding sheet covers every Habtamu study and every row has a quote.
"""
from __future__ import annotations

import csv
import json

import pytest

from pipelines.evidence import build_registry, common, geocode_sites, load_habtamu, schema

pytestmark = pytest.mark.data

STORE = common.EVIDENCE_DIR / schema.STORE_PARQUET
REGISTRY = build_registry.registry_path("ET")
GUIDE = common.REPO_ROOT / "rag" / "corpus" / "guidelines"
GRAPH = common.REPO_ROOT / "rag" / "graph" / "store" / "graph.json"


@pytest.mark.skipif(not STORE.exists(), reason="store not built")
def test_store_keeps_all_rows_and_validates():
    from pipelines.taxonomy import taxonomy_io as tio

    df = schema.read_store(common.EVIDENCE_DIR)
    assert len(df) == 19_753
    assert schema.SCHEMA_VERSION == "1.1"
    manifest = json.loads((common.EVIDENCE_DIR / schema.STORE_MANIFEST).read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "1.1"
    assert schema.validate(df, outcome_directions=tio.Taxonomy.load().outcome_directions()).ok


@pytest.mark.skipif(not (STORE.exists() and REGISTRY.exists()), reason="store or registry not built")
def test_registry_counts_only_move_in_the_allowed_direction():
    from pipelines.common.country_config import load_country
    from pipelines.taxonomy import taxonomy_io as tio

    tax = tio.Taxonomy.load()
    cat = json.loads((common.TAXONOMY_DIR / "catalogue_entries.json").read_text(encoding="utf-8")) \
        if (common.TAXONOMY_DIR / "catalogue_entries.json").exists() else []
    new = build_registry.build_registry(schema.read_store(common.EVIDENCE_DIR), tax, cat,
                                        load_country("ET", check_files=False))
    old = json.loads(REGISTRY.read_text(encoding="utf-8"))
    diff = build_registry.registry_diff(old, new)
    print("\n" + build_registry.diff_table(diff))
    excluded = set(tax.outcomes.loc[tax.outcomes["status"].isin(["excluded", "merged"]), "outcome_id"])
    for d in diff:
        if d["rows_after"] < d["rows_before"]:
            ch = next(c for c in new["challenges"] if c["id"] == d["id"])
            assert {o["id"] for o in ch["objectives"]} & excluded, f"{d['id']} lost rows without an exclusion"


@pytest.mark.skipif(not (GUIDE / "chunks.jsonl").exists(), reason="guidelines not ingested")
def test_62_guidelines_ingested_with_pages():
    with open(GUIDE / "manifest.csv", newline="", encoding="utf-8") as fh:
        docs = [r["doc_id"] for r in csv.DictReader(fh)]
    assert len(docs) == 62
    for d in docs:
        meta = json.loads((GUIDE / "texts" / d / "meta.json").read_text(encoding="utf-8"))
        assert meta["pages"] > 0 and (GUIDE / "texts" / d / "page_1.txt").exists(), d
    chunks = [json.loads(line) for line in (GUIDE / "chunks.jsonl").read_text(encoding="utf-8").splitlines()]
    assert {c["doc_id"] for c in chunks} == set(docs)
    assert all(c["tier"] == "guidelines" and c["page"] >= 1 and c["citation"].endswith(f"p. {c['page']}")
               for c in chunks)


@pytest.mark.skipif(not GRAPH.exists(), reason="graph not built")
def test_graph_validates_with_knowledge_layer():
    from rag.graph.query import GraphQuery
    from rag.graph.schema import validate_graph

    q = GraphQuery.load(GRAPH)
    assert validate_graph(q.graph) == []
    types = {a["type"] for _, a in q.graph.nodes(data=True)}
    assert {"Challenge", "CatalogueEntry", "GuidanceDoc"} <= types
    if REGISTRY.exists():
        for c in json.loads(REGISTRY.read_text(encoding="utf-8"))["challenges"]:
            if c["exposed"]:
                assert q.practices_for_challenge(c["id"]), c["id"]


@pytest.mark.skipif(not (geocode_sites.REVIEW_CSV.exists() and load_habtamu.RAW_PATH.exists()),
                    reason="geocoding sheet or Habtamu data absent")
def test_geocoding_sheet_covers_every_study():
    import pandas as pd

    sheet = pd.read_csv(geocode_sites.REVIEW_CSV, dtype=str, keep_default_na=False)
    hab = schema.coerce(load_habtamu.load()[0])
    assert set(sheet["study_id"]) == set(hab["study_id"]) and len(sheet) == 605
    assert (sheet["quote"].str.strip() != "").all()
    placed = sheet[sheet["lat"] != ""]
    bbox = geocode_sites.country_bbox("ET")
    et = placed[placed["country"] == "ET"]
    assert all(geocode_sites.in_bbox(float(r.lat), float(r.lon), bbox) for r in et.itertuples())
