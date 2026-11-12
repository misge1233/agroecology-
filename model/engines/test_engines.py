"""The baseline engines (E4 Part 4): interface, masking, fallbacks, and the random engine's
agreement with its analytic expectations."""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from model import metrics as mm
from model.engines.base import Engine, RankRequest
from model.engines.m0_current import M0CurrentEngine
from model.engines.nearest_studies import NearestStudiesEngine
from model.engines.practice_prior import PracticePriorEngine
from model.engines.random_engine import RandomEngine
from model.harness.mask import Mask
from pipelines.evidence import schema

OUTCOME_GROUP = {"YIELD": "productivity", "SOIL_LOSS": "water", "INCOME": "economics"}


def _req(qid, candidates, outcome="YIELD", context=None, direction=1, crop=None, legacy=None, **kw):
    return RankRequest(query_id=qid, context=context or {}, challenge_ids=[], outcome_id=outcome,
                       candidates=list(candidates), crop=crop, user_attrs={}, mask=Mask.empty(), direction=direction,
                       objective_group=OUTCOME_GROUP.get(outcome, "other"), legacy_indicator=kw.get("legacy_indicator"),
                       legacy_rows=legacy or {})


def _row(i, study, practice, lrr, outcome="YIELD", doi=None, lat=9.0, lon=38.0, var=None, family="F", ctx=None):
    r = {"row_id": f"ERA:{study}:{i}", "source": "ERA", "study_id": study, "doi": doi, "citation": "c", "country": "ET",
         "lat": lat, "lon": lon, "loc_precision": "site", "loc_method": "reported", "site_name": None,
         "practice_id": practice, "practice_raw": practice, "practice_family": family, "outcome_id": outcome,
         "outcome_raw": outcome, "direction": -1 if outcome == "SOIL_LOSS" else 1, "direction_reviewed": True,
         "lrr": lrr, "var_lrr": var, "weight": 1.0, "quality_flag": "NR", "licence": "l"}
    r.update(ctx or {})
    return r


# ----------------------------------------------------------------- random
def test_random_engine_matches_its_analytic_expectations():
    sizes = [2, 3, 4, 5] * 25
    queries = [(f"q{i}", [f"P{j}" for j in range(n)]) for i, n in enumerate(sizes)]
    items = pd.DataFrame([{"query_id": q, "practice_id": p, "y": float(j)} for q, cands in queries for j, p in enumerate(cands)])
    rows = []
    for seed in range(40):
        eng = RandomEngine(seed=seed)
        assert isinstance(eng, Engine)
        eng.fit(pd.DataFrame(), Mask.empty())
        for q, cands in queries:
            for it in eng.rank(_req(q, cands)):
                rows.append({"method": "random", "split": "s", "rep": seed, "fold": 0, "query_id": q,
                             "practice_id": it.practice_id, "score": it.score, "est_lrr": np.nan, "lo": np.nan,
                             "hi": np.nan, "abstain": it.abstain})
    pq = mm.per_query_table(pd.DataFrame(rows), items)
    agg = mm.aggregate(pq)["random"]["s"]
    exp = mm.expected_random(sizes)
    assert agg["top1_hit"]["mean"] == pytest.approx(exp["top1_hit"], abs=0.03)
    assert agg["tophalf_hit"]["mean"] == pytest.approx(exp["tophalf_hit"], abs=0.03)
    assert agg["c_index"]["mean"] == pytest.approx(0.5, abs=0.02)
    assert agg["ndcg3"]["mean"] == pytest.approx(exp["ndcg3"], abs=0.03)
    assert abs(agg["spearman_median"]["mean"]) < 0.15
    # deterministic per (seed, query): the same scores twice
    a = [i.score for i in RandomEngine(3).rank(_req("q7", ["A", "B", "C"]))]
    assert a == [i.score for i in RandomEngine(3).rank(_req("q7", ["A", "B", "C"]))]
    assert a != [i.score for i in RandomEngine(4).rank(_req("q7", ["A", "B", "C"]))]


# ----------------------------------------------------------------- practice prior
def test_practice_prior_means_fallbacks_and_mask():
    store = schema.coerce(pd.DataFrame([
        _row(1, "ERA_S1", "A", 0.2), _row(2, "ERA_S1", "A", 0.4), _row(3, "ERA_S2", "B", -0.1),
        _row(4, "ERA_S2", "C", 0.5, outcome="SOIL_LOSS"),               # oriented: -0.5 for a lower-is-better outcome
        _row(5, "ERA_S3", "A", 0.9),                                     # held out below
        _row(6, "ERA_S3", "D", 0.3, family="G"),
    ]))
    eng = PracticePriorEngine(outcome_group=OUTCOME_GROUP, family_of={"E": "F", "C": "F"})
    eng.fit(store, Mask.from_groups(["ERA_S3"], store))
    items = {i.practice_id: i for i in eng.rank(_req("q", ["A", "B", "C", "E", "D"]))}
    assert items["A"].est_lrr == pytest.approx(0.3) and items["A"].lead_source == "practice_prior:practice_group"
    assert items["A"].lo < 0.3 < items["A"].hi and not items["A"].abstain
    assert items["B"].est_lrr == pytest.approx(-0.1)
    # C has no productivity rows: family F fallback (A, B rows: mean of 0.2, 0.4, -0.1)
    assert items["C"].est_lrr == pytest.approx((0.2 + 0.4 - 0.1) / 3) and items["C"].lead_source.endswith("family_group")
    assert items["E"].est_lrr == pytest.approx((0.2 + 0.4 - 0.1) / 3)
    assert items["D"].abstain  # only in the held-out study
    water = {i.practice_id: i for i in eng.rank(_req("q2", ["C", "A", "D"], outcome="SOIL_LOSS"))}
    assert water["C"].est_lrr == pytest.approx(-0.5)
    # A has no water rows: its family F has one (C's), so the family mean comes before the practice-wide mean
    assert water["A"].est_lrr == pytest.approx(-0.5) and water["A"].lead_source.endswith("family_group")
    assert water["D"].abstain  # family G exists only in the held-out study
    order = sorted(items.values(), key=lambda i: -i.score)
    assert order[0].practice_id == "A"


# ----------------------------------------------------------------- nearest studies
def test_nearest_studies_uses_context_distance_and_abstains_when_thin():
    rows = []
    # cluster 1 (rain 600, elevation 1500): practice A effect +0.5 in five studies; cluster 2 (1500 mm, 2500 m): -0.5
    for s in range(5):
        rows.append(_row(1, f"ERA_C1_{s}", "A", 0.5 + 0.01 * s, lat=8 + s * 0.01, ctx={"ctx_precip_annual": 600.0, "ctx_elevation": 1500.0}))
        rows.append(_row(1, f"ERA_C2_{s}", "A", -0.5 - 0.01 * s, lat=10 + s * 0.01, ctx={"ctx_precip_annual": 1500.0, "ctx_elevation": 2500.0}))
    rows.append(_row(1, "ERA_B1", "B", 0.1, ctx={"ctx_precip_annual": 600.0, "ctx_elevation": 1500.0}))
    rows.append(_row(2, "ERA_B2", "B", 0.2, ctx={"ctx_precip_annual": 600.0, "ctx_elevation": 1500.0}))
    store = schema.coerce(pd.DataFrame(rows))
    eng = NearestStudiesEngine(outcome_group=OUTCOME_GROUP, k=4, k_min=3)
    eng.fit(store, Mask.empty())
    near1 = {i.practice_id: i for i in eng.rank(_req("q", ["A", "B"], context={"ctx_precip_annual": 650.0, "ctx_elevation": 1550.0}))}
    assert 0.45 < near1["A"].est_lrr < 0.55 and not near1["A"].abstain and len(near1["A"].citations) == 4
    assert near1["B"].abstain  # two groups < k_min
    near2 = {i.practice_id: i for i in eng.rank(_req("q", ["A"], context={"ctx_precip_annual": 1450.0, "ctx_elevation": 2450.0}))}
    assert -0.55 < near2["A"].est_lrr < -0.45
    # reported context only (Rainfall, Altitude_r) still finds the nearer cluster
    rep = eng.rank(_req("q", ["A"], context={"Rainfall": 600.0, "Altitude_r": 1500.0}))[0]
    assert rep.est_lrr > 0.4
    # the mask removes the held-out studies from the pool
    held = Mask.from_groups([f"ERA_C1_{s}" for s in range(5)], store)
    eng.fit(store, held)
    masked = eng.rank(_req("q", ["A"], context={"ctx_precip_annual": 650.0, "ctx_elevation": 1550.0}))[0]
    assert masked.est_lrr < 0 and not set(masked.citations) & held.study_ids
    assert eng.params()["k"] == 4


# ----------------------------------------------------------------- m0_current
def _dataset(n_studies=10, practices=("P0", "P1", "P2")):
    rows = []
    for s in range(n_studies):
        for j, p in enumerate(practices):
            for ind in ("yield", "soil loss"):
                effect = (j + 1) * 0.2
                rows.append({"source": "ERA", "Study_No_": f"ERA_S{s:02d}", "latitude": 9.0 + s * 0.1, "longitude": 38.0,
                             "CSA_practices": p, "practice_family": "F", "Crop_group": "Cereal", "crop_type": "Maize",
                             "Rainfall": 800.0 + s, "Altitude_r": 2000.0, "slope": 5.0, "temp_mean_annual": 19.0,
                             "precip_seasonality": 70.0, "lgp_days": 180.0, "soil_clay": 30.0, "soil_ph": 6.0,
                             "soil_soc": 20.0, "land_cover": 40, "aez_belt": "Moist Dega", "Indicator": ind,
                             "response_ratio": 1.0, "log_response_ratio": effect if ind == "yield" else -effect})
    return pd.DataFrame(rows)


def test_m0_current_refits_per_fold_and_ranks_legacy_and_store_queries(tmp_path):
    import evaluate as ev

    ds = _dataset()
    path = tmp_path / "ds.csv"
    ds.to_csv(path, index=False)
    eng = M0CurrentEngine(dataset_path=path, spec=ev.ModelSpec("RandomForest", {"n_estimators": 20, "min_samples_leaf": 2}),
                          label_of={"PID0": "P0", "PID1": "P1", "PID2": "P2"})
    mask = Mask.from_groups(["ERA_S00"], schema.coerce(pd.DataFrame([_row(1, "ERA_S00", "PID0", 0.1)])))
    eng.fit(pd.DataFrame(), mask)
    assert eng.n_train == len(ds) - 6  # the held-out study's rows are not fitted
    # legacy rows: averaged per practice, oriented; a lower-is-better indicator flips the sign
    cell = ds[(ds.Study_No_ == "ERA_S00") & (ds.Indicator == "soil loss")]
    legacy = {p: [int(i) for i in cell.index[cell.CSA_practices == p]] for p in ("P0", "P1", "P2")}
    items = eng.rank(_req("lq", ["P0", "P1", "P2"], outcome="SOIL_LOSS", legacy=legacy, legacy_indicator="soil loss"))
    by = {i.practice_id: i for i in items}
    assert by["P2"].score > by["P1"].score > by["P0"].score and by["P2"].est_lrr > 0 and not by["P2"].abstain
    assert by["P2"].lo < by["P2"].est_lrr < by["P2"].hi
    # a store-style request: context under the legacy names, candidate ids mapped to labels
    ctx = {"Rainfall": 805.0, "Altitude_r": 2000.0, "temp_mean_annual": 19.0, "precip_seasonality": 70.0, "slope": 5.0,
           "soil_clay": 30.0, "land_cover": 40, "aez_belt": "Moist Dega"}
    sq = {i.practice_id: i for i in eng.rank(_req("sq", ["PID2", "PID0", "X"], context=ctx, crop="maize", legacy_indicator="yield"))}
    assert sq["PID2"].score > sq["PID0"].score and sq["PID2"].lead_source == "model"
    assert sq["X"].abstain  # no frozen label
    assert all(i.abstain for i in eng.rank(_req("nq", ["PID2"], outcome="INCOME", context=ctx)))  # no legacy indicator
    assert all(i.abstain for i in eng.rank(_req("cq", ["PID2"], context={}, legacy_indicator="yield")))  # no context
    assert eng.params()["spec"].startswith("RandomForest")
