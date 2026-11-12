"""Inner-fold ranking score shared by the tuning, selection and stacking steps (E5).

Every learned choice of Methodology 1 v2 is scored on the *training queries* of the inner
folds (the pooled items of :func:`model.m1.data.pooled_items`) with the pair-pooled C-index
and the top-1 hit rate over cells with at least two practices; never with RMSE, and never
on the outer fold.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from model import metrics as mm


def score_items(items: pd.DataFrame, pred: np.ndarray) -> dict[str, float]:
    """``c_pooled``, ``top1`` and ``n_queries`` of predictions over the pooled items."""
    conc = comp = 0.0
    hits = []
    frame = items[["qkey", "y"]].copy()
    frame["p"] = np.asarray(pred, float)
    for _, g in frame.groupby("qkey", sort=True):
        if len(g) < 2:
            continue
        y, p = g["y"].to_numpy(float), g["p"].to_numpy(float)
        c, m = mm.concordance(y, p)
        conc += c
        comp += m
        hits.append(mm.top1_hit(y, p))
    return {"c_pooled": conc / comp if comp else float("nan"), "top1": float(np.mean(hits)) if hits else float("nan"),
            "n_queries": float(len(hits))}


def better(a: dict[str, float], b: dict[str, float] | None) -> bool:
    """``a`` beats ``b`` on the pooled C-index (ties by top-1; a nan never wins)."""
    if b is None:
        return bool(np.isfinite(a["c_pooled"]))
    if not np.isfinite(a["c_pooled"]):
        return False
    if not np.isfinite(b["c_pooled"]):
        return True
    return (a["c_pooled"], a["top1"]) > (b["c_pooled"], b["top1"])
