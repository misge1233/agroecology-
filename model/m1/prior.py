"""The shrunken practice prior of Methodology 1 v2 (E5 Part 2.4): the last link of the
fallback chain, which answers every candidate.

Empirical-Bayes estimate per (practice, objective group): the cell mean of the oriented
effect shrunk toward the practice's **component mean** (the mean over training rows of
practices that share at least one component with it, weighted by the number of shared
components), then toward its **family mean**, then the grand mean. Shrinkage weight
``n / (n + kappa)`` with ``kappa = sigma_w^2 / tau^2`` from the method of moments
(``sigma_w^2`` the pooled within-cell variance, ``tau^2`` the between-cell variance of the
cell means minus their sampling part, floored at a small value); the random-effects
interval is ``+- 1.28 x sqrt(sigma_w^2 / (n + kappa))``.
"""
from __future__ import annotations

import math
from typing import Any, Mapping

import numpy as np
import pandas as pd

from model.engines.base import Z80

TAU2_FLOOR = 1e-4


class ShrunkenPrior:
    name = "prior"

    def __init__(self, family_of: Mapping[str, str] | None = None, components_of: Mapping[str, list[str]] | None = None) -> None:
        self.family_of = dict(family_of or {})
        self.components_of = {k: list(v) for k, v in (components_of or {}).items()}
        self.cell: dict[tuple[str, str], tuple[float, int]] = {}
        self.practice: dict[str, tuple[float, int]] = {}
        self.component_group: dict[tuple[str, str], tuple[float, int]] = {}
        self.family_group: dict[tuple[str, str], tuple[float, int]] = {}
        self.grand = 0.0
        self.sigma2 = 1.0
        self.tau2 = TAU2_FLOOR
        self.kappa = 1.0

    def fit(self, rows: pd.DataFrame) -> "ShrunkenPrior":
        y = rows["y"].astype(float)
        pid = rows["practice_id"].astype(str)
        grp = rows["objective_group"].astype(str)
        self.grand = float(y.mean()) if len(rows) else 0.0
        cells = pd.DataFrame({"y": y, "p": pid, "g": grp}).groupby(["p", "g"])["y"]
        stats = cells.agg(["mean", "count", "var"])
        self.cell = {(p, g): (float(m), int(n)) for (p, g), m, n in zip(stats.index, stats["mean"], stats["count"])}
        self.practice = {p: (float(s["mean"]), int(s["count"])) for p, s in pd.DataFrame({"y": y, "p": pid}).groupby("p")["y"].agg(["mean", "count"]).iterrows()}
        within = stats["var"].dropna()
        counts = stats.loc[within.index, "count"]
        self.sigma2 = float(np.sum(within * (counts - 1)) / max(float(np.sum(counts - 1)), 1.0)) if len(within) else float(y.var()) if len(y) > 1 else 1.0
        self.sigma2 = max(self.sigma2, TAU2_FLOOR)
        means = stats["mean"]
        if len(means) > 1:
            self.tau2 = max(float(means.var()) - self.sigma2 * float(np.mean(1.0 / stats["count"])), TAU2_FLOOR)
        self.kappa = self.sigma2 / self.tau2
        # component-level and family-level means per objective group
        for p, f in zip(pid, rows["practice_family"].astype(object)):
            if isinstance(f, str) and f:
                self.family_of.setdefault(p, f)
        for p, c in zip(pid, rows["practice_components"].astype(object)):
            if isinstance(c, str) and c and not self.components_of.get(p):
                self.components_of[p] = [x for x in c.split(";") if x]
        comp_rows: dict[tuple[str, str], list[float]] = {}
        for p, g, v in zip(pid, grp, y):
            for c in self.components_of.get(p, []):
                comp_rows.setdefault((c, g), []).append(float(v))
        self.component_group = {k: (float(np.mean(v)), len(v)) for k, v in comp_rows.items()}
        fam = pd.DataFrame({"y": y, "f": pid.map(self.family_of).fillna("unknown"), "g": grp}).groupby(["f", "g"])["y"].agg(["mean", "count"])
        self.family_group = {(f, g): (float(m), int(n)) for (f, g), m, n in zip(fam.index, fam["mean"], fam["count"])}
        return self

    def prior_mean(self, practice_id: str, group: str) -> tuple[float, str]:
        """The shrinkage target of a practice: component mean, else family mean, else grand."""
        comps = self.components_of.get(practice_id, [])
        hits = [(self.component_group[(c, group)][0], self.component_group[(c, group)][1]) for c in comps if (c, group) in self.component_group]
        if hits:
            w = np.array([n for _, n in hits], float)
            return float(np.sum(w * np.array([m for m, _ in hits])) / w.sum()), "component"
        fam = self.family_of.get(practice_id)
        if fam and (fam, group) in self.family_group:
            return self.family_group[(fam, group)][0], "family"
        if practice_id in self.practice:
            return self.practice[practice_id][0], "practice_all"
        return self.grand, "grand"

    def estimate(self, practice_id: str, group: str) -> dict[str, Any]:
        m0, level = self.prior_mean(practice_id, group)
        mean, n = self.cell.get((practice_id, group), (m0, 0))
        shrink = n / (n + self.kappa)
        est = shrink * mean + (1.0 - shrink) * m0
        se = math.sqrt(self.sigma2 / (n + self.kappa))
        return {"est": est, "lo": est - Z80 * se, "hi": est + Z80 * se, "se": se, "n": n, "shrink": shrink,
                "prior_level": level}
