"""Release switch check with the full P7 protocol (E4 Part 6, E3 carry-over).

The canonical model specification (the P7 winner in ``model_metrics.json``) is run
through ``evaluate.evaluate_spec`` on the deterministic grouped folds of
``data/processed/cv_folds.csv`` (10 repetitions x 5 folds) twice: on the frozen
dataset as it is (the legacy raster stack) and on the same rows with every context
feature re-read from a geodata release (``train_model.reextract_from_release``, i.e.
``pipelines.geodata.extract.ContextExtractor`` with the serving rule). The backend
switch to ``GEODATA_RELEASE=<release>`` is recommended only when every ranking metric
(top-1 hit, top-half hit, C-index, mean and median Spearman) moves by less than one sd
of the current stack's repetition spread; otherwise the report names the features that
moved and why (the release's elevation and slope come from re-issued GLO-30 tiles).

Usage::

    python -m model.harness.release_check --release ET/2026.1 [--n-reps 10] [--out model/artifacts/release_check]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

import evaluate as ev  # model/evaluate.py
import train_model as tm  # model/train_model.py
from model.harness import REPO_ROOT

RANKING_KEYS = ("top1_hit_rate", "tophalf_hit_rate", "c_index", "spearman_mean", "spearman_median")
DEFAULT_OUT = REPO_ROOT / "model" / "artifacts" / "release_check"


def protocol_for(df: pd.DataFrame, folds: dict[str, list[int]], spec: ev.ModelSpec, n_reps: int) -> dict[str, Any]:
    cmaps = ev.build_cat_maps(df)
    X = ev.encode(df, cmaps)
    y = df[ev.TARGET].to_numpy(dtype=float)
    cat_mask = [c in ev.CAT for c in ev.FEATURES]
    return ev.evaluate_spec(df, X, y, folds, spec, cat_mask, n_reps).summary()


def compare(current: dict[str, Any], release: dict[str, Any]) -> dict[str, Any]:
    rows = {}
    ok = True
    for k in RANKING_KEYS:
        c, r = current["ranking"][k], release["ranking"][k]
        delta = r["mean"] - c["mean"]
        within = abs(delta) < c["sd"] if c["sd"] > 0 else delta == 0
        ok &= bool(within)
        rows[k] = {"current": c["mean"], "current_sd": c["sd"], "release": r["mean"], "release_sd": r["sd"],
                   "delta": delta, "within_one_sd": bool(within)}
    rows["r2"] = {"current": current["r2"]["mean"], "current_sd": current["r2"]["sd"], "release": release["r2"]["mean"],
                  "release_sd": release["r2"]["sd"], "delta": release["r2"]["mean"] - current["r2"]["mean"],
                  "within_one_sd": bool(abs(release["r2"]["mean"] - current["r2"]["mean"]) < current["r2"]["sd"])}
    return {"metrics": rows, "recommend_switch": bool(ok)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Full-protocol release switch check")
    ap.add_argument("--release", default="ET/2026.1")
    ap.add_argument("--n-reps", type=int, default=10)
    ap.add_argument("--dataset", type=Path, default=ev.DATASET_PATH)
    ap.add_argument("--folds", type=Path, default=ev.FOLDS_PATH)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    a = ap.parse_args(argv)
    from assign_folds import load_folds

    from model.engines.m0_current import canonical_spec

    spec = canonical_spec()
    df = pd.read_csv(a.dataset)
    folds = load_folds(a.folds)
    df_rel, changes = tm.reextract_from_release(df, a.release)
    print(f"spec {spec.label}; {a.n_reps} x 5 grouped folds; release {changes['release']}", flush=True)
    for col, c in changes["columns"].items():
        print(f"  {col:20s} " + ", ".join(f"{k} {v:.3g}" if isinstance(v, float) else f"{k} {v}" for k, v in c.items()))
    current = protocol_for(df, folds, spec, a.n_reps)
    release = protocol_for(df_rel, folds, spec, a.n_reps)
    result = compare(current, release)
    print(f"\n  {'metric':18s} {'current':>9s} {'sd':>7s} {'release':>9s} {'sd':>7s} {'delta':>8s}  within 1 sd")
    for k, r in result["metrics"].items():
        print(f"  {k:18s} {r['current']:9.4f} {r['current_sd']:7.4f} {r['release']:9.4f} {r['release_sd']:7.4f} "
              f"{r['delta']:+8.4f}  {'yes' if r['within_one_sd'] else 'NO'}")
    print(f"\nrecommend switching GEODATA_RELEASE to {a.release}: {'YES' if result['recommend_switch'] else 'NO'}")
    a.out.mkdir(parents=True, exist_ok=True)
    payload = {"release": a.release, "spec": spec.label, "n_reps": a.n_reps, "protocol": ev.PROTOCOL_NAME,
               "changes": changes, "current": current, "release_run": release, **result}
    path = a.out / f"full_protocol_release_check_{a.release.replace('/', '_')}.json"
    path.write_text(json.dumps(payload, indent=1, default=str) + "\n", encoding="utf-8")
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
