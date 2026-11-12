"""Feature stability across outer folds (E5 Part 1).

Runs only the inner tuning and grouped permutation selection of :class:`model.m1.engine.M1Engine`
on the training side of each outer fold of one repetition of a harness split (default:
repetition 0 of the spatial split, 5 folds) and writes the kept groups per fold and the
**stable set** (kept in at least 4 of 5 folds) to ``model/artifacts/m1_v2/feature_stability.json``.
``model/m1/train.py`` serves exactly the stable set.

Usage::

    python -m model.m1.stability [--split spatial] [--rep 0]
"""
from __future__ import annotations

import argparse
import json

from model.harness import folds as hf
from model.harness import queries as hq
from model.harness import run as hr
from model.m1 import ARTIFACT_DIR
from model.m1 import data as md
from model.m1 import regressor as rg
from model.m1 import select as fs
from model.m1.engine import M1Config
from model.m1.train import engine_maps


def kept_for_fold(store, mask, cfg: M1Config, maps) -> tuple[list[str], dict, list[dict]]:
    rows = md.training_rows(store, mask, cfg.data, maps["outcome_group"])
    fold = md.inner_folds(rows["group"], cfg.inner_folds)
    enc = md.FeatureEncoder(cfg.data, maps["outcome_group"], maps["family_of"], maps["components_of"], maps["belt_code_of"]).fit(rows)
    X = enc.transform_rows(rows, oof_folds=fold)
    y, w = rows["y"].to_numpy(float), md.row_weights(rows, cfg.data.weight_scheme)
    items = md.pooled_items(rows)
    params, _ = rg.tune(X, y, w, items, fold, enc.categorical_index)
    kept, table = fs.select_features(enc, X, y, w, items, fold, params)
    return kept, params, table


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Per-outer-fold feature selection and the stable set")
    ap.add_argument("--split", default="spatial")
    ap.add_argument("--rep", type=int, default=0)
    ap.add_argument("--min-folds", type=int, default=4)
    a = ap.parse_args(argv)
    store, tax = hr.load_store(hr.REPO_ROOT / "data" / "evidence"), hr.load_taxonomy()
    maps = engine_maps(tax)
    queries, _ = hq.load_queries()
    plan = [p for p in hr.fold_plan(a.split, hr.select_queries(queries, "ET"), hr.HARNESS_DIR, a.rep + 1, store) if p[0] == a.rep]
    cfg = M1Config()
    per_fold, out_folds = [], []
    for rep, fold, held, mask in plan:
        kept, params, table = kept_for_fold(store, mask, cfg, maps)
        per_fold.append(kept)
        dropped = [r["group"] for r in table if not r["kept"]]
        out_folds.append({"rep": rep, "fold": fold, "n_kept": len(kept), "dropped_groups": dropped, "regressor_params": params})
        print(f"fold {fold}: kept {len(kept)} columns; dropped groups {dropped}", flush=True)
    stable = fs.stable_features(per_fold, a.min_folds)
    every = sorted(set(c for k in per_fold for c in k))
    unstable = [c for c in every if c not in stable]
    payload = {"split": a.split, "rep": a.rep, "min_folds": a.min_folds, "folds": out_folds, "stable": stable,
               "kept_somewhere_but_unstable": unstable,
               "counts": {c: int(sum(c in k for k in per_fold)) for c in every}}
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    (ARTIFACT_DIR / "feature_stability.json").write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
    print(f"stable features: {len(stable)} of {len(every)} ever kept; unstable: {unstable}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
