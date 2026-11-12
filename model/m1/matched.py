"""Context-matched studies of Methodology 1 v2 (E5 Part 2.3).

The E4 ``nearest_studies`` baseline improved: the training sites are the pooled items
(one effect per cell and practice, :func:`model.m1.data.pooled_items`) with a context
vector over the release layers; for a candidate the ``k`` nearest sites that report it
for the same outcome (fallback: the same objective group) are pooled by a random-effects
model (DerSimonian and Laird 1986): the between-site variance ``tau^2`` is estimated from
the inverse-variance weighted sum of squares, every site's weight is ``1 / (v_i + tau^2)``
times the distance decay ``1 / (1 + d_i^2)``, and the pooled standard error
``sqrt(1 / sum w)`` gives the 80 % interval. ``k`` and the decay exponent are tuned on the
inner folds by the pooled C-index over the training queries; the component abstains below
``k_min`` distinct groups (default 3).

Besides the estimate it reports the **spread** of the matched effects and the distance to
the nearest site, which the conformal step uses as its difficulty score.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from model.engines.base import Z80
from model.engines.nearest_studies import CONTEXT_LAYERS, context_vector
from model.m1 import inner

K_GRID = (5, 10, 20)
POWER_GRID = (1.0, 2.0)


@dataclass
class MatchedEstimate:
    est: float
    lo: float
    hi: float
    se: float
    n_sites: int
    n_groups: int
    spread: float
    d_nearest: float
    tau2: float
    study_ids: list[str]


def dersimonian_laird(y: np.ndarray, v: np.ndarray, decay: np.ndarray) -> tuple[float, float, float]:
    """``(estimate, se, tau2)`` of the random-effects pooled mean with distance-decayed weights."""
    y, v = np.asarray(y, float), np.asarray(v, float)
    w = 1.0 / v
    ybar = float(np.sum(w * y) / np.sum(w))
    q = float(np.sum(w * (y - ybar) ** 2))
    c = float(np.sum(w) - np.sum(w ** 2) / np.sum(w))
    tau2 = max(0.0, (q - (len(y) - 1)) / c) if c > 0 and len(y) > 1 else 0.0
    w_re = decay / (v + tau2)
    est = float(np.sum(w_re * y) / np.sum(w_re))
    se = float(math.sqrt(1.0 / np.sum(w_re)))
    return est, se, tau2


class MatchedStudies:
    name = "matched_studies"

    def __init__(self, k: int = 10, power: float = 2.0, k_min: int = 3) -> None:
        self.k, self.power, self.k_min = int(k), float(power), int(k_min)
        self.sites = pd.DataFrame()
        self.vectors = np.zeros((0, len(CONTEXT_LAYERS)))
        self.mu = np.zeros(len(CONTEXT_LAYERS))
        self.sd = np.ones(len(CONTEXT_LAYERS))
        self.default_var = 1.0
        self._z = self.vectors

    # ------------------------------------------------------------ fit
    def fit(self, rows: pd.DataFrame, items: pd.DataFrame) -> "MatchedStudies":
        """``rows``: training rows (for the context of each item's first row); ``items``: pooled items."""
        self.sites = items.reset_index(drop=True)
        vecs = []
        for ri in self.sites["row_index"]:
            r = rows.loc[ri]
            ctx = {f"ctx_{lid}": (None if pd.isna(r.get(f"ctx_{lid}")) else float(r.get(f"ctx_{lid}"))) for lid in CONTEXT_LAYERS if f"ctx_{lid}" in rows.columns}
            for col, feat in (("ctx_reported_rain_mm", "Rainfall"), ("ctx_reported_altitude_m", "Altitude_r"), ("ctx_reported_slope_pct", "slope")):
                if col in rows.columns and pd.notna(r.get(col)):
                    ctx[feat] = float(r[col])
            vecs.append(context_vector(ctx))
        self.vectors = np.vstack(vecs) if vecs else np.zeros((0, len(CONTEXT_LAYERS)))
        if len(self.vectors):
            with np.errstate(invalid="ignore"):
                mu, sd = np.nanmean(self.vectors, axis=0), np.nanstd(self.vectors, axis=0)
            self.mu = np.where(np.isfinite(mu), mu, 0.0)
            self.sd = np.where(np.isfinite(sd) & (sd > 0), sd, 1.0)
            v = self.sites["var"].to_numpy(float)
            self.default_var = float(np.nanmedian(v)) if np.isfinite(v).any() else 1.0
        self._z = (self.vectors - self.mu) / self.sd
        return self

    def _distances(self, ctx: dict[str, Any], idx: np.ndarray) -> np.ndarray:
        q = (context_vector(ctx) - self.mu) / self.sd
        diff = self._z[idx] - q[None, :]
        ok = np.isfinite(diff)
        n_ok = ok.sum(axis=1)
        with np.errstate(invalid="ignore", divide="ignore"):
            d = np.sqrt(np.where(ok, diff ** 2, 0.0).sum(axis=1) / np.maximum(n_ok, 1))
        d[n_ok == 0] = np.inf
        return d

    def _candidates(self, practice_id: str, outcome_id: str, group: str, exclude_qkey: str | None) -> np.ndarray:
        s = self.sites
        if s.empty:
            return np.array([], int)
        base = (s["practice_id"] == practice_id).to_numpy()
        if exclude_qkey is not None:
            base &= (s["qkey"] != exclude_qkey).to_numpy()
        same = np.flatnonzero(base & (s["outcome_id"] == outcome_id).to_numpy())
        if len(same) >= self.k_min:
            return same
        return np.flatnonzero(base & (s["objective_group"] == group).to_numpy())

    # ------------------------------------------------------------ estimate
    def estimate(self, ctx: dict[str, Any], practice_id: str, outcome_id: str, group: str,
                 k: int | None = None, power: float | None = None, exclude_qkey: str | None = None) -> MatchedEstimate | None:
        """Pooled effect from the nearest sites, or ``None`` (abstain) below ``k_min`` groups."""
        k = self.k if k is None else int(k)
        power = self.power if power is None else float(power)
        cand = self._candidates(practice_id, outcome_id, group, exclude_qkey)
        if len(cand) == 0:
            return None
        d = self._distances(ctx, cand)
        order = np.argsort(d, kind="stable")[:k]
        sel, d_sel = cand[order], d[order]
        finite = np.isfinite(d_sel)
        sel, d_sel = sel[finite], d_sel[finite]
        groups = self.sites["group"].to_numpy()[sel]
        if len(set(groups)) < self.k_min:
            return None
        y = self.sites["y"].to_numpy(float)[sel]
        var = self.sites["var"].to_numpy(float)[sel]
        v = np.where(np.isfinite(var) & (var > 0), var, self.default_var)
        est, se, tau2 = dersimonian_laird(y, v, 1.0 / (1.0 + d_sel ** power))
        half = Z80 * se
        return MatchedEstimate(est, est - half, est + half, se, int(len(sel)), int(len(set(groups))),
                               float(np.std(y)) if len(y) > 1 else 0.0, float(d_sel.min()), tau2,
                               sorted(set(self.sites["study_id"].to_numpy()[sel])))

    # ------------------------------------------------------------ tuning
    def tune(self, rows: pd.DataFrame, items: pd.DataFrame, fold_of_item: np.ndarray,
             k_grid: tuple[int, ...] = K_GRID, power_grid: tuple[float, ...] = POWER_GRID) -> tuple[int, float, list[dict[str, Any]]]:
        """``(k, power)`` with the best mean inner pooled C-index; each inner fold's items are
        estimated from the sites of the other folds (a fresh instance per fold)."""
        table = []
        best: tuple[tuple[int, float], dict[str, float]] | None = None
        folds = np.unique(fold_of_item)
        fitted = {}
        for f in folds:
            m = MatchedStudies(self.k, self.power, self.k_min).fit(rows, items[fold_of_item != f])
            fitted[f] = m
        ctx_of = {}
        for ri in items["row_index"].unique():
            r = rows.loc[ri]
            ctx_of[ri] = {f"ctx_{lid}": (None if pd.isna(r.get(f"ctx_{lid}")) else float(r.get(f"ctx_{lid}"))) for lid in CONTEXT_LAYERS if f"ctx_{lid}" in rows.columns}
        for k in k_grid:
            for power in power_grid:
                scores = []
                for f in folds:
                    sel = items[fold_of_item == f]
                    m = fitted[f]
                    pred = np.array([
                        (e.est if (e := m.estimate(ctx_of[it.row_index], it.practice_id, it.outcome_id, it.objective_group, k, power)) else np.nan)
                        for it in sel.itertuples()
                    ])
                    ok = np.isfinite(pred)
                    if ok.sum() < 2:
                        continue
                    scores.append(inner.score_items(sel[ok], pred[ok]))
                mean = {key: float(np.nanmean([s[key] for s in scores])) if scores else float("nan") for key in ("c_pooled", "top1", "n_queries")}
                table.append({"k": k, "power": power, **mean})
                if best is None or inner.better(mean, best[1]):
                    best = ((k, power), mean)
        if best is not None:
            self.k, self.power = best[0]
        return self.k, self.power, table
