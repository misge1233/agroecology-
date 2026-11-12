"""The ``practice_prior`` baseline: mean oriented LRR per practice and objective group (E4 Part 4).

Fitted on the training rows of a fold (after ``mask.filter_rows``): for every
``(practice_id, objective_group)`` the mean, sd and count of the oriented ``lrr``
(``lrr x direction``, higher is better). A candidate without rows for the objective
group falls back to its ``(practice_family, objective_group)`` mean, then to its
practice mean over every group; with nothing at all the item abstains. The 80 %
interval is ``mean +- 1.28 x sd / sqrt(n)`` (sd of the fallback level when a cell has
one row). Scores equal the estimate.
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from model.engines.base import Z80, RankedItem, RankRequest
from model.harness.mask import Mask

MIN_ROWS = 1


class PracticePriorEngine:
    name = "practice_prior"

    def __init__(self, outcome_group: dict[str, str] | None = None, family_of: dict[str, str] | None = None) -> None:
        self.outcome_group = dict(outcome_group or {})
        self.family_of = dict(family_of or {})
        self.mask: Mask = Mask.empty()
        self.by_practice_group: dict[tuple[str, str], tuple[float, float, int]] = {}
        self.by_family_group: dict[tuple[str, str], tuple[float, float, int]] = {}
        self.by_practice: dict[str, tuple[float, float, int]] = {}
        self.pooled_sd: float = float("nan")

    @staticmethod
    def _stats(g: pd.Series) -> tuple[float, float, int]:
        v = g.to_numpy(float)
        return float(v.mean()), (float(v.std(ddof=1)) if len(v) > 1 else float("nan")), int(len(v))

    def fit(self, train_rows: pd.DataFrame, mask: Mask) -> None:
        self.mask = mask
        rows = mask.filter_rows(train_rows)
        rows = rows[rows["lrr"].notna() & rows["direction"].notna() & rows["practice_id"].notna()
                    & rows["outcome_id"].notna()].copy()
        rows["oriented"] = rows["lrr"].astype(float) * rows["direction"].astype(float)
        rows["group"] = rows["outcome_id"].map(lambda o: self.outcome_group.get(o, "other"))
        fam = rows["practice_family"].where(rows["practice_family"].notna(),
                                            rows["practice_id"].map(self.family_of))
        rows["family"] = fam.fillna("unknown")
        self.by_practice_group = {k: self._stats(g["oriented"]) for k, g in rows.groupby(["practice_id", "group"])}
        self.by_family_group = {k: self._stats(g["oriented"]) for k, g in rows.groupby(["family", "group"])}
        self.by_practice = {k: self._stats(g["oriented"]) for k, g in rows.groupby("practice_id")}
        self.pooled_sd = float(rows["oriented"].std(ddof=1)) if len(rows) > 1 else float("nan")
        for pid, f in zip(rows["practice_id"], rows["family"]):
            self.family_of.setdefault(str(pid), str(f))

    def _lookup(self, pid: str, group: str) -> tuple[tuple[float, float, int], str] | None:
        if (pid, group) in self.by_practice_group:
            return self.by_practice_group[(pid, group)], "practice_group"
        fam = self.family_of.get(pid)
        if fam and (fam, group) in self.by_family_group:
            return self.by_family_group[(fam, group)], "family_group"
        if pid in self.by_practice:
            return self.by_practice[pid], "practice_all"
        return None

    def rank(self, req: RankRequest) -> list[RankedItem]:
        group = req.objective_group or self.outcome_group.get(req.outcome_id, "other")
        out = []
        for c in req.candidates:
            hit = self._lookup(c, group)
            if hit is None:
                out.append(RankedItem(c, -math.inf, None, None, None, True, "practice_prior", []))
                continue
            (mean, sd, n), level = hit
            sd_eff = sd if np.isfinite(sd) else self.pooled_sd
            half = Z80 * sd_eff / math.sqrt(max(n, 1)) if np.isfinite(sd_eff) else float("nan")
            lo, hi = (mean - half, mean + half) if np.isfinite(half) else (None, None)
            out.append(RankedItem(c, mean, mean, lo, hi, False, f"practice_prior:{level}", []))
        return out

    def params(self) -> dict[str, Any]:
        return {"interval": "mean +- 1.28 sd/sqrt(n)", "fallbacks": ["family_group", "practice_all"]}
