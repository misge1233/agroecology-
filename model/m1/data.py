"""Training rows, features, weights and nested folds of Methodology 1 v2 (E5 Part 1).

**Rows**: the store rows eligible for the harness (reviewed direction, computable ``lrr``,
practice and outcome ids, not a duplicate, not an unchecked geocode) after
``mask.filter_rows``; country-precision rows enter with missing context and a
``ctx_missing`` flag (an ablation excludes them, another excludes the Habtamu rows).

**Target**: the oriented effect ``y = direction x lrr`` (benefit positive for every outcome).

**Features** (:class:`FeatureEncoder`, fitted on training rows only): the release ``ctx_*``
layers (27; ``flow_accumulation`` log-scaled; or the 9 numeric legacy layers), the belt as
one categorical attribute, the Köppen class, land cover, crop group, practice family,
outcome id, objective group, source, quality flag, location precision, duration, a
``ctx_missing`` flag, the practice components (multi-hot over the component layer) and
the practice id target-encoded with counts (smoothed; out-of-fold on the training rows
through the inner folds). Nothing is computed from a query's own rows: a query's features
come from its context, its outcome and the practice taxonomy.

**Weights**: ``inverse_variance`` (the store ``weight``: inverse variance where ``var_lrr``
exists, capped at its 99th percentile, else the store's quality default) or ``quality``
(High 1.0, Medium 0.8, NR/Low 0.6 for every row).

**Inner folds**: study-grouped, by the P7 greedy assigner on group sizes (deterministic).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping

import numpy as np
import pandas as pd

from model.engines.nearest_studies import CONTEXT_LAYERS, LOG_LAYERS
from model.harness import queries as hq
from model.harness.folds import assign_units
from model.harness.mask import Mask, group_key

LEGACY_LAYERS = ("precip_annual", "temp_mean_annual", "precip_seasonality", "elevation", "slope", "soil_clay",
                 "lgp_days", "soil_ph", "soil_soc")
#: legacy (serving) feature name -> layer; used for reported contexts and the legacy_68 queries
LEGACY_NAME_OF = {"precip_annual": "Rainfall", "elevation": "Altitude_r", "temp_mean_annual": "temp_mean_annual",
                  "precip_seasonality": "precip_seasonality", "slope": "slope", "soil_clay": "soil_clay",
                  "lgp_days": "lgp_days", "soil_ph": "soil_ph", "soil_soc": "soil_soc"}
REPORTED_OF = {"precip_annual": "ctx_reported_rain_mm", "elevation": "ctx_reported_altitude_m", "slope": "ctx_reported_slope_pct"}
CATEGORICALS = ("belt", "koppen", "land_cover", "crop_group", "practice_family", "outcome_id", "objective_group",
                "source", "quality_flag", "loc_precision")
QUALITY_WEIGHT = {"High": 1.0, "Medium": 0.8, "Low": 0.6, "NR": 0.6}
UNKNOWN = "<unknown>"


@dataclass(frozen=True)
class DataConfig:
    """What the model sees (every ablation of brief Part 3 is one of these switches)."""

    context: str = "all"            # "all": the 27 release layers; "legacy11": the 9 legacy numeric layers
    use_belt: bool = True
    use_koppen: bool = True
    use_components: bool = True
    use_practice_te: bool = True
    include_hab: bool = True
    include_country_precision: bool = True
    weight_scheme: str = "inverse_variance"   # | "quality"
    te_smoothing: float = 10.0

    @property
    def layers(self) -> tuple[str, ...]:
        return CONTEXT_LAYERS if self.context == "all" else LEGACY_LAYERS


# ----------------------------------------------------------------- rows
def training_rows(store: pd.DataFrame, mask: Mask, cfg: DataConfig, outcome_group: Mapping[str, str]) -> pd.DataFrame:
    """Eligible store rows after the mask and the configuration's exclusions, with ``y``,
    ``group``, ``site``, ``objective_group`` and ``ctx_missing``."""
    rows = mask.filter_rows(hq.eligible_rows(store)).copy()
    if not cfg.include_hab:
        rows = rows[rows["source"] != "HAB"]
    if not cfg.include_country_precision:
        rows = rows[rows["loc_precision"].isin(["site", "district", "exact"])]
    rows["y"] = rows["lrr"].astype(float) * rows["direction"].astype(float)
    rows["group"] = [group_key(d, s) for d, s in zip(rows["doi"], rows["study_id"])]
    rows["site"] = [hq.site_key(a, b, n) for a, b, n in zip(rows["lat"], rows["lon"], rows["site_name"])]
    rows["objective_group"] = rows["outcome_id"].map(lambda o: outcome_group.get(str(o), "other"))
    rows["ctx_missing"] = rows["ctx_release"].isna() if "ctx_release" in rows.columns else True
    return rows


def row_weights(rows: pd.DataFrame, scheme: str) -> np.ndarray:
    """Sample weights under one of the two schemes (positive, mean 1)."""
    if scheme == "quality":
        w = rows["quality_flag"].map(lambda q: QUALITY_WEIGHT.get(str(q), 0.6)).to_numpy(float)
    else:
        w = pd.to_numeric(rows["weight"], errors="coerce").to_numpy(float)
        var = pd.to_numeric(rows["var_lrr"], errors="coerce").to_numpy(float)
        has = np.isfinite(var) & (var > 0)
        if has.any():
            cap = float(np.nanpercentile(w[has], 99))
            w = np.where(has, np.minimum(w, cap), w)
        w = np.where(np.isfinite(w) & (w > 0), w, np.nanmedian(w[np.isfinite(w) & (w > 0)]) if np.isfinite(w).any() else 1.0)
    return w / w.mean() if w.size and w.mean() > 0 else np.ones(len(rows))


def inner_folds(groups: pd.Series, n_folds: int = 3) -> np.ndarray:
    """Study-grouped inner fold id per row (0..n_folds-1), deterministic (P7 greedy balance)."""
    sizes = {str(g): int(n) for g, n in groups.value_counts().items()}
    assignment = assign_units(sizes, n_folds=n_folds, n_reps=1)
    return groups.astype(str).map(lambda g: assignment[g][0]).to_numpy(int)


def pooled_items(rows: pd.DataFrame) -> pd.DataFrame:
    """One row per (query key, practice): the pooled oriented effect of the training rows of a
    practice at one site/outcome/crop/comparator cell, with the first row's index for features.

    These are the training *queries* of the ranker and the sites of the matched-studies
    component (the same cell definition as the harness queries).
    """
    r = rows.copy()
    r["crop_key"] = r["crop"].map(lambda c: " ".join(str(c).split()).lower() if isinstance(c, str) and c.strip() else "")
    r["comp"] = r["comparator"].map(hq.comparator_class)
    r["_i"] = r.index
    recs = []
    keys = ["group", "site", "outcome_id", "crop_key", "comp", "practice_id"]
    for key, g in r.groupby(keys, sort=True):
        pooled, var, method = hq.pool_effects(g["lrr"].to_numpy(), g["var_lrr"].to_numpy(), g["weight"].to_numpy())
        first = g.iloc[0]
        recs.append({"qkey": "\x1f".join(str(k) for k in key[:5]), "group": key[0], "site": key[1], "outcome_id": key[2],
                     "practice_id": key[5], "y": pooled * float(first["direction"]), "var": var, "n_rows": int(len(g)),
                     "row_index": first["_i"], "study_id": str(first["study_id"]),
                     "objective_group": str(first.get("objective_group", "other"))})
    return pd.DataFrame(recs)


# ----------------------------------------------------------------- features
class FeatureEncoder:
    """Fitted on training rows only; turns rows or query candidates into one numeric matrix."""

    def __init__(self, cfg: DataConfig, outcome_group: Mapping[str, str], family_of: Mapping[str, str],
                 components_of: Mapping[str, list[str]], belt_code_of: Mapping[str, int] | None = None) -> None:
        self.cfg = cfg
        self.outcome_group = dict(outcome_group)
        self.family_of = dict(family_of)
        self.components_of = {k: list(v) for k, v in components_of.items()}
        self.belt_code_of = dict(belt_code_of or {})
        self.vocab: dict[str, dict[str, int]] = {}
        self.components: list[str] = []
        self.crop_group_of: dict[str, str] = {}
        self.te_practice: dict[str, tuple[float, int]] = {}
        self.te_practice_group: dict[tuple[str, str], tuple[float, int]] = {}
        self.global_mean = 0.0
        self.feature_names: list[str] = []
        self.kept: list[str] | None = None

    # ------------------------------------------------------------ fit
    def fit(self, rows: pd.DataFrame) -> "FeatureEncoder":
        for c in CATEGORICALS:
            vals = self._raw_cat(rows, c)
            self.vocab[c] = {v: i for i, v in enumerate(sorted(set(vals.dropna().astype(str))))}
        comps = set()
        for v in rows["practice_components"].dropna():
            comps.update(x for x in str(v).split(";") if x)
        for pid in rows["practice_id"].dropna().unique():
            self.components_of.setdefault(str(pid), [])
        for pid, v in zip(rows["practice_id"], rows["practice_components"]):
            if isinstance(v, str) and v and not self.components_of.get(str(pid)):
                self.components_of[str(pid)] = [x for x in v.split(";") if x]
        for pid, f in zip(rows["practice_id"], rows["practice_family"]):
            if isinstance(f, str) and f:
                self.family_of.setdefault(str(pid), f)
        self.components = sorted(comps | {c for v in self.components_of.values() for c in v})
        cg = rows.dropna(subset=["crop", "crop_group"])
        if len(cg):
            self.crop_group_of = {str(c).strip().lower(): str(g) for c, g in
                                  cg.groupby(cg["crop"].astype(str).str.strip().str.lower())["crop_group"].agg(lambda s: s.value_counts().index[0]).items()}
        self.global_mean = float(rows["y"].mean()) if len(rows) else 0.0
        self.te_practice, self.te_practice_group = self._te_tables(rows)
        self.feature_names = self._all_feature_names()
        return self

    @staticmethod
    def _raw_cat(rows: pd.DataFrame, c: str) -> pd.Series:
        if c == "belt":
            return rows["ctx_aez_belt"].map(lambda v: str(int(v)) if pd.notna(v) else None) if "ctx_aez_belt" in rows else pd.Series([None] * len(rows), index=rows.index)
        if c == "koppen":
            return rows["ctx_koppen_class"].map(lambda v: str(int(v)) if pd.notna(v) else None) if "ctx_koppen_class" in rows else pd.Series([None] * len(rows), index=rows.index)
        if c == "land_cover":
            return rows["ctx_land_cover"].map(lambda v: str(int(v)) if pd.notna(v) else None) if "ctx_land_cover" in rows else pd.Series([None] * len(rows), index=rows.index)
        return rows[c].astype(object).where(rows[c].notna(), None)

    def _te_tables(self, rows: pd.DataFrame) -> tuple[dict[str, tuple[float, int]], dict[tuple[str, str], tuple[float, int]]]:
        tp = {str(p): (float(g["y"].mean()), int(len(g))) for p, g in rows.groupby("practice_id")}
        tpg = {(str(p), str(o)): (float(g["y"].mean()), int(len(g))) for (p, o), g in rows.groupby(["practice_id", "objective_group"])}
        return tp, tpg

    def _all_feature_names(self) -> list[str]:
        names = [f"ctx_{lid}" for lid in self.cfg.layers] + ["ctx_missing"]
        for c in CATEGORICALS:
            if c == "belt" and not self.cfg.use_belt:
                continue
            if c == "koppen" and not self.cfg.use_koppen:
                continue
            names.append(f"cat_{c}")
        names.append("duration_years")
        if self.cfg.use_practice_te:
            names += ["te_practice_mean", "te_practice_n", "te_practice_group_mean", "te_practice_group_n"]
        if self.cfg.use_components:
            names += [f"comp_{c}" for c in self.components]
        return names

    @property
    def categorical_columns(self) -> list[str]:
        return [n for n in self.active_names if n.startswith("cat_")]

    @property
    def active_names(self) -> list[str]:
        return [n for n in self.feature_names if self.kept is None or n in self.kept]

    @property
    def categorical_index(self) -> list[int]:
        return [i for i, n in enumerate(self.active_names) if n.startswith("cat_")]

    def feature_group(self, name: str) -> str:
        """The selection unit a column belongs to (one per layer; blocks for components and TE)."""
        if name.startswith("comp_"):
            return "components"
        if name.startswith("te_"):
            return "practice_te"
        return name

    # ------------------------------------------------------------ transform
    def _code(self, c: str, value: Any) -> int:
        vocab = self.vocab.get(c, {})
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return len(vocab)
        return vocab.get(str(value), len(vocab))

    def _te(self, pid: str, group: str, tp: dict, tpg: dict) -> tuple[float, float, float, float]:
        m = self.cfg.te_smoothing
        pm, pn = tp.get(pid, (self.global_mean, 0))
        gm, gn = tpg.get((pid, group), (self.global_mean, 0))
        return ((pn * pm + m * self.global_mean) / (pn + m), math.log1p(pn),
                (gn * gm + m * pm) / (gn + m), math.log1p(gn))

    def transform_rows(self, rows: pd.DataFrame, oof_folds: np.ndarray | None = None) -> pd.DataFrame:
        """Feature matrix of training rows; with ``oof_folds`` the target encoding of every row
        comes from the other inner folds (never from the row's own fold)."""
        layers = self.cfg.layers
        out: dict[str, Any] = {}
        for lid in layers:
            col = f"ctx_{lid}"
            v = pd.to_numeric(rows[col], errors="coerce") if col in rows.columns else pd.Series(np.nan, index=rows.index)
            if lid in REPORTED_OF and REPORTED_OF[lid] in rows.columns:
                v = v.where(v.notna(), pd.to_numeric(rows[REPORTED_OF[lid]], errors="coerce"))
            out[col] = np.log1p(np.maximum(v.to_numpy(float), 0.0)) if lid in LOG_LAYERS else v.to_numpy(float)
        out["ctx_missing"] = rows["ctx_missing"].astype(float).to_numpy() if "ctx_missing" in rows else np.ones(len(rows))
        for c in CATEGORICALS:
            if (c == "belt" and not self.cfg.use_belt) or (c == "koppen" and not self.cfg.use_koppen):
                continue
            raw = self._raw_cat(rows, c)
            out[f"cat_{c}"] = np.array([self._code(c, v) for v in raw], dtype=float)
        out["duration_years"] = pd.to_numeric(rows["duration_years"], errors="coerce").to_numpy(float) if "duration_years" in rows else np.full(len(rows), np.nan)
        if self.cfg.use_practice_te:
            te = np.zeros((len(rows), 4))
            pids = rows["practice_id"].astype(str).to_numpy()
            groups = rows["objective_group"].astype(str).to_numpy()
            if oof_folds is None:
                for i, (p, g) in enumerate(zip(pids, groups)):
                    te[i] = self._te(p, g, self.te_practice, self.te_practice_group)
            else:
                for f in np.unique(oof_folds):
                    tp, tpg = self._te_tables(rows[oof_folds != f])
                    for i in np.flatnonzero(oof_folds == f):
                        te[i] = self._te(pids[i], groups[i], tp, tpg)
            for j, name in enumerate(("te_practice_mean", "te_practice_n", "te_practice_group_mean", "te_practice_group_n")):
                out[name] = te[:, j]
        if self.cfg.use_components:
            comp_index = {c: i for i, c in enumerate(self.components)}
            mh = np.zeros((len(rows), len(self.components)))
            for i, (pid, v) in enumerate(zip(rows["practice_id"].astype(str), rows["practice_components"])):
                comps = [x for x in str(v).split(";") if x] if isinstance(v, str) and v else self.components_of.get(pid, [])
                for c in comps:
                    if c in comp_index:
                        mh[i, comp_index[c]] = 1.0
            for c, i in comp_index.items():
                out[f"comp_{c}"] = mh[:, i]
        X = pd.DataFrame(out, index=rows.index)
        return X[self.active_names]

    def query_context(self, context: Mapping[str, Any]) -> dict[str, Any]:
        """Normalise a request context (release ``ctx_*`` keys, reported fields or the legacy
        serving names) into the row-like keys the encoder reads."""
        ctx: dict[str, Any] = {}
        for lid in CONTEXT_LAYERS:
            v = context.get(f"ctx_{lid}")
            if v is None and lid in LEGACY_NAME_OF:
                v = context.get(LEGACY_NAME_OF[lid])
            ctx[f"ctx_{lid}"] = v
        belt = context.get("ctx_aez_belt")
        if belt is None and isinstance(context.get("aez_belt"), str):
            belt = self.belt_code_of.get(context["aez_belt"])
        ctx["ctx_aez_belt"] = belt
        ctx["ctx_koppen_class"] = context.get("ctx_koppen_class")
        lc = context.get("ctx_land_cover", context.get("land_cover"))
        ctx["ctx_land_cover"] = lc
        ctx["ctx_release"] = context.get("release") if context.get("ctx_precip_annual") is not None else None
        return ctx

    def transform_candidates(self, context: Mapping[str, Any], candidates: list[str], outcome_id: str,
                             objective_group: str | None, crop: str | None,
                             attrs: Mapping[str, Any] | None = None) -> pd.DataFrame:
        """Feature rows for the candidates of one query (nothing from the query's own rows)."""
        ctx = self.query_context(context)
        attrs = attrs or {}
        group = objective_group or self.outcome_group.get(outcome_id, "other")
        crop_key = str(crop).strip().lower() if isinstance(crop, str) and crop.strip() else ""
        source = str(attrs.get("sources") or "").split(";")[0] or None
        # missing context = only the reported trio (rainfall, altitude, slope) is known, as for the
        # country-precision training rows; a release or a legacy-dataset context is not missing
        missing = all(ctx.get(f"ctx_{lid}") is None for lid in CONTEXT_LAYERS if lid not in REPORTED_OF)
        rows = []
        for pid in candidates:
            comps = self.components_of.get(pid, [])
            rows.append({**ctx, "practice_id": pid, "practice_components": ";".join(comps),
                         "practice_family": self.family_of.get(pid), "outcome_id": outcome_id, "objective_group": group,
                         "crop_group": self.crop_group_of.get(crop_key), "source": source,
                         "quality_flag": attrs.get("quality_flag"), "loc_precision": attrs.get("loc_precision"),
                         "duration_years": np.nan, "ctx_missing": missing})
        frame = pd.DataFrame(rows, index=pd.RangeIndex(len(rows)))
        return self.transform_rows(frame)
