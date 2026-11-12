"""The ``m1_v2`` harness engine and its component and ablation variants (E5 Part 2.7).

Implements the E4 :class:`~model.engines.base.Engine` protocol over
:class:`model.m1.engine.M1Engine`: ``fit`` learns everything inside the fold's mask,
``rank`` answers every candidate with a score, an effect estimate, the conformal 80 %
interval, ``abstain = False``, the lead source (``model``, ``matched_studies`` or
``prior``) and the citations. :data:`VARIANTS` lists the configurations of brief Part 3:
each component alone (with the prior fallback) and the ablations.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Any

import pandas as pd

from model.engines.base import RankedItem, RankRequest
from model.harness.mask import Mask
from model.m1.data import DataConfig
from model.m1.engine import M1Config, M1Engine

#: fusion labels of the lead sources (docs/decisions/evidence_fusion.md)
FUSION_LABEL = {"model": "model-led", "matched_studies": "study-led", "prior": "documented"}

_BASE = M1Config()
VARIANTS: dict[str, M1Config] = {
    "m1_v2": _BASE,
    # components alone (the prior answers what the component cannot)
    "m1_regressor": replace(_BASE, name="m1_regressor", use_ranker=False, use_matched=False, stacker="ridge"),
    "m1_ranker": replace(_BASE, name="m1_ranker", use_regressor=False, use_matched=False, select=False, tune=False, stacker="ridge"),
    "m1_matched": replace(_BASE, name="m1_matched", use_regressor=False, use_ranker=False, select=False, stacker="ridge"),
    "m1_prior": replace(_BASE, name="m1_prior", use_regressor=False, use_ranker=False, use_matched=False, select=False, tune=False, stacker="ridge"),
    # ablations (tuned settings of the headline are not reused: each fits its own inner choices without the grid)
    "m1_nobelt": replace(_BASE, name="m1_nobelt", data=replace(_BASE.data, use_belt=False), tune=False),
    "m1_legacy11": replace(_BASE, name="m1_legacy11", data=replace(_BASE.data, context="legacy11", use_koppen=False), tune=False),
    "m1_nohab": replace(_BASE, name="m1_nohab", data=replace(_BASE.data, include_hab=False), tune=False),
    "m1_nocountry": replace(_BASE, name="m1_nocountry", data=replace(_BASE.data, include_country_precision=False), tune=False),
    "m1_wquality": replace(_BASE, name="m1_wquality", data=replace(_BASE.data, weight_scheme="quality"), tune=False),
    "m1_noranker": replace(_BASE, name="m1_noranker", use_ranker=False, tune=False),
    "m1_nomatched": replace(_BASE, name="m1_nomatched", use_matched=False, tune=False),
    "m1_rankavg": replace(_BASE, name="m1_rankavg", stacker="rank_avg", tune=False),
    "m1_ridge": replace(_BASE, name="m1_ridge", stacker="ridge", tune=False),
    "m1_notune": replace(_BASE, name="m1_notune", tune=False, select=False),
    # E5.1, post-hoc, pre-registered 12 Nov 2026 (E6 brief Part 0): wider stacker choice scored by
    # the mean of inner top-1 and C-index, and Mondrian conformal per objective group
    "m1_v2_e51": replace(_BASE, name="m1_v2_e51", stacker_set="e51", conformal_by_group=True),
}


class M1V2Engine:
    """Harness engine over :class:`M1Engine`; one instance per variant name."""

    def __init__(self, cfg: M1Config | None = None, outcome_group: dict[str, str] | None = None,
                 family_of: dict[str, str] | None = None, components_of: dict[str, list[str]] | None = None,
                 belt_code_of: dict[str, int] | None = None) -> None:
        self.cfg = cfg or _BASE
        self.name = self.cfg.name
        self.outcome_group = dict(outcome_group or {})
        self.family_of = dict(family_of or {})
        self.components_of = {k: list(v) for k, v in (components_of or {}).items()}
        self.belt_code_of = dict(belt_code_of or {})
        self.engine: M1Engine | None = None
        self.mask: Mask = Mask.empty()
        self.fit_summaries: list[dict[str, Any]] = []

    def fit(self, train_rows: pd.DataFrame, mask: Mask) -> None:
        self.mask = mask
        self.engine = M1Engine(self.cfg, self.outcome_group, self.family_of, self.components_of, self.belt_code_of)
        self.fit_summaries.append(self.engine.fit(train_rows, mask))

    def rank(self, req: RankRequest) -> list[RankedItem]:
        assert self.engine is not None, "fit first"
        items = self.engine.rank(req.context, req.candidates, req.outcome_id, req.objective_group, req.crop,
                                 req.user_attrs, qkey=req.query_id)
        return [RankedItem(it["practice_id"], it["score"], it["est_lrr"], it["lo"], it["hi"], False, it["lead_source"],
                           list(it["citations"])) for it in items]

    def params(self) -> dict[str, Any]:
        d = self.cfg.__dict__.copy()
        d["data"] = self.cfg.data.__dict__.copy()
        last = self.fit_summaries[-1] if self.fit_summaries else {}
        d["last_fit"] = {k: last.get(k) for k in ("n_rows", "n_training_queries", "regressor_params", "matched_k",
                                                   "matched_power", "features") if k in last}
        d["last_fit"]["stacker_chosen"] = (last.get("stacker") or {}).get("chosen")
        # one entry per outer fold fitted in this run (per-fold kept features, stacker, conformal q)
        d["folds"] = [{"features": f.get("features"), "stacker": (f.get("stacker") or {}).get("chosen"),
                       "conformal_q": (f.get("conformal") or {}).get("q"), "n_rows": f.get("n_rows"),
                       **({"conformal_q_by_group": f["conformal"]["q_by_group"]} if (f.get("conformal") or {}).get("by_group") else {}),
                       **({"stacker_scores": {k: v["selection"] for k, v in f["stacker"].items() if isinstance(v, dict) and "selection" in v}}
                          if (f.get("stacker") or {}).get("rule") else {})}
                      for f in self.fit_summaries]
        d["last_fit"]["conformal_q"] = (last.get("conformal") or {}).get("q")
        return d


def make(name: str, **maps: Any) -> M1V2Engine:
    if name not in VARIANTS:
        raise KeyError(f"unknown M1 variant {name!r}; known: {sorted(VARIANTS)}")
    return M1V2Engine(VARIANTS[name], **maps)
