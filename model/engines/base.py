"""The engine interface every method implements (E4 Part 4).

An engine is fitted once per fold on the training rows (the store rows of the groups
that are not held out, already filtered by the fold's :class:`Mask`, and filtered again
inside :meth:`Engine.fit` through ``mask.filter_rows`` so the mask is the one place that
decides) and then answers :class:`RankRequest` objects. A :class:`RankedItem` per
candidate carries a score (higher is better for the objective), an optional effect
estimate on the oriented ``lrr`` scale with an 80 % interval, an abstention flag, the
lead source and citations. A method that cannot answer a query returns its candidates
with ``abstain=True``; it never changes the query.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

import pandas as pd

from model.harness.mask import Mask


@dataclass
class RankRequest:
    """One query as a method sees it (nothing else from the query's rows)."""

    query_id: str
    context: dict[str, Any]
    challenge_ids: list[str]
    outcome_id: str
    candidates: list[str]
    crop: str | None
    user_attrs: dict[str, Any]
    mask: Mask
    #: the oriented direction of the outcome (+1 higher is better, -1 lower is better),
    #: supplied so an engine can orient an lrr estimate; not part of the ground truth
    direction: int = 1
    #: objective group of the outcome (for priors with a group fallback)
    objective_group: str | None = None
    #: the legacy indicator name when the outcome is one of the 7 serving indicators
    legacy_indicator: str | None = None
    #: dataset row indices per candidate for the ``legacy_68`` continuity queries
    legacy_rows: dict[str, list[int]] = field(default_factory=dict)


@dataclass
class RankedItem:
    practice_id: str
    score: float
    est_lrr: float | None = None
    lo: float | None = None
    hi: float | None = None
    abstain: bool = False
    lead_source: str = "none"
    citations: list[str] = field(default_factory=list)


@runtime_checkable
class Engine(Protocol):
    name: str

    def fit(self, train_rows: pd.DataFrame, mask: Mask) -> None: ...

    def rank(self, req: RankRequest) -> list[RankedItem]: ...


def abstain_all(req: RankRequest, lead_source: str = "none") -> list[RankedItem]:
    """Every candidate abstained, in request order (a method that cannot answer)."""
    return [RankedItem(c, 0.0, None, None, None, True, lead_source, []) for c in req.candidates]


Z80 = 1.2815515655446004  # 80 % two-sided normal interval half-width in sd units
