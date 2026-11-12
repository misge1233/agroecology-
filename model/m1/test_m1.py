"""Methodology 1 v2 (E5): components on synthetic data, the nested-leakage canary, full
coverage, determinism, and the by-hand fixtures of the prior, pooling, conformal and stacker."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from model.engines.base import RankRequest
from model.engines.m1_v2 import VARIANTS, M1V2Engine
from model.harness.mask import Mask
from model.m1 import conformal as cf
from model.m1 import data as md
from model.m1 import ranker as rk
from model.m1 import select as fs
from model.m1 import stack as st
from model.m1.engine import M1Config, M1Engine
from model.m1.matched import dersimonian_laird
from model.m1.prior import ShrunkenPrior
from pipelines.evidence import schema

OUTCOME_GROUP = {"YIELD": "productivity", "SOIL_LOSS": "water"}
FAMILY = {"A": "F1", "B": "F1", "C": "F2", "D": "F2", "X": "F1"}
COMPONENTS = {"A": ["Mulch"], "B": ["Mulch", "Manure"], "C": ["Bund"], "D": ["Bund", "Trees"], "X": ["Mulch"]}
PRACTICE_EFFECT = {"A": 0.1, "B": 0.4, "C": 0.2, "D": 0.6}


def synthetic_store(n_groups: int = 40, seed: int = 0, canary: bool = False) -> pd.DataFrame:
    """Groups at sites along a rainfall gradient; practice effects shift with rainfall so the
    context carries signal; every group compares three or four practices for yield."""
    rng = np.random.default_rng(seed)
    rows = []
    for g in range(n_groups):
        rain = 400 + 1200 * g / n_groups
        lat, lon = 6.0 + 8 * g / n_groups, 36.0 + (g % 3) * 2.0
        practices = ["A", "B", "C"] + (["D"] if g % 2 else [])
        for p in practices:
            eff = PRACTICE_EFFECT[p] + (0.3 if (p in ("A", "B") and rain > 1000) else 0.0) + rng.normal(0, 0.05)
            for i in range(2):
                lrr = eff + rng.normal(0, 0.08)
                rows.append({"row_id": f"ERA:ERA_G{g:02d}:{p}{i}", "source": "HAB" if g % 7 == 0 else "ERA",
                             "study_id": f"ERA_G{g:02d}", "doi": f"10.1/g{g:02d}", "citation": "c", "year": 2015,
                             "country": "ET", "lat": lat, "lon": lon, "loc_precision": "site", "loc_method": "reported",
                             "site_name": None, "practice_id": p, "practice_raw": p, "practice_family": FAMILY[p],
                             "practice_components": ";".join(COMPONENTS[p]), "comparator": "control", "crop": "Maize",
                             "crop_group": "Cereal", "outcome_id": "YIELD", "outcome_raw": "y", "direction": 1,
                             "direction_reviewed": True, "lrr": lrr, "var_lrr": 0.01 if i == 0 else None, "weight": 100.0 if i == 0 else 66.0,
                             "quality_flag": "NR", "licence": "l", "duration_years": 1.0, "ctx_release": "ET/2026.1",
                             "ctx_precip_annual": rain, "ctx_elevation": 2500 - rain, "ctx_temp_mean_annual": 18.0,
                             "ctx_precip_seasonality": 80.0, "ctx_slope": 5.0 + g % 5, "ctx_soil_clay": 30.0,
                             "ctx_lgp_days": 150 + rain / 10, "ctx_soil_ph": 6.0, "ctx_soil_soc": 20.0, "ctx_land_cover": 40,
                             "ctx_aez_belt": 7 if rain > 900 else 6, "ctx_koppen_class": 12, "ctx_twi": 8.0,
                             "ctx_aridity_index": rain / 1800})
    if canary:
        for i in range(3):
            rows.append({**rows[0], "row_id": f"ERA:ERA_CANARY:{i}", "study_id": "ERA_CANARY", "doi": "10.1/canary",
                         "practice_id": "X", "practice_raw": "X", "practice_family": "F1", "practice_components": "Mulch",
                         "lrr": 5.0, "var_lrr": 0.001, "weight": 1000.0, "ctx_precip_annual": 800.0})
    return schema.coerce(pd.DataFrame(rows))


def _req(qid, candidates, context, outcome="YIELD", crop="maize"):
    return RankRequest(query_id=qid, context=context, challenge_ids=[], outcome_id=outcome, candidates=candidates,
                       crop=crop, user_attrs={"sources": "ERA", "loc_precision": "site"}, mask=Mask.empty(), direction=1,
                       objective_group=OUTCOME_GROUP[outcome])


FAST = M1Config(tune=False, select=False, inner_folds=3)


def _engine(cfg: M1Config = FAST) -> M1V2Engine:
    return M1V2Engine(cfg, OUTCOME_GROUP, FAMILY, COMPONENTS, {"Moist Dega": 7, "Wet Dega": 6})


# ----------------------------------------------------------------- end to end
def test_engine_answers_every_candidate_and_recovers_the_ordering():
    store = synthetic_store()
    eng = _engine()
    eng.fit(store, Mask.from_groups(["10.1/g00", "10.1/g01"], store))
    assert eng.engine is not None and eng.engine.n_train == len(store) - 14  # the two held-out groups: 3 + 4 practices x 2
    hits = 0
    for g in (0, 1):
        rain = 400 + 1200 * g / 40
        ctx = {"ctx_precip_annual": rain, "ctx_elevation": 2500 - rain, "ctx_temp_mean_annual": 18.0, "ctx_precip_seasonality": 80.0,
               "ctx_slope": 5.0, "ctx_soil_clay": 30.0, "ctx_lgp_days": 150 + rain / 10, "ctx_soil_ph": 6.0, "ctx_soil_soc": 20.0,
               "ctx_land_cover": 40, "ctx_aez_belt": 6, "ctx_koppen_class": 12, "ctx_twi": 8.0, "ctx_aridity_index": rain / 1800,
               "release": "ET/2026.1"}
        items = eng.rank(_req(f"q{g}", ["C", "A", "B", "D", "X"], ctx))
        assert [i.practice_id for i in items] == ["C", "A", "B", "D", "X"] and not any(i.abstain for i in items)
        assert all(i.est_lrr is not None and i.lo is not None and i.hi is not None and i.lo <= i.est_lrr <= i.hi for i in items)
        assert all(i.lead_source in ("model", "matched_studies", "prior") for i in items)
        by = {i.practice_id: i for i in items}
        assert by["X"].lead_source == "prior" and by["X"].citations  # unknown practice: the prior answers, nearest groups cited
        hits += max(items[:4], key=lambda i: i.score).practice_id == "D"
    assert hits == 2
    p = eng.params()
    assert p["last_fit"]["stacker_chosen"] in ("ridge", "rank_avg") and p["last_fit"]["conformal_q"] > 0
    s = eng.fit_summaries[-1]
    assert s["n_training_queries"] >= 30 and s["ranker"]["n_queries"] >= 30 and s["components"] == ["regressor", "ranker", "matched_studies", "prior"]


def test_fit_is_deterministic():
    store = synthetic_store()
    ctx = {"ctx_precip_annual": 900.0, "ctx_elevation": 1600.0, "ctx_aez_belt": 6, "release": "ET/2026.1"}
    outs = []
    for _ in range(2):
        eng = _engine()
        eng.fit(store, Mask.from_groups(["10.1/g05"], store))
        outs.append([(i.practice_id, round(i.score, 10), round(i.est_lrr, 10), round(i.lo, 10)) for i in eng.rank(_req("q", ["A", "B", "C"], ctx))])
    assert outs[0] == outs[1]


def test_nested_canary_never_influences_learned_quantities():
    """A held-out canary group with an absurd effect must not change the stacker weights,
    the conformal quantile, the selected features or the prior: the mask governs every fit."""
    clean, with_canary = synthetic_store(), synthetic_store(canary=True)
    mask = Mask.from_groups(["10.1/canary", "10.1/g03"], with_canary)
    cfg = M1Config(tune=False, select=True, inner_folds=3)
    a, b = _engine(cfg), _engine(cfg)
    a.fit(clean, Mask.from_groups(["10.1/g03"], clean))
    b.fit(with_canary, mask)
    sa, sb = a.fit_summaries[-1], b.fit_summaries[-1]
    assert sa["n_rows"] == sb["n_rows"] and sa["features"] == sb["features"]
    assert sa["stacker"]["chosen"] == sb["stacker"]["chosen"] and sa["stacker"]["patterns"] == sb["stacker"]["patterns"]
    assert sa["conformal"]["q"] == sb["conformal"]["q"] and sa["prior"] == sb["prior"]
    ctx = {"ctx_precip_annual": 800.0, "ctx_elevation": 1700.0, "ctx_aez_belt": 6, "release": "ET/2026.1"}
    ra = {i.practice_id: i for i in a.rank(_req("q", ["A", "X"], ctx))}
    rb = {i.practice_id: i for i in b.rank(_req("q", ["A", "X"], ctx))}
    assert ra["X"].est_lrr == pytest.approx(rb["X"].est_lrr) and ra["A"].score == pytest.approx(rb["A"].score)
    assert abs(rb["X"].est_lrr) < 2.0  # nothing of the +5 canary leaked into the prior
    # the unmasked canary does change things (so the test can tell)
    c = _engine(cfg)
    c.fit(with_canary, Mask.from_groups(["10.1/g03"], with_canary))
    assert {i.practice_id: i for i in c.rank(_req("q", ["A", "X"], ctx))}["X"].est_lrr > 1.0


def test_variants_cover_the_brief():
    assert {"m1_v2", "m1_regressor", "m1_ranker", "m1_matched", "m1_prior", "m1_nobelt", "m1_legacy11", "m1_nohab",
            "m1_nocountry", "m1_wquality", "m1_noranker", "m1_nomatched", "m1_rankavg"} <= set(VARIANTS)
    store = synthetic_store(20)
    for name in ("m1_prior", "m1_matched", "m1_legacy11"):
        eng = M1V2Engine(VARIANTS[name], OUTCOME_GROUP, FAMILY, COMPONENTS)
        eng.fit(store, Mask.from_groups(["10.1/g02"], store))
        items = eng.rank(_req("q", ["A", "B"], {"Rainfall": 700.0, "Altitude_r": 1800.0, "slope": 4.0, "aez_belt": "Moist Dega"}))
        assert len(items) == 2 and not any(i.abstain for i in items) and eng.name == name


# ----------------------------------------------------------------- by-hand fixtures
def test_dersimonian_laird_by_hand():
    y, v = np.array([0.2, 0.6]), np.array([0.01, 0.01])
    est, se, tau2 = dersimonian_laird(y, v, np.ones(2))
    # fixed-effect mean 0.4; Q = 100*(0.04+0.04) = 8; C = 200 - 20000/200 = 100; tau2 = (8-1)/100 = 0.07
    assert est == pytest.approx(0.4) and tau2 == pytest.approx(0.07) and se == pytest.approx(math.sqrt(1 / (2 / 0.08)))
    est2, _, _ = dersimonian_laird(y, v, np.array([1.0, 0.0]))
    assert est2 == pytest.approx(0.2)  # a zero decay weight removes the second site


def test_prior_shrinks_toward_components_then_family():
    rows = pd.DataFrame({"y": [0.5, 0.7, 0.6, 0.1, 0.2, 0.15, 1.0], "practice_id": ["A", "A", "A", "B", "B", "B", "C"],
                         "objective_group": ["g"] * 7, "practice_family": ["F1"] * 6 + ["F2"],
                         "practice_components": ["Mulch"] * 3 + ["Bund"] * 3 + ["Mulch;Bund"]})
    pr = ShrunkenPrior().fit(rows)
    a = pr.estimate("A", "g")
    assert 0.5 < a["est"] < 0.7 and a["n"] == 3 and a["lo"] < a["est"] < a["hi"]
    unseen_mulch = pr.estimate("Z", "g") if pr.components_of.setdefault("Z", ["Mulch"]) else None
    assert unseen_mulch["prior_level"] == "component" and 0.5 < unseen_mulch["est"] < 0.75  # mulch mean incl. C
    pr.components_of["W"] = []
    pr.family_of["W"] = "F2"
    assert pr.estimate("W", "g")["prior_level"] == "family" and pr.estimate("W", "g")["est"] == pytest.approx(1.0)
    assert pr.estimate("Q", "g")["prior_level"] == "grand"


def test_conformal_quantile_and_difficulty():
    cal = cf.ConformalCalibrator(0.8)
    cal.fit(np.array([0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]), np.ones(10))
    assert cal.q == pytest.approx(0.9)  # ceil(11 x 0.8) = 9th of 10 sorted residuals
    lo, hi = cal.interval(0.0, 2.0)
    assert (lo, hi) == pytest.approx((-1.8, 1.8))
    assert cf.difficulty(0.2, 1.0, 0.3) == pytest.approx(0.05 + 0.2 + 0.5) and cf.difficulty(None, None, 0.3) == pytest.approx(0.05 + 0.3 + 0.5)
    empty = cf.ConformalCalibrator().fit(np.array([]), np.array([]))
    assert all(math.isnan(x) for x in empty.interval(0.0, 1.0))


def test_stacker_patterns_rank_average_and_lead_source():
    rng = np.random.default_rng(0)
    n = 300
    y = rng.normal(0, 1, n)
    oof = pd.DataFrame({"qkey": [f"q{i // 3}" for i in range(n)], "y": y, "reg": y + rng.normal(0, 0.3, n),
                        "rank": y * 2 + rng.normal(0, 1, n), "matched": np.where(rng.random(n) < 0.5, y + rng.normal(0, 0.5, n), np.nan),
                        "prior": rng.normal(0, 1, n)})
    oof["matched_prec"] = np.where(np.isfinite(oof["matched"]), 1.0, np.nan)
    s = st.Stacker("auto").fit(oof)
    assert s.chosen == "ridge" and set(s.summary["patterns"]) == {"110", "111"}
    scores, leads = s.predict(oof.iloc[:3])
    assert len(scores) == 3 and set(leads) <= {"model", "matched_studies", "prior"} and leads[0] == "model"
    ra = st.Stacker("rank_avg").fit(oof)
    scores, leads = ra.predict(oof.iloc[:3])
    assert ra.chosen == "rank_avg" and list(np.argsort(scores)) == list(np.argsort(st.rank_average(oof.iloc[:3], ["reg", "rank", "matched", "prior"])))
    # a candidate with no component but the prior
    lone = pd.DataFrame({"qkey": ["z"], "y": [0.0], "reg": [np.nan], "rank": [np.nan], "matched": [np.nan], "matched_prec": [np.nan], "prior": [0.3]})
    sc, ld = s.predict(lone)
    assert ld == ["prior"] and sc[0] == pytest.approx(0.3)


def test_ranker_relevance_and_pairwise_fallback():
    items = pd.DataFrame({"qkey": ["a", "a", "a", "b", "b"], "y": [0.1, 0.5, 0.3, 0.9, 0.2], "practice_id": list("ABCAB"), "row_index": range(5)})
    assert rk.relevance(items).tolist() == [0, 2, 1, 1, 0]
    X = pd.DataFrame({"f1": [0.0, 1.0, 0.5, 1.0, 0.0], "f2": [1.0, 1.0, 1.0, 2.0, 2.0]})
    pw = rk.PairwiseRanker({"max_iter": 20}).fit(X, items)
    assert pw.n_queries == 2 and pw.n_pairs == 4
    s = pw.predict(X.iloc[[0, 1]])
    assert len(s) == 2 and 0 <= s.min() and s.max() <= 1
    assert rk.lightgbm_available()
    lr = rk.LambdaRanker({"n_estimators": 10, "min_child_samples": 1, "num_leaves": 3}).fit(X, items)
    assert lr.n_queries == 2 and len(lr.predict(X)) == 5


def test_encoder_reads_release_reported_and_legacy_contexts():
    store = synthetic_store(8)
    rows = md.training_rows(store, Mask.empty(), md.DataConfig(), OUTCOME_GROUP)
    enc = md.FeatureEncoder(md.DataConfig(), OUTCOME_GROUP, FAMILY, COMPONENTS, {"Moist Dega": 7}).fit(rows)
    X = enc.transform_rows(rows)
    assert "ctx_precip_annual" in X and "cat_belt" in X and "comp_Mulch" in X and "te_practice_mean" in X
    oof = enc.transform_rows(rows, oof_folds=md.inner_folds(rows["group"], 3))
    assert oof.shape == X.shape and not np.allclose(oof["te_practice_mean"], X["te_practice_mean"])
    q = enc.transform_candidates({"Rainfall": 650.0, "Altitude_r": 1900.0, "aez_belt": "Moist Dega"}, ["A", "B"], "YIELD", None, "maize",
                                 {"sources": "ERA", "loc_precision": "site"})
    assert q.loc[0, "ctx_precip_annual"] == 650.0 and q.loc[0, "cat_belt"] == enc.vocab["belt"]["7"] and q.loc[1, "comp_Manure"] == 1.0
    assert q.loc[0, "ctx_missing"] == 1.0 and math.isnan(q.loc[0, "ctx_twi"])
    legacy = md.DataConfig(context="legacy11", use_koppen=False)
    enc2 = md.FeatureEncoder(legacy, OUTCOME_GROUP, FAMILY, COMPONENTS).fit(rows)
    assert "ctx_twi" not in enc2.transform_rows(rows).columns and "cat_koppen" not in enc2.transform_rows(rows).columns
    w_iv, w_q = md.row_weights(rows, "inverse_variance"), md.row_weights(rows, "quality")
    assert w_iv.mean() == pytest.approx(1.0) and w_q.mean() == pytest.approx(1.0) and w_iv.std() > 0


def test_feature_selection_and_stability():
    store = synthetic_store(30)
    rows = md.training_rows(store, Mask.empty(), md.DataConfig(), OUTCOME_GROUP)
    enc = md.FeatureEncoder(md.DataConfig(), OUTCOME_GROUP, FAMILY, COMPONENTS).fit(rows)
    fold = md.inner_folds(rows["group"], 3)
    X = enc.transform_rows(rows, oof_folds=fold)
    items = md.pooled_items(rows)
    kept, table = fs.select_features(enc, X, rows["y"].to_numpy(), md.row_weights(rows, "inverse_variance"), items, fold,
                                     {"learning_rate": 0.1, "max_iter": 50, "min_samples_leaf": 10})
    assert "cat_outcome_id" in kept and all(r["n_folds"] == 3 for r in table)
    assert "ctx_precip_annual" in kept  # the only layer with signal survives
    assert fs.stable_features([["a", "b"], ["a", "b"], ["a"], ["a", "b"], ["a", "b"]]) == ["a", "b"]  # b in 4 of 5
    assert fs.stable_features([["a", "b"], ["a", "b"], ["a"], ["a", "b"], ["a"]]) == ["a"]             # b in 3 of 5


def test_fixed_serving_features_skip_selection():
    store = synthetic_store(16)
    fixed = ("ctx_precip_annual", "cat_outcome_id", "cat_objective_group", "comp_Mulch")
    eng = _engine(M1Config(tune=False, select=True, inner_folds=3, fixed_features=fixed))
    eng.fit(store, Mask.empty())
    s = eng.fit_summaries[-1]
    assert s["features"] == [n for n in eng.engine.encoder.feature_names if n in fixed] and s["feature_selection"] == "fixed (stable set)"
    assert len(eng.rank(_req("q", ["A", "B"], {"ctx_precip_annual": 900.0}))) == 2
    assert eng.params()["folds"][0]["features"] == s["features"]
