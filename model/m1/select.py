"""Grouped permutation feature selection on the inner folds (E5 Part 1).

For each inner fold the regressor is fitted on the other folds and scored on the fold's
training queries (pooled C-index, :mod:`model.m1.inner`); then every feature **group**
(one per context layer; one block each for the components, the practice target encoding
and each categorical) is permuted in the scored rows (seeded) and the score recomputed.
A group whose permutation does not lower the mean inner score (``delta <= 0``) does not
improve the inner ranking and is dropped; groups are examined in sorted name order so
the outcome is deterministic. The kept set is reported per outer fold; the serving
artifact uses a feature only when it survives in at least 4 of 5 outer folds.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from model.m1 import inner
from model.m1.regressor import Regressor


def select_features(encoder: Any, X: pd.DataFrame, y: np.ndarray, w: np.ndarray, items: pd.DataFrame,
                    fold_of_row: np.ndarray, params: dict[str, Any], seed: int = 0,
                    always_keep: tuple[str, ...] = ("cat_outcome_id", "cat_objective_group")) -> tuple[list[str], list[dict[str, Any]]]:
    """``(kept feature names, table of per-group deltas)``."""
    groups: dict[str, list[str]] = {}
    for name in X.columns:
        groups.setdefault(encoder.feature_group(name), []).append(name)
    folds = np.unique(fold_of_row)
    item_fold = fold_of_row[X.index.get_indexer(items["row_index"])]
    cat_idx = [i for i, n in enumerate(X.columns) if n.startswith("cat_")]
    deltas: dict[str, list[float]] = {g: [] for g in groups}
    rng = np.random.default_rng(seed)
    for f in folds:
        train = fold_of_row != f
        sel = items[item_fold == f]
        if sel.empty:
            continue
        reg = Regressor(params, cat_idx).fit(X[train], y[train], w[train])
        Xs = X.loc[sel["row_index"]]
        base = inner.score_items(sel, reg.predict(Xs))["c_pooled"]
        for g in sorted(groups):
            Xp = Xs.copy()
            perm = rng.permutation(len(Xp))
            Xp[groups[g]] = Xp[groups[g]].to_numpy()[perm]
            deltas[g].append(base - inner.score_items(sel, reg.predict(Xp))["c_pooled"])
    table = [{"group": g, "delta_mean": float(np.nanmean(d)) if d else float("nan"), "n_folds": len(d),
              "columns": len(groups[g])} for g, d in sorted(deltas.items())]
    kept: list[str] = []
    for row in table:
        g = row["group"]
        if g in always_keep or (np.isfinite(row["delta_mean"]) and row["delta_mean"] > 0):
            kept.extend(groups[g])
            row["kept"] = True
        else:
            row["kept"] = False
    return [n for n in X.columns if n in set(kept)], table


def stable_features(per_fold: list[list[str]], min_folds: int = 4) -> list[str]:
    """Features kept in at least ``min_folds`` of the outer folds (serving rule)."""
    counts: dict[str, int] = {}
    for kept in per_fold:
        for n in kept:
            counts[n] = counts.get(n, 0) + 1
    return sorted(n for n, c in counts.items() if c >= min_folds)
