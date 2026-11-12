"""The ``m0_current`` engine: the serving HistGBM refitted per fold (E4 Part 4).

Wraps the P7 code paths (``model/evaluate.py``: ``build_cat_maps``, ``encode``,
``make_model``, ``direction_map``) and the frozen dataset; nothing is forked. Per fold the
canonical model specification (``model_metrics.json`` ``model_label``, the P7 winner) is
fitted on the dataset rows whose ``Study_No_`` is not held out (``mask.filter_rows``:
the mask's study ids include every study of a held-out DOI group). The category maps
are built on the whole dataset, as the protocol does (a fixed vocabulary, no target
information).

Ranking a request:

* ``legacy_68`` queries carry the dataset row indices per candidate; the engine predicts
  exactly those rows and averages per practice, which is what ``evaluate.ranking_metrics``
  scores, so the P7 numbers reproduce (Part 6);
* store queries: only the 7 legacy indicators have features (``legacy_indicator``);
  other outcomes abstain. A candidate needs a frozen ``CSA_practices`` label (from the
  store's ERA/CSA rows, ``label_of``) and the request a full legacy context (``Rainfall``,
  ``Altitude_r``, ``temp_mean_annual``, ``precip_seasonality``, ``slope``, ``soil_clay``,
  ``land_cover``, ``aez_belt``); otherwise the item abstains. ``Crop_group`` comes from the
  request crop through the dataset (as ``recommend.py``), else the practice's modal group
  for the indicator; ``crop_type`` is the request crop when the dataset knows it, else
  ``Unspecified``.

Scores and estimates are on the oriented scale (prediction x direction). The 80 %
interval is ``+- 1.28 x`` the fold model's residual sd per indicator on its own training
rows (in-sample, so it understates the width; the coverage metric reports what it is).
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

import evaluate as ev  # model/evaluate.py (the P7 protocol; model/harness puts model/ on sys.path)
from model.engines.base import Z80, RankedItem, RankRequest
from model.harness import REPO_ROOT
from model.harness.mask import Mask

DATASET_PATH = ev.DATASET_PATH
METRICS_PATH = REPO_ROOT / "model" / "artifacts" / "model_metrics.json"
LEGACY_NUMERIC = ("Rainfall", "Altitude_r", "temp_mean_annual", "precip_seasonality", "slope", "soil_clay")


def canonical_spec(metrics_path: Path = METRICS_PATH) -> ev.ModelSpec:
    """The P7 winner from ``model_metrics.json`` (``model`` family and ``model_params``)."""
    m = json.loads(Path(metrics_path).read_text(encoding="utf-8"))
    return ev.ModelSpec(m["model"], dict(m.get("model_params") or {}))


class M0CurrentEngine:
    name = "m0_current"

    def __init__(self, dataset_path: Path = DATASET_PATH, spec: ev.ModelSpec | None = None,
                 label_of: dict[str, str] | None = None) -> None:
        self.dataset_path = Path(dataset_path)
        self.spec = spec or canonical_spec()
        self.label_of = dict(label_of or {})
        self.mask: Mask = Mask.empty()
        self.df: pd.DataFrame | None = None
        self.cmaps: dict[str, dict[str, int]] | None = None
        self.X: pd.DataFrame | None = None
        self.model: Any = None
        self.resid_sd: dict[str, float] = {}
        self.directions = ev.direction_map()
        self.crop_groups: dict[str, str] = {}
        self.crop_types: set[str] = set()
        self.family_of_label: dict[str, str] = {}
        self.n_train = 0

    # ------------------------------------------------------------ data
    def _load(self) -> None:
        if self.df is None:
            df = pd.read_csv(self.dataset_path)
            self.df = df
            self.cmaps = ev.build_cat_maps(df)
            self.X = ev.encode(df, self.cmaps)
            self.crop_groups = {str(c).lower(): str(g) for c, g in zip(df["crop_type"], df["Crop_group"])}
            self.crop_types = {str(c).lower() for c in df["crop_type"]}
            self.family_of_label = {str(p): str(f) for p, f in zip(df["CSA_practices"], df["practice_family"])}
            for label in df["CSA_practices"].unique():
                self.label_of.setdefault(str(label), str(label))  # a label is its own id when no store id exists

    def fit(self, train_rows: pd.DataFrame, mask: Mask) -> None:
        self._load()
        assert self.df is not None and self.X is not None
        self.mask = mask
        train = mask.filter_rows(self.df)
        idx = train.index
        y = self.df.loc[idx, ev.TARGET].to_numpy(float)
        cat_mask = [c in ev.CAT for c in ev.FEATURES]
        self.model = ev.make_model(self.spec, cat_mask)
        self.model.fit(self.X.loc[idx], y)
        self.n_train = int(len(idx))
        pred = self.model.predict(self.X.loc[idx])
        resid = pd.Series(y - pred, index=idx)
        self.resid_sd = {str(i): float(resid[self.df.loc[idx, "Indicator"] == i].std(ddof=1))
                         for i in self.df.loc[idx, "Indicator"].unique()}

    # ------------------------------------------------------------ ranking
    def _row(self, label: str, req: RankRequest, indicator: str) -> dict[str, Any] | None:
        assert self.df is not None
        ctx = req.context
        if any(ctx.get(k) is None for k in LEGACY_NUMERIC) or ctx.get("land_cover") is None or not ctx.get("aez_belt"):
            return None
        crop = (req.crop or "").lower()
        sub = self.df[(self.df["CSA_practices"] == label) & (self.df["Indicator"] == indicator)]
        fam = self.family_of_label.get(label)
        if fam is None:
            return None
        if crop in self.crop_groups:
            cg = self.crop_groups[crop]
        elif len(sub):
            cg = str(sub["Crop_group"].mode().iloc[0])
        else:
            cg = str(self.df[self.df["CSA_practices"] == label]["Crop_group"].mode().iloc[0])
        return {"CSA_practices": label, "practice_family": fam, "Crop_group": cg,
                "crop_type": req.crop if crop in self.crop_types else "Unspecified",
                "aez_belt": ctx["aez_belt"], "Indicator": indicator, "land_cover": int(ctx["land_cover"]),
                **{k: float(ctx[k]) for k in LEGACY_NUMERIC}}

    def rank(self, req: RankRequest) -> list[RankedItem]:
        assert self.df is not None and self.X is not None and self.model is not None and self.cmaps is not None
        indicator = req.legacy_indicator
        if not indicator or indicator not in self.directions:
            return [RankedItem(c, -math.inf, None, None, None, True, "model", []) for c in req.candidates]
        d = float(self.directions[indicator])
        sd = self.resid_sd.get(indicator, float("nan"))
        out: list[RankedItem] = []
        if req.legacy_rows:
            for c in req.candidates:
                rows = req.legacy_rows.get(c) or []
                if not rows:
                    out.append(RankedItem(c, -math.inf, None, None, None, True, "model", []))
                    continue
                pred = float(np.mean(self.model.predict(self.X.loc[rows]))) * d
                half = Z80 * sd if np.isfinite(sd) else float("nan")
                out.append(RankedItem(c, pred, pred, pred - half if np.isfinite(half) else None,
                                      pred + half if np.isfinite(half) else None, False, "model", []))
            return out
        rows, keep = [], []
        for c in req.candidates:
            label = self.label_of.get(c)
            r = self._row(label, req, indicator) if label else None
            if r is None:
                out.append(RankedItem(c, -math.inf, None, None, None, True, "model", []))
            else:
                rows.append(r)
                keep.append(c)
        if rows:
            frame = pd.DataFrame(rows)
            preds = self.model.predict(ev.encode(frame, self.cmaps)) * d
            half = Z80 * sd if np.isfinite(sd) else float("nan")
            by_c = {c: float(p) for c, p in zip(keep, preds)}
            ordered = []
            for c in req.candidates:
                if c in by_c:
                    p = by_c[c]
                    ordered.append(RankedItem(c, p, p, p - half if np.isfinite(half) else None,
                                              p + half if np.isfinite(half) else None, False, "model", []))
                else:
                    ordered.append(next(i for i in out if i.practice_id == c))
            return ordered
        return out

    def params(self) -> dict[str, Any]:
        try:
            dataset = str(self.dataset_path.relative_to(REPO_ROOT))
        except ValueError:
            dataset = str(self.dataset_path)
        return {"spec": self.spec.label, "dataset": dataset, "features": list(ev.FEATURES),
                "interval": "+- 1.28 x in-sample residual sd per indicator"}
