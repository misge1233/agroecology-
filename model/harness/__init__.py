"""The evaluation harness (E4): one query set, deterministic folds, one masking
mechanism, one metric library, one prediction format and one report generator for
every method (roadmap sections 11 and Appendix B, ``docs/briefs/E4_evaluation_harness.md``).

Modules: :mod:`queries` (Part 1), :mod:`folds` (Part 2), :mod:`mask` (Part 3),
:mod:`report` and :mod:`run` (Part 5). Engines live in :mod:`model.engines`; the metric
library is :mod:`model.metrics`.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
# model/evaluate.py and pipelines/dataset/assign_folds.py are script-style modules
# (``import evaluate``, ``from assign_folds import ...``), as train_model.py imports them.
for _p in (REPO_ROOT / "model", REPO_ROOT / "pipelines" / "dataset"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
HARNESS_DIR = REPO_ROOT / "data" / "evidence" / "harness"
RUNS_DIR = REPO_ROOT / "model" / "harness" / "runs"
REPORTS_DIR = REPO_ROOT / "model" / "reports"
RELEASE = "ET/2026.1"
