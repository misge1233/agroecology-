"""The ``nearest_studies`` baseline: pooled LRR of the k nearest training sites (E4 Part 4).

The study-led source of evidence fusion, formalised (roadmap 8.1). Training rows of a
fold are pooled per ``(group, site, practice_id, outcome_id)`` into one effect
(``model.harness.queries.pool_effects``: inverse-variance when every row has
``var_lrr``, else the store-weighted mean) with the site's context vector. For a
request, every candidate is estimated from the ``k = 10`` nearest training sites that
report the candidate for the same outcome (fallback: the same objective group):

* **context vector**: the release layers the serving model uses plus the new ones
  (:data:`CONTEXT_LAYERS`; ``flow_accumulation`` is log-scaled), standardised with the
  training mean and sd; queries with only a reported context (country precision,
  non-Ethiopian sites) use the dimensions they have (rainfall, altitude, slope);
* **distance**: root mean square of the standardised differences over the dimensions
  both sides have (so sites with fewer dimensions are comparable);
* **weights**: ``w_i = 1 / (1 + d_i^2)`` times the inverse variance when ``var_lrr``
  exists for the pooled effect, else times the inverse of the median training variance;
* **estimate**: weighted mean of the oriented effects; 80 % interval
  ``+- 1.28 x sd_w / sqrt(n_eff)`` with the weighted sd and Kish's effective n;
* **abstention**: fewer than :data:`K_MIN` (3) distinct groups among the nearest sites.

Citations are the study ids of the sites used.
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from model.engines.base import Z80, RankedItem, RankRequest
from model.harness.mask import Mask, group_key
from model.harness.queries import pool_effects, site_key

CONTEXT_LAYERS = ("precip_annual", "temp_mean_annual", "precip_seasonality", "elevation", "slope", "soil_clay",
                  "lgp_days", "soil_ph", "soil_soc", "slope_length_factor", "tpi", "twi", "flow_accumulation",
                  "dist_to_stream_m", "soil_sand", "soil_bulk_density", "soil_cec", "soil_nitrogen", "soil_awc",
                  "soil_depth_bedrock", "rain_mean_1991_2020", "rain_cv_interannual", "dry_season_length_months",
                  "pet_hargreaves_annual", "aridity_index", "cropland_fraction_1km", "travel_time_to_city_min")
LOG_LAYERS = ("flow_accumulation",)
#: reported-context fallback: legacy feature name -> layer dimension
REPORTED_DIMS = {"Rainfall": "precip_annual", "Altitude_r": "elevation", "slope": "slope"}
K = 10
K_MIN = 3


def context_vector(ctx: dict[str, Any]) -> np.ndarray:
    """Raw (unstandardised) vector over :data:`CONTEXT_LAYERS`; ``nan`` where the context lacks a layer."""
    v = np.full(len(CONTEXT_LAYERS), np.nan)
    for i, lid in enumerate(CONTEXT_LAYERS):
        x = ctx.get(f"ctx_{lid}")
        if x is None:
            feat = next((f for f, d in REPORTED_DIMS.items() if d == lid), None)
            x = ctx.get(feat) if feat else None
        if x is not None and not (isinstance(x, float) and math.isnan(x)):
            v[i] = math.log1p(max(float(x), 0.0)) if lid in LOG_LAYERS else float(x)
    return v


class NearestStudiesEngine:
    name = "nearest_studies"

    def __init__(self, outcome_group: dict[str, str] | None = None, k: int = K, k_min: int = K_MIN) -> None:
        self.outcome_group = dict(outcome_group or {})
        self.k, self.k_min = int(k), int(k_min)
        self.mask: Mask = Mask.empty()
        self.sites = pd.DataFrame()
        self.vectors = np.zeros((0, len(CONTEXT_LAYERS)))
        self.mu = np.zeros(len(CONTEXT_LAYERS))
        self.sd = np.ones(len(CONTEXT_LAYERS))
        self.default_var = 1.0

    def fit(self, train_rows: pd.DataFrame, mask: Mask) -> None:
        self.mask = mask
        rows = mask.filter_rows(train_rows)
        rows = rows[rows["lrr"].notna() & rows["direction"].notna() & rows["practice_id"].notna()
                    & rows["outcome_id"].notna()].copy()
        rows["group"] = [group_key(d, s) for d, s in zip(rows["doi"], rows["study_id"])]
        rows["site"] = [site_key(a, b, n) for a, b, n in zip(rows["lat"], rows["lon"], rows["site_name"])]
        recs, vecs = [], []
        for (g, s, pid, oid), q in rows.groupby(["group", "site", "practice_id", "outcome_id"], sort=True):
            pooled, var, method = pool_effects(q["lrr"].to_numpy(), q["var_lrr"].to_numpy(), q["weight"].to_numpy())
            first = q.iloc[0]
            ctx = {f"ctx_{lid}": (None if pd.isna(first.get(f"ctx_{lid}")) else float(first.get(f"ctx_{lid}")))
                   for lid in CONTEXT_LAYERS if f"ctx_{lid}" in q.columns}
            for col, feat in (("ctx_reported_rain_mm", "Rainfall"), ("ctx_reported_altitude_m", "Altitude_r"),
                              ("ctx_reported_slope_pct", "slope")):
                if col in q.columns and pd.notna(first.get(col)):
                    ctx[feat] = float(first[col])
            recs.append({"group": g, "site": s, "practice_id": pid, "outcome_id": oid,
                         "objective_group": self.outcome_group.get(oid, "other"),
                         "y": pooled * float(first["direction"]), "var": var, "n_rows": int(len(q)),
                         "study_id": str(first["study_id"])})
            vecs.append(context_vector(ctx))
        self.sites = pd.DataFrame(recs)
        self.vectors = np.vstack(vecs) if vecs else np.zeros((0, len(CONTEXT_LAYERS)))
        if len(self.vectors):
            with np.errstate(invalid="ignore"):
                self.mu = np.nanmean(self.vectors, axis=0)
                sd = np.nanstd(self.vectors, axis=0)
            self.sd = np.where(np.isfinite(sd) & (sd > 0), sd, 1.0)
            self.mu = np.where(np.isfinite(self.mu), self.mu, 0.0)
            v = self.sites["var"].to_numpy(float)
            self.default_var = float(np.nanmedian(v)) if np.isfinite(v).any() else 1.0
        self._z = (self.vectors - self.mu) / self.sd

    def _distances(self, ctx: dict[str, Any], idx: np.ndarray) -> np.ndarray:
        q = (context_vector(ctx) - self.mu) / self.sd
        diff = self._z[idx] - q[None, :]
        ok = np.isfinite(diff)
        n_ok = ok.sum(axis=1)
        sq = np.where(ok, diff ** 2, 0.0).sum(axis=1)
        with np.errstate(invalid="ignore", divide="ignore"):
            d = np.sqrt(sq / np.maximum(n_ok, 1))
        d[n_ok == 0] = np.inf  # no shared dimension: not comparable
        return d

    def rank(self, req: RankRequest) -> list[RankedItem]:
        out = []
        group = req.objective_group or self.outcome_group.get(req.outcome_id, "other")
        for c in req.candidates:
            cand = np.flatnonzero((self.sites["practice_id"] == c).to_numpy() & (self.sites["outcome_id"] == req.outcome_id).to_numpy()) \
                if len(self.sites) else np.array([], int)
            if len(cand) < self.k_min:
                cand = np.flatnonzero((self.sites["practice_id"] == c).to_numpy() & (self.sites["objective_group"] == group).to_numpy()) \
                    if len(self.sites) else np.array([], int)
            if len(cand) == 0:
                out.append(RankedItem(c, -math.inf, None, None, None, True, "nearest_studies", []))
                continue
            d = self._distances(req.context, cand)
            order = np.argsort(d, kind="stable")[: self.k]
            sel = cand[order]
            d_sel = d[order]
            finite = np.isfinite(d_sel)
            sel, d_sel = sel[finite], d_sel[finite]
            groups = self.sites["group"].to_numpy()[sel]
            if len(set(groups)) < self.k_min:
                out.append(RankedItem(c, -math.inf, None, None, None, True, "nearest_studies",
                                      sorted(set(self.sites["study_id"].to_numpy()[sel]))))
                continue
            y = self.sites["y"].to_numpy(float)[sel]
            var = self.sites["var"].to_numpy(float)[sel]
            iv = np.where(np.isfinite(var) & (var > 0), 1.0 / np.where(np.isfinite(var) & (var > 0), var, 1.0), 1.0 / self.default_var)
            w = iv / (1.0 + d_sel ** 2)
            est = float(np.sum(w * y) / np.sum(w))
            n_eff = float(np.sum(w) ** 2 / np.sum(w ** 2))
            sd_w = float(math.sqrt(np.sum(w * (y - est) ** 2) / np.sum(w))) if len(y) > 1 else float("nan")
            half = Z80 * sd_w / math.sqrt(max(n_eff, 1.0)) if np.isfinite(sd_w) else float("nan")
            lo, hi = (est - half, est + half) if np.isfinite(half) else (None, None)
            out.append(RankedItem(c, est, est, lo, hi, False, "nearest_studies",
                                  sorted(set(self.sites["study_id"].to_numpy()[sel]))))
        return out

    def params(self) -> dict[str, Any]:
        return {"k": self.k, "k_min": self.k_min, "context_layers": list(CONTEXT_LAYERS), "log_layers": list(LOG_LAYERS),
                "distance": "RMS of standardised differences over shared dimensions",
                "weights": "1/(1+d^2) x inverse variance (median training variance when absent)"}
