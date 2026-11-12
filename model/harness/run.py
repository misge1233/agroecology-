"""Run methods through the harness and write predictions, metrics and the report (E4 Part 5).

For every split (``spatial``, ``study``, or ``legacy`` = the P7 grouped folds of
``data/processed/cv_folds.csv`` for the ``legacy_68`` queries), every repetition and
every fold: build the :class:`Mask` of the held-out groups, fit each engine on the
training rows (the engine applies the mask), rank the held-out queries, collect one
prediction row per candidate. Then score everything with :mod:`model.metrics` and write

* ``model/harness/runs/<run_id>/predictions.parquet`` (``run_id, method, split, fold, rep,
  query_id, practice_id, score, est_lrr, lo, hi, abstain, lead_source, citations``),
* ``metrics.json`` (mean and sd across repetitions, query-level bootstrap intervals,
  breakdowns, the random engine's analytic expectations, unmaskable chunk counts),
* ``config.json`` (methods and their parameters, query and fold hashes, Tier 1 index
  hash, release id, git commit, timings), ``per_query.parquet``,
* ``model/reports/eval_<date>_<run_id>.md`` with the PNG figures (:mod:`report`).

Two runs with the same inputs give identical metrics (``compare_runs``).

Usage::

    python -m model.harness.run --methods random,practice_prior,nearest_studies,m0_current --split spatial,study --reps 5
    python -m model.harness.run --methods m0_current --split legacy --query-set legacy_68
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import logging
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pandas as pd

from model import metrics as mm
from model.engines import registry
from model.engines.base import RankRequest
from model.harness import HARNESS_DIR, RELEASE, REPO_ROOT, RUNS_DIR
from model.harness import folds as hf
from model.harness import queries as hq
from model.harness.mask import Mask

logger = logging.getLogger(__name__)

PREDICTION_COLUMNS = ["run_id", "method", "split", "fold", "rep", "query_id", "practice_id", "score", "est_lrr", "lo",
                      "hi", "abstain", "lead_source", "citations"]
CV_FOLDS = REPO_ROOT / "data" / "processed" / "cv_folds.csv"
TIER1_CHUNKS = REPO_ROOT / "rag" / "corpus" / "chunks.jsonl"
HEADLINE_BOOT = ("top1_hit", "tophalf_hit", "c_index", "ndcg3", "spearman_median")
BREAKDOWNS = (("objective_group", None), ("challenge_ids", ";"), ("belt", None), ("sources", None),
              ("loc_precision", None), ("query_set", None), ("post_2024", None))


# ----------------------------------------------------------------- inputs
def git_commit() -> str | None:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True, timeout=10)
        dirty = subprocess.run(["git", "status", "--porcelain"], cwd=REPO_ROOT, capture_output=True, text=True, timeout=10)
        return (out.stdout.strip() + ("+dirty" if dirty.stdout.strip() else "")) or None
    except (OSError, subprocess.SubprocessError):
        return None


def file_sha256(path: Path) -> str | None:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest() if Path(path).exists() else None


def tier1_index_hash() -> str | None:
    if not TIER1_CHUNKS.exists():
        return None
    from rag.retrieve import index_hash

    return index_hash(TIER1_CHUNKS)


def load_taxonomy() -> Any:
    from pipelines.taxonomy import taxonomy_io as tio

    return tio.Taxonomy.load()


def load_store(store_dir: Path) -> pd.DataFrame:
    from pipelines.evidence import schema

    return schema.read_store(store_dir)


def select_queries(queries: pd.DataFrame, query_set: str) -> pd.DataFrame:
    if query_set == "all":
        return queries[~queries["legacy"]]
    if query_set == "post_2024":
        return queries[queries["post_2024"] & ~queries["legacy"]]
    return queries[queries["query_set"] == query_set]


def make_engine(name: str, taxonomy: Any, store: pd.DataFrame, seed: int = 0) -> Any:
    """An engine with the taxonomy maps it needs (outcome -> objective group, practice -> family, id -> label)."""
    cls = registry()[name]
    outcome_group = {str(r.outcome_id): str(r.objective_group) for r in taxonomy.outcomes.itertuples()}
    family_of = {str(r.practice_id): str(r.practice_family) for r in taxonomy.practices.itertuples()}
    if name == "random":
        return cls(seed=seed)
    if name == "practice_prior":
        return cls(outcome_group=outcome_group, family_of=family_of)
    if name == "nearest_studies":
        return cls(outcome_group=outcome_group)
    if name == "m0_current":
        return cls(label_of=hq.dataset_labels(store))
    if name in ("component_count", "input_intensity"):  # E7 Part A4: heuristic baselines
        components_of = {str(r.practice_id): [c.strip() for c in str(r.components).split(";") if c.strip()]
                         for r in taxonomy.practices.itertuples()}
        return cls(outcome_group=outcome_group, family_of=family_of, components_of=components_of)
    if name.startswith("m1_"):  # E5: Methodology 1 v2 and its variants
        components_of = {str(r.practice_id): [c.strip() for c in str(r.components).split(";") if c.strip()]
                         for r in taxonomy.practices.itertuples()}
        try:
            from pipelines.geodata.extract import load_aez_lookup

            belt_code_of = {name_: code for code, name_ in load_aez_lookup().items()}
        except Exception:  # noqa: BLE001 - the lookup is optional (tests)
            belt_code_of = {}
        return cls(outcome_group=outcome_group, family_of=family_of, components_of=components_of, belt_code_of=belt_code_of)
    return cls()


def request_of(q: pd.Series, items: pd.DataFrame, mask: Mask) -> RankRequest:
    ctx = json.loads(q["context"]) if isinstance(q["context"], str) else dict(q["context"] or {})
    legacy_rows: dict[str, list[int]] = {}
    if q.get("legacy", False):
        for it in items[items["query_id"] == q["query_id"]].itertuples():
            if isinstance(it.rows_json, str):
                legacy_rows[str(it.practice_id)] = json.loads(it.rows_json)
    return RankRequest(
        query_id=str(q["query_id"]), context=ctx,
        challenge_ids=[c for c in str(q["challenge_ids"] or "").split(";") if c],
        outcome_id=str(q["outcome_id"]), candidates=[c for c in str(q["candidates"]).split(";") if c],
        crop=q["crop"] if isinstance(q["crop"], str) else None,
        user_attrs={"sources": q.get("sources"), "loc_precision": q.get("loc_precision")}, mask=mask,
        direction=int(q["direction"]), objective_group=str(q["objective_group"]),
        legacy_indicator=q["legacy_indicator"] if isinstance(q["legacy_indicator"], str) else None,
        legacy_rows=legacy_rows,
    )


# ----------------------------------------------------------------- fold plans
def fold_plan(split: str, queries: pd.DataFrame, harness_dir: Path, reps: int, store: pd.DataFrame
              ) -> list[tuple[int, int, list[str], Mask]]:
    """``(rep, fold, held-out query ids, mask)`` for every fold of a split, restricted to ``queries``."""
    plan: list[tuple[int, int, list[str], Mask]] = []
    wanted = set(queries["query_id"])
    if split == "fresh":  # E7 A6: one fold, every selected query held out, trained on everything else
        return [(0, 0, sorted(wanted), Mask.from_groups(sorted(set(queries["group"].astype(str))), store))]
    if split == "legacy":
        from assign_folds import load_folds  # pipelines/dataset (on sys.path via model.harness)

        folds = load_folds(CV_FOLDS)
        n_reps = min(reps, len(next(iter(folds.values()))))
        by_group = queries.groupby("group")["query_id"].apply(list)
        for rep in range(n_reps):
            for fold in range(hf.N_FOLDS):
                studies = sorted(s for s, f in folds.items() if f[rep] == fold)
                held = [qid for s in studies for qid in by_group.get(s, []) if qid in wanted]
                plan.append((rep, fold, held, Mask.from_groups(studies, store)))
        return plan
    path = harness_dir / (hf.FOLDS_SPATIAL.name if split == "spatial" else hf.FOLDS_STUDY.name)
    folds = hf.load_folds(path)
    n_reps = min(reps, len([c for c in folds.columns if c.startswith("fold_rep")]))
    for rep in range(n_reps):
        for fold in range(hf.N_FOLDS):
            held, groups = hf.fold_members(folds, rep, fold)
            held = [h for h in held if h in wanted]
            plan.append((rep, fold, held, Mask.from_groups(groups, store)))
    return plan


# ----------------------------------------------------------------- the run
def run(methods: list[str], splits: list[str], reps: int = hf.N_REPS, query_set: str = "ET", seed: int = 0,
        harness_dir: Path = HARNESS_DIR, store_dir: Path = REPO_ROOT / "data" / "evidence",
        out_dir: Path = RUNS_DIR, run_id: str | None = None, report: bool = True,
        queries_override: pd.DataFrame | None = None, items_override: pd.DataFrame | None = None,
        store_override: pd.DataFrame | None = None, taxonomy_override: Any = None,
        fill_prior: bool = True, engine_overrides: dict[str, Any] | None = None) -> Path:
    """Run every method on every split and write the run folder; returns its path.

    ``fill_prior`` adds the ``<method>+prior`` full-coverage variants when ``practice_prior``
    is among the methods (E5 Part 0); ``engine_overrides`` maps a method name to a ready
    engine instance (tests, ablation configurations)."""
    t_start = time.time()
    queries_all, items = (queries_override, items_override) if queries_override is not None else hq.load_queries(harness_dir)
    store = store_override if store_override is not None else load_store(store_dir)
    taxonomy = taxonomy_override or load_taxonomy()
    queries = select_queries(queries_all, query_set).reset_index(drop=True)
    if queries.empty:
        raise ValueError(f"no queries in set {query_set!r}")
    train_rows = hq.eligible_rows(store)
    engines = {m: (engine_overrides or {}).get(m) or make_engine(m, taxonomy, store, seed) for m in methods}
    config: dict[str, Any] = {
        "methods": {m: (e.params() if hasattr(e, "params") else {}) for m, e in engines.items()},
        "splits": splits, "reps": reps, "query_set": query_set, "seed": seed, "n_queries": int(len(queries)),
        "query_hash": hq.query_hash(queries_all), "fold_files": {}, "index_hash": tier1_index_hash(),
        "release": RELEASE, "git_commit": git_commit(), "store_rows": int(len(store)),
        "started_utc": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
    }
    for split in splits:
        if split == "fresh":  # no fold file: the held-out set is the query set itself
            config["fold_files"][split] = {"file": None, "rule": "all selected queries held out in one fold"}
            continue
        p = {"spatial": harness_dir / hf.FOLDS_SPATIAL.name, "study": harness_dir / hf.FOLDS_STUDY.name,
             "legacy": CV_FOLDS}[split]
        config["fold_files"][split] = {"file": str(p.relative_to(REPO_ROOT)) if p.is_relative_to(REPO_ROOT) else str(p),
                                       "sha256": file_sha256(p)}
    rid = run_id or (_dt.date.today().isoformat() + "_" + hashlib.sha256(json.dumps(
        {k: config[k] for k in ("methods", "splits", "reps", "query_set", "seed", "query_hash", "fold_files")},
        sort_keys=True, default=str).encode()).hexdigest()[:8])
    config["run_id"] = rid
    rows: list[dict[str, Any]] = []
    timings: dict[str, float] = {}
    unmaskable: dict[str, int] = {}
    for split in splits:
        plan = fold_plan(split, queries, harness_dir, reps, store)
        for rep, fold, held, mask in plan:
            if not held:
                continue
            held_q = queries[queries["query_id"].isin(held)]
            for m, eng in engines.items():
                t0 = time.time()
                eng.fit(train_rows, mask)
                for _, q in held_q.iterrows():
                    req = request_of(q, items, mask)
                    for it in eng.rank(req):
                        rows.append({"run_id": rid, "method": m, "split": split, "fold": fold, "rep": rep,
                                     "query_id": req.query_id, "practice_id": it.practice_id, "score": float(it.score),
                                     "est_lrr": it.est_lrr, "lo": it.lo, "hi": it.hi, "abstain": bool(it.abstain),
                                     "lead_source": it.lead_source, "citations": ";".join(it.citations or [])})
                timings[f"{m}:{split}"] = timings.get(f"{m}:{split}", 0.0) + time.time() - t0
                for cid, n in getattr(eng, "unmaskable", {}).items():
                    unmaskable[cid] = unmaskable.get(cid, 0) + n
            logger.info("%s rep %d fold %d: %d queries", split, rep, fold, len(held))
    preds = pd.DataFrame(rows, columns=PREDICTION_COLUMNS)
    for c in ("est_lrr", "lo", "hi"):
        preds[c] = pd.to_numeric(preds[c], errors="coerce")
    if fill_prior:
        preds = mm.fill_abstentions(preds)  # E5 Part 0: <method>+prior variants for full coverage
    run_dir = out_dir / rid
    run_dir.mkdir(parents=True, exist_ok=True)
    preds.to_parquet(run_dir / "predictions.parquet", engine="pyarrow", index=False)
    pq = mm.per_query_table(preds, items)
    pq.to_parquet(run_dir / "per_query.parquet", engine="pyarrow", index=False)
    metrics = build_metrics(pq, preds, items, queries, methods, splits, unmaskable)
    # parameters again after fitting: engines that learn per fold (m1_*) report their per-fold choices
    config["methods"] = {m: (e.params() if hasattr(e, "params") else {}) for m, e in engines.items()}
    config["timings_s"] = {k: round(v, 1) for k, v in timings.items()}
    config["elapsed_s"] = round(time.time() - t_start, 1)
    (run_dir / "metrics.json").write_text(json.dumps(_clean(metrics), indent=1, default=_json_default) + "\n",
                                          encoding="utf-8")
    (run_dir / "config.json").write_text(json.dumps(config, indent=1, default=str) + "\n", encoding="utf-8")
    if report:
        from model.harness.report import write_report

        write_report(run_dir, metrics, config, preds, items, queries, pq)
    return run_dir


def _json_default(o: Any) -> Any:
    if isinstance(o, float) and o != o:
        return None
    return str(o)


def _clean(obj: Any) -> Any:
    """``nan`` floats become ``null`` so ``metrics.json`` is strict JSON."""
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_clean(v) for v in obj]
    if isinstance(obj, float) and obj != obj:
        return None
    return obj


def build_metrics(pq: pd.DataFrame, preds: pd.DataFrame, items: pd.DataFrame, queries: pd.DataFrame,
                  methods: list[str], splits: list[str], unmaskable: dict[str, int]) -> dict[str, Any]:
    """The ``metrics.json`` body."""
    agg = mm.aggregate(pq)
    boot: dict[str, dict[str, dict[str, Any]]] = {}
    for m in methods:
        for s in splits:
            block = pq[(pq["method"] == m) & (pq["split"] == s)]
            if block.empty:
                continue
            boot.setdefault(m, {})[s] = {k: mm.bootstrap(block, k) for k in HEADLINE_BOOT}
    breakdowns: dict[str, Any] = {}
    for by, sep in BREAKDOWNS:
        if by not in queries.columns:
            continue
        table = mm.breakdown(pq, queries, by, explode=sep)
        breakdowns[by] = table.to_dict(orient="records")
    sizes = queries["n_practices"].tolist()
    all_methods = sorted(pq["method"].unique())
    # E5 Part 0: full coverage = methods that never abstain (own rows or the +prior variant);
    # common subset = queries every compared method answered in every repetition; paired
    # bootstrap differences between every two full-coverage methods.
    full = [m for m in all_methods if all(v["abstention_rate"]["mean"] == 0 for v in agg.get(m, {}).values())]
    base_of = {m: (m[:-len(mm.FILL_SUFFIX)] if m.endswith(mm.FILL_SUFFIX) else m) for m in full}
    full = [m for m in full if not (m.endswith(mm.FILL_SUFFIX) and base_of[m] in full)]
    compared = [m for m in all_methods if not m.endswith(mm.FILL_SUFFIX)]
    common: dict[str, Any] = {}
    for split, sub in mm.common_subset(pq, compared).items():
        common[split] = {"n": sub["n"], "methods": compared,
                         "aggregate": {m: v.get(split, {}) for m, v in mm.aggregate(sub["per_query"]).items()}}
    paired: dict[str, Any] = {}
    for i, a in enumerate(full):
        for b in full[i + 1:]:
            paired[f"{a} vs {b}"] = mm.paired_bootstrap(pq, a, b)
    return {"aggregate": agg, "bootstrap95": boot, "breakdowns": breakdowns,
            "full_coverage": {"methods": full, "aggregate": {m: agg[m] for m in full}},
            "common_subset": common, "paired": paired,
            "random_expectation": mm.expected_random(sizes) if sizes else {},
            "unmaskable_chunks": {"n_distinct": len(unmaskable), "hits": int(sum(unmaskable.values())),
                                  "chunk_ids": sorted(unmaskable)[:50]},
            "n_queries": int(len(queries)), "min_cell": mm.MIN_CELL}


def rescore(run_dir: Path, harness_dir: Path = HARNESS_DIR, report: bool = True) -> Path:
    """Recompute ``per_query.parquet``, ``metrics.json`` and the report of a run from its saved
    predictions (no engine is refitted); ``config.json`` is kept, with a ``rescored_utc`` stamp."""
    run_dir = Path(run_dir)
    config = json.loads((run_dir / "config.json").read_text(encoding="utf-8"))
    preds = mm.fill_abstentions(pd.read_parquet(run_dir / "predictions.parquet"))  # idempotent (E5 Part 0)
    queries_all, items = hq.load_queries(harness_dir)
    queries = select_queries(queries_all, config["query_set"]).reset_index(drop=True)
    pq = mm.per_query_table(preds, items)
    pq.to_parquet(run_dir / "per_query.parquet", engine="pyarrow", index=False)
    methods = sorted(preds["method"].unique())
    splits = [s for s in config["splits"] if s in set(preds["split"])]
    old = json.loads((run_dir / "metrics.json").read_text(encoding="utf-8")) if (run_dir / "metrics.json").exists() else {}
    unmask = old.get("unmaskable_chunks") or {}
    metrics = build_metrics(pq, preds, items, queries, methods, splits,
                            {c: 1 for c in unmask.get("chunk_ids", [])})
    metrics["unmaskable_chunks"] = unmask or metrics["unmaskable_chunks"]
    config["rescored_utc"] = _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")
    (run_dir / "metrics.json").write_text(json.dumps(_clean(metrics), indent=1, default=_json_default) + "\n",
                                          encoding="utf-8")
    (run_dir / "config.json").write_text(json.dumps(config, indent=1, default=str) + "\n", encoding="utf-8")
    if report:
        from model.harness.report import write_report

        write_report(run_dir, metrics, config, preds, items, queries, pq)
    return run_dir


def compare_runs(a: Path, b: Path, places: int = 3) -> list[str]:
    """Metrics that differ between two run folders at ``places`` decimals (empty = identical)."""
    ma = json.loads((Path(a) / "metrics.json").read_text(encoding="utf-8"))["aggregate"]
    mb = json.loads((Path(b) / "metrics.json").read_text(encoding="utf-8"))["aggregate"]
    diffs = []
    for m in sorted(set(ma) | set(mb)):
        for s in sorted(set(ma.get(m, {})) | set(mb.get(m, {}))):
            for k in sorted(set(ma.get(m, {}).get(s, {})) | set(mb.get(m, {}).get(s, {}))):
                va, vb = ma.get(m, {}).get(s, {}).get(k), mb.get(m, {}).get(s, {}).get(k)
                for stat in ("mean", "sd"):
                    xa, xb = (va or {}).get(stat), (vb or {}).get(stat)
                    na = xa is None or (isinstance(xa, float) and xa != xa)
                    nb = xb is None or (isinstance(xb, float) and xb != xb)
                    if na and nb:
                        continue
                    if na or nb or round(float(xa), places) != round(float(xb), places):
                        diffs.append(f"{m}/{s}/{k}/{stat}: {xa} vs {xb}")
    return diffs


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run methods through the evaluation harness")
    ap.add_argument("--methods", default="random,practice_prior,nearest_studies,m0_current")
    ap.add_argument("--split", default="spatial,study", help="comma list of spatial, study, legacy")
    ap.add_argument("--reps", type=int, default=hf.N_REPS)
    ap.add_argument("--query-set", default="ET", help="ET, global, all, post_2024 or legacy_68")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--run-id", default=None)
    ap.add_argument("--harness-dir", type=Path, default=HARNESS_DIR)
    ap.add_argument("--store-dir", type=Path, default=REPO_ROOT / "data" / "evidence")
    ap.add_argument("--out-dir", type=Path, default=RUNS_DIR)
    ap.add_argument("--no-report", dest="report", action="store_false")
    ap.add_argument("--no-fill", dest="fill_prior", action="store_false",
                    help="do not add the <method>+prior full-coverage variants")
    ap.add_argument("--compare", nargs=2, metavar=("RUN_A", "RUN_B"), help="compare two run folders and exit")
    ap.add_argument("--rescore", metavar="RUN_DIR", help="re-score a run folder from its predictions and exit")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO if a.verbose else logging.WARNING, format="%(levelname)s %(message)s")
    if a.compare:
        diffs = compare_runs(Path(a.compare[0]), Path(a.compare[1]))
        print("identical to 3 decimals" if not diffs else "\n".join(diffs))
        return 0 if not diffs else 1
    if a.rescore:
        run_dir = rescore(Path(a.rescore), a.harness_dir, a.report)
        print(f"rescored {run_dir}")
        metrics = json.loads((run_dir / "metrics.json").read_text(encoding="utf-8"))
        for m, by_split in metrics["aggregate"].items():
            for s, v in by_split.items():
                print(f"{m:16s} {s:8s} top1 {v['top1_hit']['mean']:.4f} C {v['c_index']['mean']:.4f} "
                      f"C_pooled {v['c_index_pooled']['mean']:.4f} +- {v['c_index_pooled']['sd']:.4f} "
                      f"rho_med {v['spearman_median']['mean']:.4f}")
        return 0
    methods = [m for m in a.methods.split(",") if m]
    splits = [s for s in a.split.split(",") if s]
    run_dir = run(methods, splits, a.reps, a.query_set, a.seed, a.harness_dir, a.store_dir, a.out_dir, a.run_id, a.report,
                  fill_prior=a.fill_prior)
    metrics = json.loads((run_dir / "metrics.json").read_text(encoding="utf-8"))
    for m, by_split in metrics["aggregate"].items():
        for s, v in by_split.items():
            print(f"{m:16s} {s:8s} top1 {v['top1_hit']['mean']:.3f} (chance {v['top1_chance']['mean']:.3f}) "
                  f"C {v['c_index']['mean']:.3f} ndcg3 {v['ndcg3']['mean']:.3f} rho_med {v['spearman_median']['mean']:.3f} "
                  f"abstain {v['abstention_rate']['mean']:.2f} n {v['n_queries']['mean']:.0f}")
    print(f"wrote {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
