"""Calibrated 80 % intervals by normalised split conformal prediction (E5 Part 2.6).

On the inner out-of-fold predictions of the training queries the residuals of the effect
estimate are divided by a **difficulty score** ``d = floor + spread + b x distance``:
the spread of the matched studies' effects around the candidate (the within-cell sd of
the prior when no matched studies exist) and the standardised distance to the nearest
training site. The 80 % quantile ``q`` of the normalised residuals (the finite-sample
``ceil((n + 1) x 0.8) / n`` quantile) is learned inside the outer training fold and
applied to the outer fold as ``est +- q x d``. Target (brief): held-out coverage between
0.75 and 0.85, width reported.

**E5.1 (pre-registered 12 Nov 2026, post-hoc).** With ``by_group=True`` the quantile is
taken per objective group (Mondrian conformal) when the group has at least ``min_group``
(30) inner residuals, else the pooled quantile is used. The E5 default is unchanged.
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np

FLOOR = 0.05
DIST_WEIGHT = 0.5
LEVEL = 0.8
MIN_GROUP = 30


def difficulty(spread: float | None, d_nearest: float | None, fallback_spread: float,
               floor: float = FLOOR, b: float = DIST_WEIGHT) -> float:
    s = float(spread) if spread is not None and np.isfinite(spread) else float(fallback_spread)
    d = float(d_nearest) if d_nearest is not None and np.isfinite(d_nearest) else 1.0
    return floor + s + b * d


def _quantile(r: np.ndarray, level: float) -> float:
    """The finite-sample conformal quantile of the normalised residuals ``r``."""
    n = int(r.size)
    if n == 0:
        return float("nan")
    k = min(n, int(math.ceil((n + 1) * level)))
    return float(np.sort(r)[k - 1])


class ConformalCalibrator:
    def __init__(self, level: float = LEVEL, by_group: bool = False, min_group: int = MIN_GROUP) -> None:
        self.level = float(level)
        self.q = float("nan")
        self.n = 0
        self.fallback_spread = 0.3
        self.by_group = bool(by_group)
        self.min_group = int(min_group)
        self.q_group: dict[str, float] = {}
        self.n_group: dict[str, int] = {}

    def fit(self, residuals: np.ndarray, difficulties: np.ndarray, groups: Any = None) -> "ConformalCalibrator":
        r = np.abs(np.asarray(residuals, float)) / np.maximum(np.asarray(difficulties, float), 1e-6)
        ok = np.isfinite(r)
        self.n = int(ok.sum())
        self.q = _quantile(r[ok], self.level)
        self.q_group, self.n_group = {}, {}
        if self.by_group and groups is not None:
            g = np.asarray([str(x) for x in groups], dtype=object)
            for name in sorted(set(g[ok])):
                sel = ok & (g == name)
                self.n_group[name] = int(sel.sum())
                if self.n_group[name] >= self.min_group:
                    self.q_group[name] = _quantile(r[sel], self.level)
        return self

    def quantile_for(self, group: str | None = None) -> float:
        """The group's quantile under Mondrian conformal, else the pooled one."""
        # getattr: artifacts pickled before E5.1 have neither attribute (pooled quantile, as fitted)
        q_group = getattr(self, "q_group", {}) if getattr(self, "by_group", False) else {}
        if group is not None and str(group) in q_group:
            return q_group[str(group)]
        return self.q

    def interval(self, est: float, d: float, group: str | None = None) -> tuple[float, float]:
        q = self.quantile_for(group)
        if not np.isfinite(q):
            return float("nan"), float("nan")
        half = q * max(float(d), 1e-6)
        return est - half, est + half

    def summary(self) -> dict[str, Any]:
        out: dict[str, Any] = {"level": self.level, "q": self.q, "n_calibration": self.n, "floor": FLOOR,
                               "distance_weight": DIST_WEIGHT, "fallback_spread": self.fallback_spread}
        if getattr(self, "by_group", False):
            out.update({"by_group": True, "min_group": self.min_group, "q_by_group": dict(self.q_group),
                        "n_by_group": dict(self.n_group)})
        return out
