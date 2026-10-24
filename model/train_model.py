#!/usr/bin/env python3
"""
train_model.py  -  train & select the CSA response-ratio model (P7 protocol).

- 13 features (see feature_selection_report.md). Target: log_response_ratio.
- **Cross-validation is delegated to model/evaluate.py** (wrap, never fork):
  deterministic grouped folds read from data/processed/cv_folds.csv, repeated
  10 x 5, reported as mean +- sd, with ranking metrics, a leakage ablation and
  the noise ceiling. This script keeps its CLI and its artefact outputs; it
  no longer defines a CV protocol of its own.
- Confidence flags come from the MEAN per-indicator grouped R² across the
  repetitions, so they no longer flip with fold luck.
- Fits the selected model on ALL data; saves model + category encoders +
  metadata to artifacts/csa_model.joblib and artifacts/model_metrics.json.

Pipeline position:
  merged -> (build_practice_family) -> final -> (assign_folds) -> (this script)
  in   data/processed/CSA_ERA_final_model_ready.csv   (--dataset)
       data/processed/cv_folds.csv                    (--folds)
  out  model/artifacts/{csa_model.joblib, model_metrics.json, model_eval.json}
  and, with --copy-to (default app/backend/artifacts), the copies the API
  serves. See docs/reports/merged_dataset_notes.md.

Usage:
    python model/train_model.py                 # full protocol (~10 min)
    python model/train_model.py --quick         # 2 reps, 1 setting (smoke)
    python model/train_model.py --reuse-eval    # re-emit artefacts, no re-run
    python model/train_model.py --dataset X.csv --artifacts out/ --no-copy

Requires: pandas, numpy, scikit-learn, joblib.
"""
from __future__ import annotations

import argparse
import json
import logging
import shutil
import sys
from pathlib import Path
from typing import Any

import joblib
import pandas as pd

MODEL_DIR = Path(__file__).resolve().parent
REPO_ROOT = MODEL_DIR.parents[0]
if str(MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(MODEL_DIR))

import evaluate as ev  # noqa: E402  (the canonical protocol — wrap, never fork)

logger = logging.getLogger(__name__)

DATASET_PATH = ev.DATASET_PATH
FOLDS_PATH = ev.FOLDS_PATH
ARTIFACTS_DIR = REPO_ROOT / "model" / "artifacts"
BACKEND_ARTIFACTS = REPO_ROOT / "app" / "backend" / "artifacts"

# Re-exported so the names train_model.py has always owned keep working.
CAT, NUM, FEATURES = ev.CAT, ev.NUM, ev.FEATURES
TARGET, GROUP = ev.TARGET, ev.GROUP
build_cat_maps, encode = ev.build_cat_maps, ev.encode


def spec_from_label(payload: dict[str, Any], label: str) -> ev.ModelSpec:
    """Recover the winning model's spec from the evaluation payload."""
    for run in payload["runs"]:
        if run["label"] == label:
            return ev.ModelSpec(run["family"], dict(run["params"]))
    raise KeyError(f"no run labelled {label!r} in the evaluation payload")


def build_metrics(payload: dict[str, Any], best: dict[str, Any],
                  df: pd.DataFrame) -> dict[str, Any]:
    """``model_metrics.json`` — the long-standing keys plus the P7 additions.

    The existing keys keep their exact shapes (``per_indicator`` stays
    ``{indicator: [n, r2]}``) because ``app/backend/app/metadata_service.py``
    and the frontend read this file.
    """
    baseline = next(r for r in payload["runs"] if r["family"] == "Baseline")
    per_indicator = {
        indicator: [int(stats["n"]["mean"]), round(stats["r2"]["mean"], 3)]
        for indicator, stats in best["per_indicator"].items()
    }
    return {
        # --- unchanged contract -------------------------------------------
        "model": best["family"],
        "cv_r2": best["r2"]["mean"],
        "cv_rmse": best["rmse"]["mean"],
        "baseline_r2": baseline["r2"]["mean"],
        "per_indicator": per_indicator,
        "per_source": {s: round(v["r2"]["mean"], 3)
                       for s, v in best["per_source"].items()},
        "indicator_confidence": payload["indicator_confidence"],
        "n_rows": int(len(df)),
        "n_groups": int(df[GROUP].nunique()),
        "features": FEATURES,
        # --- P7 additions --------------------------------------------------
        "protocol": payload["protocol"],
        "cv_r2_sd": best["r2"]["sd"],
        "cv_rmse_sd": best["rmse"]["sd"],
        "baseline_r2_sd": baseline["r2"]["sd"],
        "fold_file": payload["fold_file"],
        "n_reps": payload["n_reps"],
        "n_folds": payload["n_folds"],
        "model_params": best["params"],
        "model_label": best["label"],
        "ranking_metrics": best["ranking"],
        "direction_metrics": best["direction"],
        "per_indicator_detail": best["per_indicator"],
        "noise_ceiling": payload["noise_ceiling"],
        "leakage_ablation_r2": (payload.get("leakage_ablation") or {})
        .get("r2", {}).get("mean"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("--dataset", type=Path, default=DATASET_PATH,
                        help="final model-ready csv to train on")
    parser.add_argument("--folds", type=Path, default=FOLDS_PATH,
                        help="deterministic fold file from assign_folds.py")
    parser.add_argument("--artifacts", type=Path, default=ARTIFACTS_DIR,
                        help="directory for csa_model.joblib + model_metrics.json")
    parser.add_argument("--copy-to", type=Path, default=BACKEND_ARTIFACTS,
                        help="also copy the artefacts here (the API's copies)")
    parser.add_argument("--no-copy", dest="copy", action="store_false",
                        help="skip the copy step")
    parser.add_argument("--quick", action="store_true",
                        help="2 repetitions, 1 setting — smoke run, NOT for release")
    parser.add_argument("--no-grid", dest="grid", action="store_false",
                        help="evaluate only the two default settings")
    parser.add_argument("--no-ablations", dest="ablations", action="store_false")
    parser.add_argument("--reuse-eval", action="store_true",
                        help="reuse an existing model_eval.json instead of "
                             "re-running the protocol")
    parser.add_argument("--report", type=Path,
                        default=REPO_ROOT / "docs" / "reports" / "model_evaluation_report.md",
                        help="markdown evaluation report to (re)generate")
    parser.add_argument("--no-report", dest="report", action="store_const", const=None)
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(levelname)s %(message)s")

    art: Path = args.artifacts
    art.mkdir(parents=True, exist_ok=True)
    eval_path = art / "model_eval.json"

    df = pd.read_csv(args.dataset)
    print(f"dataset: {args.dataset} {df.shape}", flush=True)

    if args.reuse_eval:
        if not eval_path.exists():
            parser.error(f"--reuse-eval but {eval_path} does not exist")
        payload = json.loads(eval_path.read_text(encoding="utf-8"))
        print(f"reusing {eval_path} ({payload['n_reps']} repetitions)", flush=True)
        # Flags follow the CURRENT rule in evaluate.confidence_flags, not the
        # rule in force when the payload was written; persist the refresh so
        # payload, report and artefact agree.
        best_run = next(r for r in payload["runs"] if r["label"] == payload["best"])
        refreshed = ev.confidence_flags(best_run["per_indicator"])
        if refreshed != payload.get("indicator_confidence"):
            print(f"confidence flags refreshed: {payload.get('indicator_confidence')} "
                  f"-> {refreshed}", flush=True)
            payload["indicator_confidence"] = refreshed
            eval_path.write_text(json.dumps(payload, indent=2, default=str) + "\n",
                                 encoding="utf-8")
    else:
        print("running the evaluation protocol "
              f"({'quick' if args.quick else 'full'}) …", flush=True)
        payload = ev.run_protocol(args.dataset, args.folds, grid=args.grid,
                                  ablations=args.ablations, quick=args.quick)
        eval_path.write_text(json.dumps(payload, indent=2, default=str) + "\n",
                             encoding="utf-8")
        print(f"wrote {eval_path}", flush=True)

    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(ev.format_report(payload), encoding="utf-8")
        print(f"wrote {args.report}", flush=True)

    best = next(r for r in payload["runs"] if r["label"] == payload["best"])
    baseline = next(r for r in payload["runs"] if r["family"] == "Baseline")

    print(f"\nprotocol: {payload['protocol']} "
          f"({payload['n_reps']} reps x {payload['n_folds']} folds)")
    print(f"baseline (practice x indicator mean): "
          f"R2 {baseline['r2']['mean']:.3f} +- {baseline['r2']['sd']:.3f}")
    for run in payload["runs"]:
        if run["family"] == "Baseline":
            continue
        mark = "  <- selected" if run["label"] == payload["best"] else ""
        print(f"  {run['label']:<52} R2 {run['r2']['mean']:.3f} "
              f"+- {run['r2']['sd']:.3f}{mark}")
    print(f"\nBEST: {payload['best']}")
    print(f"ranking: rho {best['ranking']['spearman_mean']['mean']:.2f}, "
          f"top-1 {best['ranking']['top1_hit_rate']['mean']:.0%} "
          f"(chance {best['ranking']['top1_chance']['mean']:.0%}), "
          f"C-index {best['ranking']['c_index']['mean']:.2f}")

    # ---- fit the selected model on ALL data and write the artefacts
    cmaps = build_cat_maps(df)
    X = encode(df, cmaps)
    y = df[TARGET].to_numpy(dtype=float)
    cat_mask = [c in CAT for c in FEATURES]
    spec = spec_from_label(payload, payload["best"])
    final = ev.make_model(spec, cat_mask)
    final.fit(X, y)

    joblib.dump({"model": final, "cat_maps": cmaps, "features": FEATURES,
                 "cat": CAT, "num": NUM, "cat_mask": cat_mask, "target": TARGET,
                 "model_name": spec.family,
                 "indicator_confidence": payload["indicator_confidence"]},
                art / "csa_model.joblib")
    metrics = build_metrics(payload, best, df)
    (art / "model_metrics.json").write_text(
        json.dumps(metrics, indent=2, default=str) + "\n", encoding="utf-8")
    print(f"\nsaved {art/'csa_model.joblib'} + {art/'model_metrics.json'}")
    print("indicator confidence:", payload["indicator_confidence"])

    if args.copy and args.copy_to.resolve() != art.resolve():
        args.copy_to.mkdir(parents=True, exist_ok=True)
        # Only what the API actually loads: recommend.py reads csa_model.joblib
        # and metadata_service.py reads model_metrics.json. model_eval.json is
        # the full evidence behind the report and stays in model/artifacts/.
        for name in ("csa_model.joblib", "model_metrics.json"):
            shutil.copyfile(art / name, args.copy_to / name)
        print("copied artefacts to", args.copy_to)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
