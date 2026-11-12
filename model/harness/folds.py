"""Deterministic folds over the harness queries (E4 Part 2).

Two splits, each 5 folds x 5 repetitions, written once and read through one function
(:func:`load_folds`, as ``pipelines/dataset/assign_folds.load_folds`` does for the P7
protocol):

* **study-grouped** (``folds_study.csv``): every query of one ``group`` (DOI or study
  id) is in one fold;
* **spatial blocks** (``folds_spatial.csv``): queries are assigned to 1 x 1 degree
  blocks (about 110 km) from their coordinates (``b<lat>_<lon>`` from the floor of each);
  queries without coordinates form one block per country (``country_<cc>``); whole
  blocks are held out. A group that spans two blocks takes the block holding most of
  its queries (ties: the lexicographically first block), so a group never splits across
  folds in either split; such groups are listed in the manifest.

Blocks (or groups) are assigned to folds by the greedy balance of
``assign_folds.greedy_assign`` on query counts: repetition 0 is the deterministic
largest-first order, repetitions 1 to 4 block-shuffle that order with
``random.Random(rep)`` (``assign_folds.ordered_studies``), pure Python, no numpy sort.

``folds_manifest.json`` records the seed, ``n_reps``, ``n_folds``, the SHA-256 of the
query keys (``queries.query_hash``) and of both fold files, so two builds of the same
queries give byte-identical files (``--check`` verifies that).

Usage::

    python -m model.harness.folds [--check]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd

from model.harness import HARNESS_DIR, REPO_ROOT

if str(REPO_ROOT / "pipelines" / "dataset") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "pipelines" / "dataset"))
from assign_folds import greedy_assign, ordered_studies  # noqa: E402  (the P7 assigner, wrapped)

N_FOLDS = 5
N_REPS = 5
SEED = 0
SPLITS = ("spatial", "study")
FOLDS_SPATIAL = HARNESS_DIR / "folds_spatial.csv"
FOLDS_STUDY = HARNESS_DIR / "folds_study.csv"
FOLDS_MANIFEST = HARNESS_DIR / "folds_manifest.json"


def rep_cols(n_reps: int = N_REPS) -> list[str]:
    return [f"fold_rep{r:02d}" for r in range(n_reps)]


def spatial_block(lat: Any, lon: Any, country: Any) -> str:
    """``b<floor lat>_<floor lon>`` or ``country_<cc>`` without coordinates."""
    if lat is not None and lon is not None and not (isinstance(lat, float) and math.isnan(lat)) \
            and not (isinstance(lon, float) and math.isnan(lon)):
        return f"b{math.floor(float(lat))}_{math.floor(float(lon))}"
    return f"country_{country or 'unknown'}"


def group_blocks(queries: pd.DataFrame) -> tuple[dict[str, str], list[dict[str, Any]]]:
    """Block of every group (majority block) and the groups that span more than one block."""
    raw = Counter()
    for r in queries.itertuples():
        raw[(r.group, spatial_block(r.lat, r.lon, r.country))] += 1
    per_group: dict[str, Counter] = {}
    for (g, b), n in raw.items():
        per_group.setdefault(g, Counter())[b] += n
    block_of: dict[str, str] = {}
    spanning: list[dict[str, Any]] = []
    for g in sorted(per_group):
        c = per_group[g]
        best = sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
        block_of[g] = best
        if len(c) > 1:
            spanning.append({"group": g, "blocks": dict(sorted(c.items())), "assigned": best})
    return block_of, spanning


def assign_units(sizes: dict[str, int], n_folds: int = N_FOLDS, n_reps: int = N_REPS) -> dict[str, list[int]]:
    """unit -> fold per repetition, by the P7 greedy balance on ``sizes`` (query counts)."""
    per_rep = [greedy_assign(ordered_studies(sizes, rep), sizes, n_folds) for rep in range(n_reps)]
    return {u: [rep[u] for rep in per_rep] for u in sorted(sizes)}


def build_folds(queries: pd.DataFrame, split: str, n_folds: int = N_FOLDS, n_reps: int = N_REPS
                ) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    """Fold table for one split: ``query_id, group, block, fold_rep00..``."""
    q = queries[~queries["legacy"]] if "legacy" in queries.columns else queries
    q = q.sort_values("query_id").reset_index(drop=True)
    block_of, spanning = group_blocks(q)
    unit_of = {g: (block_of[g] if split == "spatial" else g) for g in block_of}
    units = q["group"].map(unit_of)
    sizes = {u: int(n) for u, n in units.value_counts().items()}
    assignment = assign_units(sizes, n_folds, n_reps)
    out = pd.DataFrame({"query_id": q["query_id"], "group": q["group"], "block": q["group"].map(block_of)})
    for r, col in enumerate(rep_cols(n_reps)):
        out[col] = [assignment[u][r] for u in units]
    return out, spanning


def write_folds(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, lineterminator="\n", encoding="utf-8")


def load_folds(path: Path) -> pd.DataFrame:
    """The one fold reader: a frame indexed by ``query_id`` with ``group``, ``block`` and the rep columns."""
    if not Path(path).exists():
        raise FileNotFoundError(f"{path} not found: python -m model.harness.folds")
    df = pd.read_csv(path, dtype={"query_id": str, "group": str, "block": str})
    reps = [c for c in df.columns if c.startswith("fold_rep")]
    df[reps] = df[reps].astype(int)
    return df.set_index("query_id")


def fold_members(folds: pd.DataFrame, rep: int, fold: int) -> tuple[list[str], list[str]]:
    """``(held-out query ids, held-out groups)`` of one fold of one repetition."""
    col = f"fold_rep{rep:02d}"
    held = folds[folds[col] == fold]
    return list(held.index), sorted(set(held["group"]))


def check_integrity(folds: pd.DataFrame, split: str) -> dict[str, Any]:
    """Every group (and block, for the spatial split) sits in one fold per repetition; sizes balanced."""
    reps = [c for c in folds.columns if c.startswith("fold_rep")]
    problems = []
    for col in reps:
        if (folds.groupby("group")[col].nunique() > 1).any():
            problems.append(f"{col}: a group spans folds")
        if split == "spatial" and (folds.groupby("block")[col].nunique() > 1).any():
            problems.append(f"{col}: a block spans folds")
    sizes = {col: folds[col].value_counts().sort_index().tolist() for col in reps}
    return {"ok": not problems, "problems": problems, "fold_sizes": sizes}


def file_sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build the deterministic harness folds")
    ap.add_argument("--harness-dir", type=Path, default=HARNESS_DIR)
    ap.add_argument("--n-folds", type=int, default=N_FOLDS)
    ap.add_argument("--n-reps", type=int, default=N_REPS)
    ap.add_argument("--check", action="store_true", help="rebuild in memory and compare hashes with the files on disk")
    a = ap.parse_args(argv)
    from model.harness.queries import load_queries, query_hash

    queries, _ = load_queries(a.harness_dir)
    built: dict[str, pd.DataFrame] = {}
    manifest: dict[str, Any] = {"seed": SEED, "n_reps": a.n_reps, "n_folds": a.n_folds,
                                "query_hash": query_hash(queries), "n_queries": int((~queries["legacy"]).sum()),
                                "assigner": "pipelines/dataset/assign_folds.py (greedy balance, block shuffle)",
                                "splits": {}}
    for split, path in (("spatial", a.harness_dir / FOLDS_SPATIAL.name), ("study", a.harness_dir / FOLDS_STUDY.name)):
        df, spanning = build_folds(queries, split, a.n_folds, a.n_reps)
        built[split] = df
        integrity = check_integrity(df.set_index("query_id"), split)
        if not integrity["ok"]:
            raise SystemExit(f"fold integrity failed for {split}: {integrity['problems']}")
        if a.check:
            tmp = path.with_suffix(".check.csv")
            write_folds(df, tmp)
            same = file_sha256(tmp) == file_sha256(path)
            tmp.unlink()
            print(f"{split}: {'identical' if same else 'DIFFERENT'} to {path.name}")
            if not same:
                return 1
            continue
        write_folds(df, path)
        manifest["splits"][split] = {"file": path.name, "sha256": file_sha256(path), "n_units": int(df["block" if split == "spatial" else "group"].nunique()),
                                     "fold_sizes": integrity["fold_sizes"],
                                     "groups_spanning_blocks": spanning if split == "spatial" else None}
        print(f"{split}: {len(df)} queries, {manifest['splits'][split]['n_units']} units, fold sizes rep0 "
              f"{integrity['fold_sizes']['fold_rep00']}" + (f", {len(spanning)} groups span blocks" if split == "spatial" else ""))
    if not a.check:
        (a.harness_dir / FOLDS_MANIFEST.name).write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")
        print(f"wrote {a.harness_dir / FOLDS_MANIFEST.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
