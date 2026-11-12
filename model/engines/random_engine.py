"""The ``random`` baseline: a seeded uniform score per candidate (E4 Part 4).

Its expected metrics are known analytically (``model.metrics.expected_random``):
top-1 = mean 1/n, top-half = mean floor(n/2)/n, C-index 0.5, median Spearman 0;
the unit test checks the engine against them. It gives no numbers (``est_lrr`` None)
and never abstains.
"""
from __future__ import annotations

import random

import pandas as pd

from model.engines.base import RankedItem, RankRequest
from model.harness.mask import Mask


class RandomEngine:
    name = "random"

    def __init__(self, seed: int = 0) -> None:
        self.seed = int(seed)
        self.mask: Mask = Mask.empty()

    def fit(self, train_rows: pd.DataFrame, mask: Mask) -> None:
        self.mask = mask  # nothing to learn; the mask is kept for the record

    def rank(self, req: RankRequest) -> list[RankedItem]:
        rng = random.Random(f"{self.seed}:{req.query_id}")
        return [RankedItem(c, rng.random(), None, None, None, False, "random", []) for c in req.candidates]

    def params(self) -> dict[str, int]:
        return {"seed": self.seed}
