"""Methodology 1 v2 assembled: nested fit, fallback chain, calibrated intervals (E5 Part 2).

:meth:`M1Engine.fit` receives the store rows and the fold's :class:`Mask` and learns
everything inside that outer training fold:

1. training rows, features and weights (:mod:`model.m1.data`); inner study-grouped folds;
2. the regressor's hyperparameters (inner grid) and the kept feature groups (grouped
   permutation importance), both on the inner folds;
3. inner out-of-fold predictions of every component for the training queries (regressor,
   ranker, matched studies, prior), which fit the stacker (ridge per availability pattern
   or rank averaging, decided on the inner folds) and the conformal quantile;
4. the final components on every training row.

:meth:`M1Engine.rank` scores the candidates of a query from its context alone: component
scores, the stacker's combination and lead source, the effect estimate with the
conformal 80 % interval, and the citations (matched study ids, else the nearest training
groups for the outcome). Every candidate is answered; nothing abstains.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field, replace
from typing import Any, Mapping

import numpy as np
import pandas as pd

from model.harness.mask import Mask
from model.m1 import conformal as cf
from model.m1 import data as md
from model.m1 import regressor as rg
from model.m1 import select as fs
from model.m1 import stack as st
from model.m1.matched import MatchedStudies
from model.m1.prior import ShrunkenPrior
from model.m1.ranker import make_ranker


@dataclass(frozen=True)
class M1Config:
    data: md.DataConfig = field(default_factory=md.DataConfig)
    use_regressor: bool = True
    use_ranker: bool = True
    use_matched: bool = True
    stacker: str = "auto"              # auto | ridge | rank_avg
    tune: bool = True                  # inner grid for the regressor and the matched k
    select: bool = True                # grouped permutation feature selection
    inner_folds: int = 3
    prefer_lightgbm: bool = True
    k_min: int = 3
    regressor_params: dict[str, Any] | None = None
    #: serving (E5 Part 1): a fixed feature set (the features stable in >= 4 of 5 outer folds);
    #: when set, selection is skipped and only these features are used
    fixed_features: tuple[str, ...] | None = None
    matched_k: int = 10
    matched_power: float = 2.0
    name: str = "m1_v2"

    @property
    def components_used(self) -> list[str]:
        return [c for c, on in (("regressor", self.use_regressor), ("ranker", self.use_ranker),
                                ("matched_studies", self.use_matched)) if on] + ["prior"]


class M1Engine:
    def __init__(self, cfg: M1Config, outcome_group: Mapping[str, str], family_of: Mapping[str, str],
                 components_of: Mapping[str, list[str]], belt_code_of: Mapping[str, int] | None = None) -> None:
        self.cfg = cfg
        self.outcome_group = dict(outcome_group)
        self.family_of = dict(family_of)
        self.components_of = {k: list(v) for k, v in components_of.items()}
        self.belt_code_of = dict(belt_code_of or {})
        self.encoder: md.FeatureEncoder | None = None
        self.regressor: rg.Regressor | None = None
        self.ranker: Any = None
        self.matched: MatchedStudies | None = None
        self.prior: ShrunkenPrior | None = None
        self.stacker: st.Stacker | None = None
        self.calibrator = cf.ConformalCalibrator()
        self.summary: dict[str, Any] = {}
        self.n_train = 0

    # ------------------------------------------------------------ fit
    def fit(self, store: pd.DataFrame, mask: Mask) -> dict[str, Any]:
        t0 = time.time()
        cfg = self.cfg
        rows = md.training_rows(store, mask, cfg.data, self.outcome_group)
        if rows.empty:
            raise ValueError("no training rows after the mask")
        self.n_train = int(len(rows))
        fold = md.inner_folds(rows["group"], cfg.inner_folds)
        enc = md.FeatureEncoder(cfg.data, self.outcome_group, self.family_of, self.components_of, self.belt_code_of).fit(rows)
        self.encoder = enc
        X_oof = enc.transform_rows(rows, oof_folds=fold)
        y = rows["y"].to_numpy(float)
        w = md.row_weights(rows, cfg.data.weight_scheme)
        items = md.pooled_items(rows)
        fold_of_item = fold[rows.index.get_indexer(items["row_index"])]
        summary: dict[str, Any] = {"n_rows": self.n_train, "n_groups": int(rows["group"].nunique()),
                                   "n_items": int(len(items)), "n_training_queries": int(items.groupby("qkey").size().ge(2).sum()),
                                   "inner_folds": cfg.inner_folds, "weights": cfg.data.weight_scheme,
                                   "components": cfg.components_used}
        # --- 1. inner tuning and feature selection (regressor features)
        params = dict(cfg.regressor_params or rg.DEFAULT_PARAMS)
        if cfg.use_regressor and cfg.tune:
            params, table = rg.tune(X_oof, y, w, items, fold, enc.categorical_index)
            summary["regressor_grid"] = table
        summary["regressor_params"] = params
        if cfg.fixed_features is not None:
            fixed = set(cfg.fixed_features)
            enc.kept = [n for n in X_oof.columns if n in fixed]
            X_oof = X_oof[enc.kept]
            summary["feature_selection"] = "fixed (stable set)"
        elif cfg.use_regressor and cfg.select:
            kept, table = fs.select_features(enc, X_oof, y, w, items, fold, params)
            enc.kept = kept
            X_oof = X_oof[kept]
            summary["feature_selection"] = table
        summary["features"] = list(enc.active_names)
        cat_idx = enc.categorical_index
        # --- 2. inner out-of-fold component predictions of the training queries
        oof = items[["qkey", "y", "practice_id", "outcome_id", "objective_group", "row_index"]].copy()
        for c in st.COMPONENTS:
            oof[c] = np.nan
        oof["spread"], oof["d_nearest"] = np.nan, np.nan
        matched_tuned = False
        for f in np.unique(fold):
            tr_rows, te_items = fold != f, fold_of_item == f
            if not te_items.any():
                continue
            it_tr, it_te = items[fold_of_item != f], items[te_items]
            Xi = X_oof.loc[it_te["row_index"]]
            if cfg.use_regressor:
                reg = rg.Regressor(params, cat_idx).fit(X_oof[tr_rows], y[tr_rows], w[tr_rows])
                oof.loc[te_items, "reg"] = reg.predict(Xi)
            if cfg.use_ranker:
                rk = make_ranker(prefer_lightgbm=cfg.prefer_lightgbm).fit(X_oof, it_tr)
                oof.loc[te_items, "rank"] = rk.predict(Xi)
            if cfg.use_matched:
                m = MatchedStudies(cfg.matched_k, cfg.matched_power, cfg.k_min).fit(rows, it_tr)
                if cfg.tune and not matched_tuned:
                    # tuned once, on the inner folds of the first fold's training items
                    sub_fold = fold_of_item[fold_of_item != f]
                    sub_fold = md.inner_folds(it_tr["group"], cfg.inner_folds) if len(np.unique(sub_fold)) < 2 else sub_fold
                    k, power, table = m.tune(rows, it_tr, sub_fold)
                    self.cfg = replace(cfg, matched_k=k, matched_power=power)
                    cfg = self.cfg
                    summary["matched_grid"] = table
                    summary["matched_k"], summary["matched_power"] = k, power
                    matched_tuned = True
                    m.k, m.power = k, power
                for i in np.flatnonzero(te_items):
                    it = items.iloc[i]
                    ctx = self._ctx_of_row(rows.loc[it["row_index"]])
                    e = m.estimate(ctx, it["practice_id"], it["outcome_id"], it["objective_group"])
                    if e is not None:
                        oof.iloc[i, oof.columns.get_loc("matched")] = e.est
                        oof.iloc[i, oof.columns.get_loc("matched_prec")] = -np.log(max(e.se, 1e-6))
                        oof.iloc[i, oof.columns.get_loc("spread")] = e.spread
                        oof.iloc[i, oof.columns.get_loc("d_nearest")] = e.d_nearest
            pr = ShrunkenPrior(self.family_of, self.components_of).fit(rows[tr_rows])
            oof.loc[te_items, "prior"] = [pr.estimate(p, g)["est"] for p, g in zip(it_te["practice_id"], it_te["objective_group"])]
        # --- 3. stacker and conformal on the inner out-of-fold predictions
        self.stacker = st.Stacker(cfg.stacker).fit(oof)
        summary["stacker"] = self.stacker.summary
        est_oof = self._effect(oof)
        self.calibrator.fallback_spread = float(np.nanmedian(oof["spread"])) if np.isfinite(oof["spread"]).any() else 0.3
        diff = np.array([cf.difficulty(s, d, self.calibrator.fallback_spread) for s, d in zip(oof["spread"], oof["d_nearest"])])
        self.calibrator.fit(oof["y"].to_numpy(float) - est_oof, diff)
        summary["conformal"] = self.calibrator.summary()
        # --- 4. final components on every training row
        X_full = enc.transform_rows(rows)
        self.regressor = rg.Regressor(params, cat_idx).fit(X_full, y, w) if cfg.use_regressor else None
        self.ranker = make_ranker(prefer_lightgbm=cfg.prefer_lightgbm).fit(X_full, items) if cfg.use_ranker else None
        self.matched = MatchedStudies(cfg.matched_k, cfg.matched_power, cfg.k_min).fit(rows, items) if cfg.use_matched else None
        self.prior = ShrunkenPrior(self.family_of, self.components_of).fit(rows)
        if self.ranker is not None:
            summary["ranker"] = {"kind": self.ranker.name, "n_queries": self.ranker.n_queries, "n_items": self.ranker.n_items,
                                 **({"n_pairs": self.ranker.n_pairs} if hasattr(self.ranker, "n_pairs") else {})}
        summary["prior"] = {"kappa": self.prior.kappa, "sigma2": self.prior.sigma2, "tau2": self.prior.tau2}
        summary["fit_seconds"] = round(time.time() - t0, 1)
        self.summary = summary
        return summary

    @staticmethod
    def _ctx_of_row(row: pd.Series) -> dict[str, Any]:
        ctx = {k: (None if pd.isna(v) else float(v)) for k, v in row.items() if isinstance(k, str) and k.startswith("ctx_") and k != "ctx_release" and not k.startswith("ctx_reported_")}
        for col, feat in (("ctx_reported_rain_mm", "Rainfall"), ("ctx_reported_altitude_m", "Altitude_r"), ("ctx_reported_slope_pct", "slope")):
            if col in row.index and pd.notna(row[col]):
                ctx[feat] = float(row[col])
        return ctx

    def _effect(self, frame: pd.DataFrame) -> np.ndarray:
        """The effect estimate on the ``y`` scale: the ridge output when the ridge was chosen,
        else the first available of regressor, matched studies and prior."""
        assert self.stacker is not None
        if self.stacker.chosen == "ridge":
            return self.stacker._ridge_scores(frame)
        out = frame["prior"].to_numpy(float).copy()
        for c in ("matched", "reg"):
            v = frame[c].to_numpy(float)
            out = np.where(np.isfinite(v), v, out)
        return out

    # ------------------------------------------------------------ rank
    def rank(self, context: Mapping[str, Any], candidates: list[str], outcome_id: str, objective_group: str | None,
             crop: str | None, attrs: Mapping[str, Any] | None = None, qkey: str = "q") -> list[dict[str, Any]]:
        assert self.encoder is not None and self.prior is not None and self.stacker is not None, "fit first"
        cfg = self.cfg
        group = objective_group or self.outcome_group.get(outcome_id, "other")
        Xc = self.encoder.transform_candidates(context, candidates, outcome_id, group, crop, attrs)
        frame = pd.DataFrame({"qkey": qkey, "practice_id": candidates})
        for c in st.COMPONENTS:
            frame[c] = np.nan
        frame["spread"], frame["d_nearest"] = np.nan, np.nan
        if self.regressor is not None:
            frame["reg"] = self.regressor.predict(Xc)
        if self.ranker is not None:
            frame["rank"] = self.ranker.predict(Xc)
        ctx = self.encoder.query_context(context)
        cites: list[list[str]] = []
        for i, pid in enumerate(candidates):
            e = self.matched.estimate(ctx, pid, outcome_id, group) if self.matched is not None else None
            if e is not None:
                frame.loc[i, ["matched", "matched_prec", "spread", "d_nearest"]] = [e.est, -np.log(max(e.se, 1e-6)), e.spread, e.d_nearest]
                cites.append(e.study_ids)
            else:
                cites.append([])
            frame.loc[i, "prior"] = self.prior.estimate(pid, group)["est"]
        scores, leads = self.stacker.predict(frame)
        est = self._effect(frame)
        out = []
        for i, pid in enumerate(candidates):
            d = cf.difficulty(frame.loc[i, "spread"], frame.loc[i, "d_nearest"], self.calibrator.fallback_spread)
            lo, hi = self.calibrator.interval(float(est[i]), d)
            citations = cites[i] or (self._nearest_groups(ctx, outcome_id) if self.matched is not None else [])
            out.append({"practice_id": pid, "score": float(scores[i]), "est_lrr": float(est[i]),
                        "lo": None if not np.isfinite(lo) else float(lo), "hi": None if not np.isfinite(hi) else float(hi),
                        "lead_source": leads[i], "citations": citations,
                        "components": {c: (None if not np.isfinite(frame.loc[i, c]) else float(frame.loc[i, c])) for c in st.COMPONENTS}})
        return out

    def _nearest_groups(self, ctx: dict[str, Any], outcome_id: str, k: int = 3) -> list[str]:
        """Study ids of the nearest training sites for the outcome (any practice), for citations."""
        m = self.matched
        assert m is not None
        idx = np.flatnonzero((m.sites["outcome_id"] == outcome_id).to_numpy()) if len(m.sites) else np.array([], int)
        if len(idx) == 0:
            return []
        d = m._distances(ctx, idx)
        order = np.argsort(d, kind="stable")
        out: list[str] = []
        for j in order:
            if not np.isfinite(d[j]):
                break
            sid = str(m.sites["study_id"].iloc[idx[j]])
            if sid not in out:
                out.append(sid)
            if len(out) >= k:
                break
        return out
