"""Ranking engines behind one interface (E4 Part 4).

Every method the protocol compares is an :class:`model.engines.base.Engine`: it is
fitted on the training rows of a fold with the fold's :class:`~model.harness.mask.Mask`
and ranks the candidates of a :class:`~model.engines.base.RankRequest`. Baselines in
this phase: ``random``, ``practice_prior``, ``nearest_studies`` and ``m0_current`` (the
serving HistGBM refitted per fold through ``model/evaluate.py``). :func:`registry` maps
method names to engine classes for the harness CLI.
"""
from __future__ import annotations

from typing import Any


def registry() -> dict[str, Any]:
    """Method name -> engine class (imported lazily so a missing optional dependency only
    breaks the engine that needs it)."""
    from model.engines.m0_current import M0CurrentEngine
    from model.engines.m1_v2 import VARIANTS, M1V2Engine
    from model.engines.nearest_studies import NearestStudiesEngine
    from model.engines.practice_prior import PracticePriorEngine
    from model.engines.random_engine import RandomEngine

    out: dict[str, Any] = {"random": RandomEngine, "practice_prior": PracticePriorEngine,
                           "nearest_studies": NearestStudiesEngine, "m0_current": M0CurrentEngine}
    # E5: Methodology 1 v2 and its component and ablation variants (one class, one config each)
    for name, cfg in VARIANTS.items():
        out[name] = (lambda cfg=cfg: (lambda **kw: M1V2Engine(cfg, **kw)))()
    return out
