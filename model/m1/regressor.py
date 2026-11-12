"""The effect regressor of Methodology 1 v2 (E5 Part 2.1).

Gradient boosting on the oriented effect ``y`` with the features of :mod:`model.m1.data`
(sklearn ``HistGradientBoostingRegressor``; categorical columns declared, missing values
handled natively; sample weights from the chosen weight scheme). The hyperparameters come
from a small grid scored on the **inner** folds by the pooled C-index over the training
queries (:mod:`model.m1.inner`), never by RMSE and never on the outer fold.

LightGBM was installed and tested (4.6.0 with numpy 2.4.6) and is used for the ranker;
the regressor stays on sklearn as the brief's default, so the artifact has one fewer
binary dependency.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

from model.m1 import inner

GRID: tuple[dict[str, Any], ...] = (
    {"learning_rate": 0.05, "max_iter": 300, "min_samples_leaf": 20},
    {"learning_rate": 0.1, "max_iter": 300, "min_samples_leaf": 20},
    {"learning_rate": 0.05, "max_iter": 300, "min_samples_leaf": 50},
    {"learning_rate": 0.1, "max_iter": 150, "min_samples_leaf": 50},
)
DEFAULT_PARAMS = GRID[0]


class Regressor:
    name = "regressor"

    def __init__(self, params: dict[str, Any] | None = None, categorical_index: list[int] | None = None) -> None:
        self.params = dict(params or DEFAULT_PARAMS)
        self.categorical_index = list(categorical_index or [])
        self.model: HistGradientBoostingRegressor | None = None

    def fit(self, X: pd.DataFrame, y: np.ndarray, w: np.ndarray | None = None) -> "Regressor":
        cat = [i for i in self.categorical_index if i < X.shape[1]] or None
        self.model = HistGradientBoostingRegressor(categorical_features=cat, l2_regularization=1.0, random_state=0,
                                                   **self.params)
        self.model.fit(X.to_numpy(float), np.asarray(y, float), sample_weight=w)
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        assert self.model is not None, "fit first"
        return self.model.predict(X.to_numpy(float))


def tune(X: pd.DataFrame, y: np.ndarray, w: np.ndarray, items: pd.DataFrame, fold_of_row: np.ndarray,
         categorical_index: list[int], grid: tuple[dict[str, Any], ...] = GRID) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Best grid setting by the mean inner pooled C-index over the training queries.

    ``items`` are the pooled items (``row_index`` into ``X``); an inner fold's items are
    scored by a model fitted on the rows of the other inner folds. Ties keep the first
    setting of the grid (deterministic).
    """
    folds = np.unique(fold_of_row)
    item_fold = fold_of_row[X.index.get_indexer(items["row_index"])]
    table = []
    best: tuple[dict[str, Any], dict[str, float]] | None = None
    for params in grid:
        scores = []
        for f in folds:
            train = fold_of_row != f
            reg = Regressor(params, categorical_index).fit(X[train], y[train], w[train])
            sel = items[item_fold == f]
            if sel.empty:
                continue
            pred = reg.predict(X.loc[sel["row_index"]])
            scores.append(inner.score_items(sel, pred))
        mean = {k: float(np.nanmean([s[k] for s in scores])) if scores else float("nan") for k in ("c_pooled", "top1", "n_queries")}
        table.append({"params": dict(params), **mean})
        if best is None or inner.better(mean, best[1]):
            best = (dict(params), mean)
    return (best[0] if best else dict(DEFAULT_PARAMS)), table
