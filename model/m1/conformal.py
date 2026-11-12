"""Calibrated 80 % intervals by normalised split conformal prediction (E5 Part 2.6).

On the inner out-of-fold predictions of the training queries the residuals of the effect
estimate are divided by a **difficulty score** ``d = floor + spread + b x distance``:
the spread of the matched studies' effects around the candidate (the within-cell sd of
the prior when no matched studies exist) and the standardised distance to the nearest
training site. The 80 % quantile ``q`` of the normalised residuals (the finite-sample
``ceil((n + 1) x 0.8) / n`` quantile) is learned inside the outer training fold and
applied to the outer fold as ``est +- q x d``. Target (brief): held-out coverage between
0.75 and 0.85, width reported.
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np

FLOOR = 0.05
DIST_WEIGHT = 0.5
LEVEL = 0.8


def difficulty(spread: float | None, d_nearest: float | None, fallback_spread: float,
               floor: float = FLOOR, b: float = DIST_WEIGHT) -> float:
    s = float(spread) if spread is not None and np.isfinite(spread) else float(fallback_spread)
    d = float(d_nearest) if d_nearest is not None and np.isfinite(d_nearest) else 1.0
    return floor + s + b * d


class ConformalCalibrator:
    def __init__(self, level: float = LEVEL) -> None:
        self.level = float(level)
        self.q = float("nan")
        self.n = 0
        self.fallback_spread = 0.3

    def fit(self, residuals: np.ndarray, difficulties: np.ndarray) -> "ConformalCalibrator":
        r = np.abs(np.asarray(residuals, float)) / np.maximum(np.asarray(difficulties, float), 1e-6)
        r = r[np.isfinite(r)]
        self.n = int(r.size)
        if self.n == 0:
            self.q = float("nan")
            return self
        k = min(self.n, int(math.ceil((self.n + 1) * self.level)))
        self.q = float(np.sort(r)[k - 1])
        return self

    def interval(self, est: float, d: float) -> tuple[float, float]:
        if not np.isfinite(self.q):
            return float("nan"), float("nan")
        half = self.q * max(float(d), 1e-6)
        return est - half, est + half

    def summary(self) -> dict[str, Any]:
        return {"level": self.level, "q": self.q, "n_calibration": self.n, "floor": FLOOR, "distance_weight": DIST_WEIGHT,
                "fallback_spread": self.fallback_spread}
