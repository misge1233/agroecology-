"""The within-study ranker of Methodology 1 v2 (E5 Part 2.2).

Learns which practice is better at the same site from the training queries (pooled items
of cells with at least two practices). Primary: LightGBM ``LGBMRanker`` (lambdarank) with
the query cells as groups and graded relevance = the rank of the observed oriented
effect within the cell (0 = worst, capped at 30 levels). Fallback when LightGBM is not
importable: a symmetric pairwise classifier (``HistGradientBoostingClassifier`` on
``[x_i - x_j, context]`` with both orders of every pair, label ``y_i > y_j``, pairs with
``|y_i - y_j| < 0.02`` dropped); its score for a candidate is the mean predicted
probability of beating the other candidates of the query.

Features are the encoder's matrix (no site identifiers exist in it: coordinates, site
names and study ids never enter), so the ranker cannot memorise sites. The study effect
cancels by construction because every pair compares practices of one cell.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

MIN_PAIR_GAP = 0.02
MAX_RELEVANCE = 30


def lightgbm_available() -> bool:
    try:
        import lightgbm  # noqa: F401
    except Exception:  # noqa: BLE001
        return False
    return True


def relevance(items: pd.DataFrame) -> np.ndarray:
    """Integer relevance per item: the rank of ``y`` within its ``qkey`` (0 = worst)."""
    rel = np.zeros(len(items), dtype=int)
    for _, idx in items.groupby("qkey").indices.items():
        order = np.argsort(items["y"].to_numpy(float)[idx], kind="stable")
        ranks = np.empty(len(idx), dtype=int)
        ranks[order] = np.arange(len(idx))
        rel[idx] = np.minimum(ranks, MAX_RELEVANCE)
    return rel


class LambdaRanker:
    name = "ranker:lambdarank"

    def __init__(self, params: dict[str, Any] | None = None) -> None:
        self.params = {"n_estimators": 200, "learning_rate": 0.05, "num_leaves": 15, "min_child_samples": 10,
                       "subsample": 0.9, "subsample_freq": 1, "colsample_bytree": 0.8, "random_state": 0, "verbose": -1,
                       **(params or {})}
        self.model: Any = None
        self.n_queries = 0
        self.n_items = 0

    def fit(self, X: pd.DataFrame, items: pd.DataFrame) -> "LambdaRanker":
        from lightgbm import LGBMRanker

        keep = items.groupby("qkey")["practice_id"].transform("size") >= 2
        it = items[keep].sort_values("qkey", kind="stable")
        self.n_queries, self.n_items = int(it["qkey"].nunique()), int(len(it))
        if self.n_queries == 0:
            self.model = None
            return self
        groups = it.groupby("qkey", sort=False).size().to_numpy()
        self.model = LGBMRanker(label_gain=list(range(MAX_RELEVANCE + 1)), **self.params)
        self.model.fit(X.loc[it["row_index"]].to_numpy(float), relevance(it), group=groups)
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        if self.model is None:
            return np.zeros(len(X))
        return self.model.predict(X.to_numpy(float))


class PairwiseRanker:
    name = "ranker:pairwise"

    def __init__(self, params: dict[str, Any] | None = None) -> None:
        self.params = {"learning_rate": 0.1, "max_iter": 200, "min_samples_leaf": 20, "random_state": 0, **(params or {})}
        self.model: Any = None
        self.n_queries = 0
        self.n_items = 0
        self.n_pairs = 0

    def fit(self, X: pd.DataFrame, items: pd.DataFrame) -> "PairwiseRanker":
        from sklearn.ensemble import HistGradientBoostingClassifier

        rows, labels = [], []
        M = X.loc[items["row_index"]].to_numpy(float)
        y = items["y"].to_numpy(float)
        nq = 0
        for _, idx in items.groupby("qkey").indices.items():
            if len(idx) < 2:
                continue
            nq += 1
            for a in idx:
                for b in idx:
                    if a < b and abs(y[a] - y[b]) >= MIN_PAIR_GAP:
                        rows.append(np.concatenate([M[a] - M[b], M[a]]))
                        labels.append(int(y[a] > y[b]))
                        rows.append(np.concatenate([M[b] - M[a], M[b]]))
                        labels.append(int(y[b] > y[a]))
        self.n_queries, self.n_items, self.n_pairs = nq, int(len(items)), len(rows) // 2
        if not rows:
            self.model = None
            return self
        self.model = HistGradientBoostingClassifier(**self.params).fit(np.vstack(rows), np.array(labels))
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        """Mean probability of beating each other candidate of the same query (rows = one query)."""
        if self.model is None or len(X) < 2:
            return np.zeros(len(X))
        M = X.to_numpy(float)
        out = np.zeros(len(M))
        for i in range(len(M)):
            others = [j for j in range(len(M)) if j != i]
            feats = np.vstack([np.concatenate([M[i] - M[j], M[i]]) for j in others])
            out[i] = float(self.model.predict_proba(feats)[:, 1].mean())
        return out


def make_ranker(params: dict[str, Any] | None = None, prefer_lightgbm: bool = True) -> LambdaRanker | PairwiseRanker:
    if prefer_lightgbm and lightgbm_available():
        return LambdaRanker(params)
    return PairwiseRanker(params)
