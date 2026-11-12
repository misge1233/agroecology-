"""The masking canary (E4 Part 3, mandatory).

For a held-out group a synthetic chunk carrying a unique token and the group's DOI is
put into a temporary Chroma collection; retrieval under the fold's mask must never
return it (dense path with a fake embedding, lexical path with BM25, fused), while the
same query without the mask does. The same for a graph ``REPORTS_EFFECT`` edge and for a
training row. It runs for **every fold of every repetition** of both splits built on a
fixture query set, and (``data`` marker) on the real Tier 1 index for one fold.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import networkx as nx
import pandas as pd
import pytest

from model.harness import folds as hf
from model.harness import queries as hq
from model.harness.mask import Mask, group_keys
from pipelines.evidence import schema
from rag import retrieve as rr
from rag.graph.query import GraphQuery
from rag.graph.schema import EdgeType, NodeType, add_edge, add_node, new_graph, node_id

TOKEN = "zqxcanarytoken"
DIM = 16


def fake_embed(text: str) -> list[float]:
    """Deterministic bag-of-hashed-words embedding (no API): the canary token dominates it."""
    v = [0.0] * DIM
    for w in text.lower().split():
        h = int(hashlib.sha256(w.encode()).hexdigest(), 16)
        v[h % DIM] += 1.0 + (3.0 if w == TOKEN else 0.0)
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


def _chunk(cid, text, **meta):
    return {"chunk_id": cid, "text": text, "era_code": meta.get("era_code"), "doi": meta.get("doi"),
            "study_ids": meta.get("study_ids"), "title": "t", "year": 2020, "journal": "j", "source": "abstract"}


def build_fixture_index(tmp_path: Path, chunks: list[dict]) -> rr.RagRetriever:
    import chromadb
    from rag.ingest.build_index import _metadata

    client = chromadb.PersistentClient(path=str(tmp_path / "store"))
    col = client.get_or_create_collection("era_corpus", metadata={"hnsw:space": "cosine"})
    col.add(ids=[c["chunk_id"] for c in chunks], embeddings=[fake_embed(c["text"]) for c in chunks],
            documents=[c["text"] for c in chunks], metadatas=[_metadata(c) for c in chunks])
    (tmp_path / "chunks.jsonl").write_text("\n".join(json.dumps(c) for c in chunks) + "\n", encoding="utf-8")
    r = rr.RagRetriever(index_dir=tmp_path / "store", chunks_path=tmp_path / "chunks.jsonl", api_key="fixture")
    r._embed = fake_embed  # type: ignore[method-assign]
    return r


# ----------------------------------------------------------------- fixture queries + folds
def _store_row(i, study, practice, doi, lat, lon, source="ERA", year=2020):
    return {"row_id": f"{source}:{study}:{i}", "source": source, "study_id": study, "doi": doi, "citation": "c",
            "year": year, "country": "ET", "lat": lat, "lon": lon, "loc_precision": "site", "loc_method": "reported",
            "site_name": None, "practice_id": practice, "practice_raw": practice, "practice_family": "F",
            "comparator": "control", "crop": "maize", "outcome_id": "YIELD", "outcome_raw": "y", "direction": 1,
            "direction_reviewed": True, "lrr": 0.1 * (hash(practice) % 7), "weight": 1.0, "quality_flag": "NR",
            "licence": "l", "ctx_release": "ET/2026.1", "ctx_precip_annual": 900.0, "ctx_elevation": 2000.0,
            "ctx_aez_belt": 7}


def fixture_store() -> pd.DataFrame:
    rows = []
    for g in range(12):
        study = f"ERA_S{g:02d}" if g % 3 else f"HAB_H_{g:02d}_001"
        doi = f"10.1/d{g:02d}" if g % 4 else None
        for p in ("A", "B", "C"):
            rows.append(_store_row(len(rows), study, p, doi, 6.0 + g * 0.7, 36.0 + (g % 2) * 1.5,
                                   source="HAB" if study.startswith("HAB") else "ERA"))
    return schema.coerce(pd.DataFrame(rows))


class Tax:
    outcomes = pd.DataFrame([{"outcome_id": "YIELD", "objective_group": "productivity", "legacy_indicator": "yield", "direction": "1"}])
    challenges = pd.DataFrame([{"challenge_id": "LOW_CROP_PRODUCTIVITY", "outcome_ids": "YIELD"}])
    practices = pd.DataFrame([{"practice_id": p, "practice_family": "F"} for p in "ABC"])


def _graph_for(store: pd.DataFrame) -> nx.MultiDiGraph:
    g = new_graph()
    add_node(g, NodeType.PRACTICE, "Mulch", label="Mulch", practice_family="F")
    add_node(g, NodeType.INDICATOR, "yield", label="yield")
    for sid, doi in store.groupby("study_id")["doi"].first().items():
        add_node(g, NodeType.STUDY, sid, label=sid, doi=doi, era_code=(sid[4:] if sid.startswith("ERA_") else sid),
                 data_source="ERA" if sid.startswith("ERA_") else "HAB", corpus_status="none", n_chunks=0)
        add_edge(g, node_id(NodeType.STUDY, sid), EdgeType.REPORTS_EFFECT, node_id(NodeType.PRACTICE, "Mulch"),
                 "era_rows", key_suffix="yield", indicator="yield", n_obs=3, mean_log_rr=0.2, median_log_rr=0.2,
                 share_positive=1.0, aez_belts=["Moist Dega"], crop_groups=["Cereal"])
    return g


def test_canary_for_every_fold_on_the_fixture_index(tmp_path):
    store = fixture_store()
    queries, _ = hq.build_queries(store, Tax(), aez_lookup={7: "Moist Dega"})
    assert len(queries) == 12
    graph = GraphQuery(_graph_for(store))
    dataset = pd.DataFrame({"Study_No_": store["study_id"], "x": 1.0})
    base_chunks = [_chunk(f"OTHER_{i:03d}", f"soil bunds reduce runoff on slopes study {i}", era_code=f"O{i}", doi=f"10.9/o{i}",
                          study_ids=[f"ERA_O{i}"]) for i in range(6)]
    base_chunks.append(_chunk("NOMETA_000", f"{TOKEN} a guidance paragraph without any study metadata"))
    checked = 0
    for split in ("spatial", "study"):
        fold_df, _ = hf.build_folds(queries, split)
        folds = fold_df.set_index("query_id")
        for rep in range(hf.N_REPS):
            for fold in range(hf.N_FOLDS):
                held_q, held_groups = hf.fold_members(folds, rep, fold)
                if not held_groups:
                    continue
                mask = Mask.from_groups(held_groups, store)
                # one held-out group, deterministic per fold: its DOI (or study id) goes on the canary chunk
                group = sorted(held_groups)[(rep * 5 + fold) % len(held_groups)]
                sid = store.loc[group_keys(store) == group, "study_id"].iloc[0]
                doi = group if "/" in group else None
                canary = _chunk("CANARY_000", f"{TOKEN} mulch raised maize yield in this held-out trial", doi=doi,
                                era_code=(sid[4:] if sid.startswith("ERA_") else sid), study_ids=[sid])
                r = build_fixture_index(tmp_path / f"{split}_{rep}_{fold}", base_chunks + [canary])
                query = f"{TOKEN} mulch maize yield"
                open_hits = {h["chunk_id"] for h in r.retrieve(query, k=8)}
                assert "CANARY_000" in open_hits, "the canary must be retrievable without a mask"
                for dense in (True, False):
                    masked_hits = {h["chunk_id"] for h in r.retrieve(query, k=8, mask=mask, dense=dense)}
                    assert "CANARY_000" not in masked_hits, (split, rep, fold, group)
                    assert "NOMETA_000" in masked_hits  # unmaskable chunks are kept and counted
                assert r.unmaskable.get("NOMETA_000", 0) >= 1
                # the retriever's dense path really filtered at the index (where clause), not only afterwards
                assert "CANARY_000" not in r._dense(query, 8, mask)
                # graph: the held-out study's REPORTS_EFFECT edge is gone from the masked view only
                assert sid in {s["study_no"] for s in graph.evidence_summary("Mulch", "yield")["studies"]}
                view = graph.masked(mask)
                assert sid not in {s["study_no"] for s in view.evidence_summary("Mulch", "yield")["studies"]}
                assert sid in view.masked_studies
                # training rows: the held-out study is filtered from store and dataset frames
                assert sid not in set(mask.filter_rows(store)["study_id"])
                assert sid not in set(mask.filter_rows(dataset)["Study_No_"])
                assert set(mask.filter_rows(store)["study_id"]).isdisjoint(mask.study_ids)
                checked += 1
    assert checked == 2 * hf.N_REPS * hf.N_FOLDS


# ----------------------------------------------------------------- real index, one fold
REAL_INDEX = Path(__file__).resolve().parent / "index" / "store"
REAL_CHUNKS = Path(__file__).resolve().parent / "corpus" / "chunks.jsonl"
STORE = Path(__file__).resolve().parents[1] / "data" / "evidence" / "evidence_rows.parquet"
FOLDS = Path(__file__).resolve().parents[1] / "data" / "evidence" / "harness" / "folds_study.csv"


@pytest.mark.data
@pytest.mark.skipif(not (REAL_INDEX / "chroma.sqlite3").exists() or not REAL_CHUNKS.exists() or not STORE.exists()
                    or not FOLDS.exists(), reason="real index, store or folds absent")
def test_canary_on_the_real_index_for_one_fold(tmp_path):
    """Fold 0 of repetition 0 of the study split against the real Tier 1 chunks: a canary chunk with a
    held-out DOI never returns, no returned chunk belongs to a masked group, and the chunks without
    study metadata are counted. Dense retrieval runs when an API key is configured, else lexical only."""
    import chromadb
    from rag.ingest.build_index import _metadata

    store = pd.read_parquet(STORE)
    folds = hf.load_folds(FOLDS)
    _, held_groups = hf.fold_members(folds, 0, 0)
    mask = Mask.from_groups(held_groups, store)
    assert mask.dois and mask.study_ids
    doi = sorted(mask.dois)[0]
    real = [json.loads(l) for l in REAL_CHUNKS.read_text(encoding="utf-8").splitlines() if l.strip()]
    canary = _chunk("CANARY_REAL", f"{TOKEN} mulch raised maize yield in this held-out trial", doi=doi)
    chunks = real + [canary]
    (tmp_path / "chunks.jsonl").write_text("\n".join(json.dumps(c, ensure_ascii=False) for c in chunks) + "\n", encoding="utf-8")
    client = chromadb.PersistentClient(path=str(tmp_path / "store"))
    col = client.get_or_create_collection("era_corpus", metadata={"hnsw:space": "cosine"})
    col.add(ids=["CANARY_REAL"], embeddings=[fake_embed(canary["text"])], documents=[canary["text"]],
            metadatas=[_metadata(canary)])
    r = rr.RagRetriever(index_dir=tmp_path / "store", chunks_path=tmp_path / "chunks.jsonl", api_key="fixture")
    r._embed = fake_embed  # type: ignore[method-assign]
    q = f"{TOKEN} mulch maize yield"
    assert "CANARY_REAL" in {h["chunk_id"] for h in r.retrieve(q, k=5)}
    assert "CANARY_REAL" not in {h["chunk_id"] for h in r.retrieve(q, k=5, mask=mask)}
    # the real chunks, lexical path under the mask: nothing returned belongs to a held-out group
    for query in ("soil bunds soil loss Ethiopia", "mulch maize yield", "intercropping biomass", "manure SOM content"):
        for h in r.retrieve(query, k=20, mask=mask, dense=False):
            assert not mask.blocks_chunk(h), h["chunk_id"]
    unmaskable = [c["chunk_id"] for c in real if not Mask.chunk_is_maskable(c)]
    assert len(unmaskable) == 0, f"Tier 1 chunks without study metadata: {unmaskable[:5]}"
    if rr._find_api_key():
        dense = rr.default_retriever()
        for query in ("soil bunds soil loss Ethiopia", "mulch maize yield"):
            for h in dense.retrieve(query, k=20, mask=mask):
                assert not mask.blocks_chunk(h), h["chunk_id"]
