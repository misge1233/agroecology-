"""Methodology 1 v2: the evidence model (E5).

Modules: :mod:`data` (training rows, features, weights, nested folds), :mod:`regressor`,
:mod:`ranker`, :mod:`matched`, :mod:`prior`, :mod:`stack`, :mod:`conformal`,
:mod:`select` (feature selection), :mod:`engine` (the components assembled into one
fit/rank object), :mod:`train` (the serving artifact). The harness engine is
:mod:`model.engines.m1_v2`.
"""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ARTIFACT_DIR = REPO_ROOT / "model" / "artifacts" / "m1_v2"
