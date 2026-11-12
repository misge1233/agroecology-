"""Fit the final Methodology 1 v2 engine and write the serving artifact (E5 Part 4).

``python -m model.m1.train --release ET/2026.1`` fits the engine on every eligible store row
(no mask) with the selected configuration and writes ``model/artifacts/m1_v2/``:

* ``m1_v2.joblib`` (the fitted :class:`model.m1.engine.M1Engine`; git-ignored),
* ``features.json`` (the active feature names and the per-fold stability table when a
  harness run with feature selection is given with ``--selection-from``),
* ``config.json`` (engine configuration, the store manifest, release id, query and fold
  hashes, index hash, git commit, fit summary: stacker choice and weights, conformal
  quantile, matched k),
* ``model_card.md`` (data, features, components, metrics with intervals when a harness
  run is given with ``--metrics-from``, limitations, intended use).

The frozen artifact contract is untouched: ``csa_model.joblib`` and ``recommend.py`` are
not read or written here; the backend loads this artifact only behind
``ADVISOR_ENGINE=m1_v2``.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
from pathlib import Path
from typing import Any

import joblib

from model.harness import HARNESS_DIR, RELEASE, REPO_ROOT
from model.harness import queries as hq
from model.harness import run as hr
from model.harness.mask import Mask
from model.m1 import ARTIFACT_DIR
from model.m1.engine import M1Config, M1Engine

ARTIFACT = "m1_v2.joblib"


def file_sha256(path: Path) -> str | None:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest() if Path(path).exists() else None


def engine_maps(taxonomy: Any) -> dict[str, Any]:
    """The taxonomy maps the engine needs (the same construction as the harness)."""
    from pipelines.geodata.extract import load_aez_lookup

    return {"outcome_group": {str(r.outcome_id): str(r.objective_group) for r in taxonomy.outcomes.itertuples()},
            "family_of": {str(r.practice_id): str(r.practice_family) for r in taxonomy.practices.itertuples()},
            "components_of": {str(r.practice_id): [c.strip() for c in str(r.components).split(";") if c.strip()]
                              for r in taxonomy.practices.itertuples()},
            "belt_code_of": {name: code for code, name in load_aez_lookup().items()}}


def model_card(cfg: M1Config, summary: dict[str, Any], config: dict[str, Any], metrics: dict[str, Any] | None,
               stable: list[str] | None) -> str:
    L = ["# Model card: Methodology 1 v2 (`m1_v2`)", "",
         f"Built {config['built_utc']} by `model/m1/train.py` from the evidence store ({summary['n_rows']:,} eligible rows, "
         f"{summary['n_groups']} study groups, {summary['n_training_queries']} training queries) with release "
         f"`{config['release']}` context; git `{config['git_commit']}`. Serves behind `ADVISOR_ENGINE=m1_v2` "
         "(default `legacy`: the frozen `csa_model.joblib` path is unchanged).", "",
         "## What it does", "",
         "Ranks every candidate practice for a site, a challenge and an objective (any canonical outcome in the registry) "
         "and gives an effect estimate on the oriented log response ratio scale with a conformal 80 % interval. Four "
         "components feed one combination rule: an effect regressor (HistGradientBoosting on the oriented effect), a "
         "within-study ranker (LightGBM lambdarank on the training queries), context-matched studies (DerSimonian-Laird "
         "pooling of the nearest training sites) and a shrunken practice prior (empirical Bayes toward component, family "
         "and grand means). The prior answers every candidate, so the engine never abstains; `lead_source` names the "
         "component with the largest contribution (model, matched_studies, prior = model-led, study-led, documented).", "",
         "## Data", "",
         "Store rows with a reviewed direction, a computable `lrr`, practice and outcome ids, not a duplicate, not an "
         f"unchecked geocode; weights `{cfg.data.weight_scheme}`. Country-precision rows enter with the reported context "
         "and a `ctx_missing` flag. Nothing is learned from a query's own rows; in evaluation every learned quantity was "
         "fitted inside the outer training fold (nested inner folds).", "",
         "## Features", "",
         f"{len(summary['features'])} active features: the release context layers, belt and Köppen class as categorical "
         "attributes, land cover, crop group, practice family, outcome id, objective group, source, quality flag, location "
         "precision, duration, the practice components (multi-hot) and the practice target encoding with counts "
         "(out-of-fold on the training rows).", ""]
    if isinstance(summary.get("feature_selection"), list):
        dropped = [r["group"] for r in summary["feature_selection"] if not r["kept"]]
        L += [f"Grouped permutation selection on the inner folds dropped: {', '.join(dropped) or 'nothing'}.", ""]
    if stable:
        L += [f"Features stable in at least 4 of 5 outer folds (spatial split, repetition 0; `feature_stability.json`): {len(stable)}, served exactly (`features.json`).", ""]
    L += ["## Components and combination", "",
          f"- regressor: `{summary['regressor_params']}`",
          f"- ranker: {summary.get('ranker')}",
          f"- matched studies: k = {summary.get('matched_k', cfg.matched_k)}, decay power {summary.get('matched_power', cfg.matched_power)}, "
          f"k_min = {cfg.k_min}",
          f"- prior: kappa {summary['prior']['kappa']:.2f}, sigma2 {summary['prior']['sigma2']:.3f}, tau2 {summary['prior']['tau2']:.4f}",
          (f"- stacker: `{summary['stacker']['chosen']}` (inner comparison ridge {summary['stacker']['ridge']} vs rank averaging {summary['stacker']['rank_avg']})"
           if summary["stacker"].get("ridge") else
           f"- stacker: `{summary['stacker']['chosen']}`, fixed to the choice made inside the majority of the outer folds of the "
           "evaluation (`per_fold_choices.json`: rank averaging in 8 of 10 fits, all 5 spatial folds)"),
          f"- conformal: 80 % quantile {summary['conformal']['q']:.3f} on {summary['conformal']['n_calibration']} inner out-of-fold items", ""]
    if metrics:
        L += ["## Evaluation (E4 harness, ET set, full coverage, mean across 5 x 5 folds)", "",
              "| split | top-1 hit | chance | C-index | NDCG@3 | 80 % coverage | width |", "|---|---:|---:|---:|---:|---:|---:|"]
        for split, v in metrics.items():
            L.append(f"| {split} | {v['top1_hit']:.3f} | {v['top1_chance']:.3f} | {v['c_index']:.3f} | {v['ndcg3']:.3f} | "
                     f"{v['coverage80']:.2f} | {v['width80']:.2f} |")
        L.append("")
    L += ["## Limitations", "",
          "- Evidence is thin for many practice x outcome cells: the prior leads there, and its interval is a shrinkage "
          "interval, not a prediction interval.",
          "- Context outside Ethiopia and country-precision sites carry only the reported rainfall, altitude and slope.",
          "- The ranker and regressor learn from the same 800-odd studies; a new practice with no rows is placed by its "
          "components and family only.",
          "- Numbers shown to users must carry their provenance (`lead_source`, citations) as every other source does.", "",
          "## Intended use", "",
          "Ranking and effect estimates behind the advisory when `ADVISOR_ENGINE=m1_v2`; not a substitute for the "
          "study-level evidence and guidance that the fusion layer shows beside it.", ""]
    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Fit the final M1 v2 engine and write the serving artifact")
    ap.add_argument("--release", default=RELEASE)
    ap.add_argument("--store-dir", type=Path, default=REPO_ROOT / "data" / "evidence")
    ap.add_argument("--out", type=Path, default=ARTIFACT_DIR)
    ap.add_argument("--metrics-from", type=Path, default=None, help="harness run folder whose m1_v2 metrics go on the card")
    ap.add_argument("--no-tune", dest="tune", action="store_false")
    ap.add_argument("--no-select", dest="select", action="store_false")
    a = ap.parse_args(argv)
    store = hr.load_store(a.store_dir)
    taxonomy = hr.load_taxonomy()
    stability_path = a.out / "feature_stability.json"
    stable = None
    if stability_path.exists():  # E5 Part 1: serve only the features stable in >= 4 of 5 outer folds
        stable = json.loads(stability_path.read_text(encoding="utf-8"))["stable"]
    stacker = "auto"
    choices_path = a.out / "per_fold_choices.json"
    if choices_path.exists():  # E5: serve the stacker chosen inside the majority of outer folds (stability rule)
        votes = [c["stacker"] for c in json.loads(choices_path.read_text(encoding="utf-8"))]
        stacker = max(sorted(set(votes)), key=votes.count)
    cfg = M1Config(tune=a.tune, select=a.select, fixed_features=tuple(stable) if stable else None, stacker=stacker)
    engine = M1Engine(cfg, **engine_maps(taxonomy))
    summary = engine.fit(store, Mask.empty())
    a.out.mkdir(parents=True, exist_ok=True)
    joblib.dump(engine, a.out / ARTIFACT)
    queries_all, _ = hq.load_queries(HARNESS_DIR) if (HARNESS_DIR / "queries.parquet").exists() else (None, None)
    metrics = None
    if a.metrics_from and (a.metrics_from / "metrics.json").exists():
        m = json.loads((a.metrics_from / "metrics.json").read_text(encoding="utf-8"))
        agg = (m.get("full_coverage") or {}).get("aggregate", {}).get("m1_v2") or m.get("aggregate", {}).get("m1_v2") or {}
        metrics = {s: {k: v[k]["mean"] for k in ("top1_hit", "top1_chance", "c_index", "ndcg3", "coverage80", "width80")}
                   for s, v in agg.items()}
    config = {"engine": "m1_v2", "built_utc": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
              "release": a.release, "git_commit": hr.git_commit(),
              "store_manifest_sha256": file_sha256(a.store_dir / "store_manifest.json"),
              "store_rows": int(len(store)), "query_hash": hq.query_hash(queries_all) if queries_all is not None else None,
              "fold_files": {s: file_sha256(HARNESS_DIR / f"folds_{s}.csv") for s in ("spatial", "study")},
              "index_hash": hr.tier1_index_hash(), "config": {**cfg.__dict__, "data": cfg.data.__dict__},
              "fit": {k: v for k, v in summary.items() if k not in ("feature_selection", "regressor_grid", "matched_grid")},
              "metrics_from": str(a.metrics_from) if a.metrics_from else None, "artifact": ARTIFACT}
    (a.out / "config.json").write_text(json.dumps(config, indent=1, default=str) + "\n", encoding="utf-8")
    (a.out / "features.json").write_text(json.dumps({"active": summary["features"], "selection": summary.get("feature_selection"),
                                                     "regressor_grid": summary.get("regressor_grid"), "matched_grid": summary.get("matched_grid")},
                                                    indent=1, default=str) + "\n", encoding="utf-8")
    (a.out / "model_card.md").write_text(model_card(cfg, summary, config, metrics, stable), encoding="utf-8")
    print(f"wrote {a.out / ARTIFACT} ({summary['n_rows']} rows, {len(summary['features'])} features, "
          f"stacker {summary['stacker']['chosen']}, conformal q {summary['conformal']['q']:.3f}, {summary['fit_seconds']} s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
