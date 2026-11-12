"""Heuristic ranking baselines without a language model (E7 Part A4).

Two fixed orderings test whether the zero-evidence LLM's advantage is trial-design
structure (combined or input-heavy treatments are usually the ones built to win):

* ``component_count``: more practice components first; ties broken by the practice prior
  (the E4 ``practice_prior`` of the fold), then by practice id.
* ``input_intensity``: practices ordered by the summed input level of their components
  (:data:`COMPONENT_INPUT_LEVEL`), ties by the family level (:data:`FAMILY_INPUT_LEVEL`),
  then by the practice prior, then by practice id.

**The input-level table was written on 12 Nov 2026 from the taxonomy only**
(`pipelines/taxonomy` components and families), before any E7 result, and is not tuned:

* 3, high external input or investment: purchased mineral fertilizer, lime, improved or
  bred genetics, irrigation of any kind, biochar production, purchased feed supplements;
* 2, moderate: on-farm organic inputs and residues, labour-built soil and water structures
  and water harvesting, planted trees and integrated packages without purchased inputs,
  feed processing and substitution, improved stoves;
* 1, management only: intercropping, rotation, tillage changes, weeding, grazing and
  pasture management, exclosure, parkland and pruning management, and *reducing* an input.

Unknown components count 1. Neither engine produces an effect estimate or interval; they
never abstain. Both are ranking-only baselines for the validity tests.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

import pandas as pd

from model.engines.base import RankedItem, RankRequest
from model.engines.practice_prior import PracticePriorEngine
from model.harness.mask import Mask

COMPONENT_INPUT_LEVEL: dict[str, int] = {
    # 3: high external input or investment
    "Inorganic Fertilizer": 3, "pH Control": 3, "Improved Varieties": 3, "Drought Tolerant Crops": 3,
    "Genetic Improvement": 3, "Drip Irrigation": 3, "Supplemental Irrigation": 3, "Furrow Irrigation": 3,
    "Alternate Furrow Irrigation": 3, "Deficit Irrigation": 3, "Overhead Irrigation with Mulching": 3,
    "Biochar": 3, "Feed Addition": 3, "ISFM": 3,
    # 2: moderate, mostly on-farm inputs or labour-built structures
    "Organic Fertilizer": 2, "Organic Amendments": 2, "Mulch": 2, "Crop Residue Incorporation": 2,
    "Water Harvesting": 2, "In-situ Water Harvesting": 2, "situ water harvesting": 2,
    "Physical SWC Measures": 2, "Physical + Biological SWC Practices": 2, "Agronomic/Biological SWC Practices": 2,
    "Biological SWC Practices": 2, "Multistrata Agroforestry": 2, "Alleycropping": 2, "Silvopasture": 2,
    "Improved Fallow": 2, "Agroforestry Fallow": 2, "IWM": 2, "Feed Processing": 2, "Feed Substitution": 2,
    "Animal Feed Management": 2, "Cookstove": 2,
    # 1: management only, or reducing an input
    "Intercropping": 1, "Crop Rotation": 1, "Intercropping or Rotation": 1, "Reduced Tillage": 1,
    "Conservation Tillage": 1, "Weeding": 1, "Grazing Management": 1, "Pasture Management": 1, "Exclosure": 1,
    "Ex": 1, "Parklands": 1, "Agroforestry Pruning": 1, "Other Agroforestry": 1, "Inorganic Fertilizer Reduction": 1,
}
FAMILY_INPUT_LEVEL: dict[str, int] = {
    "Integrated soil fertility management": 3, "Erosion control and water management": 2,
    "Crop production and management": 2, "Livestock production and management": 2,
    "Agro-forestry and forest management": 1,
}


def table_hash() -> str:
    """Identity of the fixed input-level tables (recorded in every run's config)."""
    blob = json.dumps({"components": COMPONENT_INPUT_LEVEL, "families": FAMILY_INPUT_LEVEL}, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class _HeuristicEngine:
    """Order candidates by a fixed key; ties by the fold's practice prior, then by id."""

    name = "heuristic"

    def __init__(self, outcome_group: dict[str, str] | None = None, family_of: dict[str, str] | None = None,
                 components_of: dict[str, list[str]] | None = None) -> None:
        self.family_of = dict(family_of or {})
        self.components_of = {k: list(v) for k, v in (components_of or {}).items()}
        self.prior = PracticePriorEngine(outcome_group, family_of)

    def fit(self, train_rows: pd.DataFrame, mask: Mask) -> None:
        self.prior.fit(train_rows, mask)

    def key(self, pid: str) -> tuple[float, ...]:  # pragma: no cover - overridden
        raise NotImplementedError

    def rank(self, req: RankRequest) -> list[RankedItem]:
        prior = {it.practice_id: (it.score if not it.abstain else float("-inf")) for it in self.prior.rank(req)}
        order = sorted(req.candidates, key=lambda p: (*self.key(p), prior[p], p), reverse=True)
        pos = {p: i for i, p in enumerate(order)}
        n = len(order)
        return [RankedItem(p, float(n - pos[p]), None, None, None, False, self.name, []) for p in req.candidates]


class ComponentCountEngine(_HeuristicEngine):
    name = "component_count"

    def key(self, pid: str) -> tuple[float, ...]:
        return (float(len(self.components_of.get(pid) or [pid])),)

    def params(self) -> dict[str, Any]:
        return {"order": "number of components, then practice prior, then id"}


class InputIntensityEngine(_HeuristicEngine):
    name = "input_intensity"

    def key(self, pid: str) -> tuple[float, ...]:
        comps = self.components_of.get(pid) or []
        level = sum(COMPONENT_INPUT_LEVEL.get(c, 1) for c in comps) if comps else 1
        return (float(level), float(FAMILY_INPUT_LEVEL.get(self.family_of.get(pid, ""), 1)))

    def params(self) -> dict[str, Any]:
        return {"order": "summed component input level, then family level, then practice prior, then id",
                "table_sha256": table_hash(), "written": "12 Nov 2026, from the taxonomy only, before any E7 run"}
