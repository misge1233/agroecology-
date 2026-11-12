"""Harness foundations (E4 Parts 1-3): comparator classes, eligibility, pooling, query
building, deterministic folds with no split group or block, and the Mask."""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from model.harness import folds as hf
from model.harness import queries as hq
from model.harness.mask import Mask, era_code_of, group_key
from pipelines.evidence import schema


# ----------------------------------------------------------------- fixtures
class Tax:
    """A minimal taxonomy object (the fields the query builder reads)."""

    def __init__(self):
        self.outcomes = pd.DataFrame([
            {"outcome_id": "YIELD", "objective_group": "productivity", "legacy_indicator": "yield", "direction": "1"},
            {"outcome_id": "SOIL_LOSS", "objective_group": "water", "legacy_indicator": "soil loss", "direction": "-1"},
        ])
        self.challenges = pd.DataFrame([
            {"challenge_id": "LOW_CROP_PRODUCTIVITY", "outcome_ids": "YIELD;BIOMASS_YIELD"},
            {"challenge_id": "SOIL_EROSION", "outcome_ids": "SOIL_LOSS;RUNOFF"},
            {"challenge_id": "SOIL_FERTILITY_DECLINE", "outcome_ids": "SOM_CONTENT;YIELD"},
        ])
        self.practices = pd.DataFrame([{"practice_id": p, "practice_family": "F"} for p in ("A", "B", "C", "D")])


def _row(i, study, practice, lrr, outcome="YIELD", direction=1, source="ERA", doi="10.1/p1", lat=9.0, lon=38.0,
         comparator="control", crop="Maize", var=None, weight=1.0, year=2020, country="ET", loc="site",
         method="reported", extra=None, reviewed=True, ctx=True):
    r = {"row_id": f"{source}:{study}:{i}", "source": source, "study_id": study, "doi": doi, "citation": "c",
         "year": year, "country": country, "lat": lat, "lon": lon, "loc_precision": loc, "loc_method": method,
         "site_name": "Site", "practice_id": practice, "practice_raw": practice.lower(), "practice_family": "F",
         "comparator": comparator, "crop": crop, "outcome_id": outcome, "outcome_raw": outcome.lower(),
         "direction": direction, "direction_reviewed": reviewed, "lrr": lrr, "var_lrr": var, "weight": weight,
         "quality_flag": "NR", "licence": "l", "extra": json.dumps(extra) if extra else None,
         "ctx_reported_rain_mm": 700.0, "ctx_reported_altitude_m": 2000.0}
    if ctx:
        r.update({"ctx_release": "ET/2026.1", "ctx_precip_annual": 900.0, "ctx_elevation": 2100.0,
                  "ctx_temp_mean_annual": 18.0, "ctx_precip_seasonality": 80.0, "ctx_slope": 5.0, "ctx_soil_clay": 30.0,
                  "ctx_land_cover": 40, "ctx_aez_belt": 7, "ctx_lgp_days": 200.0, "ctx_soil_ph": 6.5, "ctx_soil_soc": 20.0,
                  "ctx_twi": 8.0})
    return r


def small_store() -> pd.DataFrame:
    rows = [
        # query 1: one DOI, site (9, 38), YIELD, maize, control: practices A, B, C (B measured twice with var)
        _row(1, "ERA_S1", "A", 0.10), _row(2, "ERA_S1", "B", 0.30, var=0.01), _row(3, "ERA_S1", "B", 0.50, var=0.03),
        _row(4, "ERA_S1", "C", 0.20),
        # the same DOI extracted by CSA: same group, same site -> same query (row 5 adds practice D)
        _row(1, "CSA_9", "D", -0.10, source="CSA"),
        # a dup_of row and an unreviewed row are ignored
        _row(6, "ERA_S1", "A", 0.90, extra={"dup_of": "ERA:ERA_S1:1"}), _row(7, "ERA_S1", "C", 0.90, reviewed=False),
        # query 2: soil loss (lower is better), farmer practice comparator, only 2 practices
        _row(8, "ERA_S1", "A", -0.40, outcome="SOIL_LOSS", direction=-1, comparator="Farmer practice"),
        _row(9, "ERA_S1", "B", -0.10, outcome="SOIL_LOSS", direction=-1, comparator="farmers practice"),
        # query 3: a Habtamu study without DOI, country precision, 2023; a single practice (no query)
        _row(1, "HAB_X_2023_001", "A", 0.2, doi=None, lat=None, lon=None, loc="country", country="KE", year=2023,
             source="HAB", ctx=False),
        # query 4: HAB 2024 study, no DOI, site, three practices, unchecked geocode -> excluded entirely
        _row(1, "HAB_Y_2024_001", "A", 0.2, doi=None, lat=8.0, lon=37.0, year=2024, source="HAB", method="geocoded_llm_unchecked"),
        _row(2, "HAB_Y_2024_001", "B", 0.3, doi=None, lat=8.0, lon=37.0, year=2024, source="HAB", method="geocoded_llm_unchecked"),
        # query 5: HAB 2024 checked, two sites of one group (spanning two blocks)
        _row(1, "HAB_Z_2024_001", "A", 0.2, doi="10.1/z", lat=8.2, lon=37.5, year=2024, source="HAB", method="geocoded_llm_checked"),
        _row(2, "HAB_Z_2024_001", "B", 0.3, doi="10.1/z", lat=8.2, lon=37.5, year=2024, source="HAB", method="geocoded_llm_checked"),
        _row(3, "HAB_Z_2024_001", "A", 0.1, doi="10.1/z", lat=9.7, lon=37.5, year=2024, source="HAB", method="geocoded_llm_checked"),
        _row(4, "HAB_Z_2024_001", "C", 0.6, doi="10.1/z", lat=9.7, lon=37.5, year=2024, source="HAB", method="geocoded_llm_checked"),
    ]
    return schema.coerce(pd.DataFrame(rows))


AEZ = {7: "Moist Dega"}


# ----------------------------------------------------------------- comparator classes
@pytest.mark.parametrize("text,cls", [
    ("control", "no_practice"), ("Control", "no_practice"), ("CONTROL", "no_practice"), ("N0P0", "no_practice"),
    ("FYM0 NP0", "no_practice"), ("control 0 H", "no_practice"), ("T1", "no_practice"), ("No bund_ wheat broadcast", "no_practice"),
    ("V1- Farmer practice", "farmer_practice"), ("Local", "farmer_practice"), ("traditional", "farmer_practice"),
    ("CT", "conventional_tillage"), ("conventional tillage", "conventional_tillage"), ("Ploughing", "conventional_tillage"),
    ("100% RF", "mineral_fertilizer_only"), ("NPK", "mineral_fertilizer_only"), ("recommended fertilizer", "mineral_fertilizer_only"),
    ("Black eye bean", "other"), (None, "other"), ("", "other"), (float("nan"), "other"),
])
def test_comparator_class(text, cls):
    assert hq.comparator_class(text) == cls


# ----------------------------------------------------------------- queries
def test_eligibility_pooling_and_query_keys():
    store = small_store()
    tax = Tax()
    q, items = hq.build_queries(store, tax, seed=0, aez_lookup=AEZ)
    assert len(q) == 4  # yield cell, soil-loss cell, and the two HAB_Z sites
    y = q[q["outcome_id"] == "YIELD"].iloc[0]
    assert y["group"] == "10.1/p1" and y["site"] == "9.000,38.000" and y["comparator_class"] == "no_practice"
    assert y["n_practices"] == 4 and y["crop"] == "maize" and set(y["candidates"].split(";")) == {"A", "B", "C", "D"}
    assert y["sources"] == "CSA;ERA" and y["challenge_ids"] == "LOW_CROP_PRODUCTIVITY;SOIL_FERTILITY_DECLINE"
    ctx = json.loads(y["context"])
    assert ctx["Rainfall"] == 900.0 and ctx["aez_belt"] == "Moist Dega" and ctx["ctx_twi"] == 8.0 and ctx["land_cover"] == 40
    assert y["ctx_source"] == "release" and y["belt"] == "Moist Dega" and y["query_set"] == "ET"
    it = items[items["query_id"] == y["query_id"]].set_index("practice_id")
    # B: inverse-variance mean of 0.3 (var .01) and 0.5 (var .03) = (30 + 16.67)/(133.3) = 0.35
    assert it.loc["B", "y"] == pytest.approx(0.35) and it.loc["B", "pooling"] == "inverse_variance"
    assert it.loc["B", "var_pooled"] == pytest.approx(1 / (100 + 100 / 3))
    assert it.loc["A", "y"] == pytest.approx(0.10) and it.loc["A", "pooling"] == "weighted_mean"  # dup_of row ignored
    assert it.loc["C", "y"] == pytest.approx(0.20)  # the unreviewed row is ignored
    assert it.loc["D", "n_rows"] == 1 and it.loc["D", "practice_label"] == "d"
    s = q[q["outcome_id"] == "SOIL_LOSS"].iloc[0]
    assert s["comparator_class"] == "farmer_practice" and s["n_practices"] == 2
    si = items[items["query_id"] == s["query_id"]].set_index("practice_id")
    assert si.loc["A", "y"] == pytest.approx(0.40) and si.loc["A", "lrr_pooled"] == pytest.approx(-0.40)  # oriented
    z = q[q["group"] == "10.1/z"]
    assert len(z) == 2 and z["post_2024"].all() and (z["query_set"] == "ET").all()
    # determinism of ids and candidate order
    q2, _ = hq.build_queries(store, tax, seed=0, aez_lookup=AEZ)
    pd.testing.assert_frame_equal(q.reset_index(drop=True), q2.reset_index(drop=True))
    q3, _ = hq.build_queries(store, tax, seed=1, aez_lookup=AEZ)
    assert set(q3["query_id"]) == set(q["query_id"])
    # without the comparator key the two yield rows with different comparators would merge
    qn, _ = hq.build_queries(store, tax, seed=0, use_comparator=False, aez_lookup=AEZ)
    assert (qn["comparator_class"] == "all").all() and len(qn) == 4


def test_reported_context_for_country_precision():
    store = small_store()
    store.loc[store["study_id"] == "HAB_X_2023_001", "practice_id"] = ["A"]
    extra = store[store["study_id"] == "HAB_X_2023_001"].copy()
    extra["row_id"] = "HAB:HAB_X_2023_001:2"
    extra["practice_id"] = "B"
    store = pd.concat([store, extra], ignore_index=True)
    q, _ = hq.build_queries(store, Tax(), aez_lookup=AEZ)
    g = q[q["group"] == "HAB_X_2023_001"].iloc[0]
    ctx = json.loads(g["context"])
    assert g["ctx_source"] == "reported" and ctx["Rainfall"] == 700.0 and ctx["Altitude_r"] == 2000.0 and ctx["aez_belt"] is None
    assert g["query_set"] == "global" and g["site"] == "Site" and g["loc_precision"] == "country"


def test_legacy_queries_reproduce_the_p7_cells():
    rows = []
    for s in range(3):
        for p in ("P0", "P1", "P2"):
            for ind, val in (("yield", 0.1), ("soil loss", -0.2)):
                rows.append({"source": "ERA", "Study_No_": f"ERA_S{s}", "latitude": 9.0 + s, "longitude": 38.0,
                             "CSA_practices": p, "practice_family": "F", "Crop_group": "Cereal", "crop_type": "Maize",
                             "Rainfall": 800.0, "Altitude_r": 2000.0, "slope": 5.0, "temp_mean_annual": 18.0,
                             "precip_seasonality": 70.0, "lgp_days": 180.0, "soil_clay": 30.0, "soil_ph": 6.0,
                             "soil_soc": 20.0, "land_cover": 40, "aez_belt": "Moist Dega", "Indicator": ind,
                             "response_ratio": 1.0, "log_response_ratio": val * (1 + "P0P1P2".index(p) / 2)})
    ds = pd.DataFrame(rows)
    q, items = hq.legacy_queries(ds, Tax(), label_to_id={"P0": "A"})
    assert len(q) == 6 and (q["query_set"] == "legacy_68").all() and q["legacy"].all()
    sl = q[q["outcome_id"] == "SOIL_LOSS"].iloc[0]
    it = items[items["query_id"] == sl["query_id"]].set_index("practice_id")
    assert it.loc["A", "y"] == pytest.approx(0.2) and it.loc["A", "practice_label"] == "P0"  # oriented, label kept
    assert json.loads(it.loc["A", "rows_json"]) == [ds.index[(ds.Study_No_ == sl["group"]) & (ds.CSA_practices == "P0") & (ds.Indicator == "soil loss")][0]]
    assert json.loads(sl["context"])["legacy_rows"] is True and sl["direction"] == -1


# ----------------------------------------------------------------- folds
def test_folds_are_deterministic_and_never_split_a_group_or_block():
    store = small_store()
    q, _ = hq.build_queries(store, Tax(), aez_lookup=AEZ)
    # inflate: 40 groups spread over 6 blocks so the balance has something to do
    extra = []
    for i in range(40):
        for j in range(1 + i % 3):
            r = q.iloc[0].copy()
            r["query_id"] = f"q{i:02d}_{j}"
            r["group"] = f"10.1/g{i:02d}"
            r["lat"], r["lon"] = 6.5 + (i % 6), 36.5 + (j % 2) * 0.2
            extra.append(r)
    big = pd.concat([q, pd.DataFrame(extra)], ignore_index=True)
    big["legacy"] = False
    for split in ("spatial", "study"):
        a, span_a = hf.build_folds(big, split)
        b, _ = hf.build_folds(big.sample(frac=1, random_state=1), split)  # input order does not matter
        pd.testing.assert_frame_equal(a, b)
        chk = hf.check_integrity(a.set_index("query_id"), split)
        assert chk["ok"], chk
        assert set(a.columns) == {"query_id", "group", "block", *hf.rep_cols()}
        assert a[hf.rep_cols()].nunique().min() == 5  # every repetition uses all five folds
        reps = a[hf.rep_cols()].to_numpy()
        assert (reps[:, 0] != reps[:, 1]).any()  # repetitions differ
    sp, spanning = hf.build_folds(big, "spatial")
    assert spanning and spanning[0]["group"] == "10.1/z" and spanning[0]["assigned"] in ("b8_37", "b9_37")
    assert (sp[sp["group"] == "10.1/z"]["fold_rep00"].nunique()) == 1
    assert hf.spatial_block(None, None, "KE") == "country_KE" and hf.spatial_block(-1.2, 36.9, "KE") == "b-2_36"


def test_load_folds_and_members(tmp_path):
    store = small_store()
    q, _ = hq.build_queries(store, Tax(), aez_lookup=AEZ)
    df, _ = hf.build_folds(q, "study")
    hf.write_folds(df, tmp_path / "f.csv")
    f = hf.load_folds(tmp_path / "f.csv")
    assert f.index.name == "query_id" and f["fold_rep00"].dtype.kind == "i"
    held, groups = hf.fold_members(f, 0, int(f["fold_rep00"].iloc[0]))
    assert held and set(groups) <= set(f["group"])


# ----------------------------------------------------------------- mask
def test_mask_from_groups_covers_every_channel():
    store = small_store()
    m = Mask.from_groups(["10.1/p1", "HAB_X_2023_001"], store)
    assert m.dois == {"10.1/p1"} and {"ERA_S1", "CSA_9", "HAB_X_2023_001"} <= m.study_ids
    assert {"S1", "HAB_X_2023_001"} <= m.era_codes
    assert m.blocks_chunk({"doi": "10.1/P1"}) and m.blocks_chunk({"era_code": "S1"})
    assert m.blocks_chunk({"study_ids": "ERA_S1;ERA_S2"}) and m.blocks_chunk({"study_ids": ["CSA_9"]})
    assert not m.blocks_chunk({"doi": "10.1/z", "era_code": "Z9", "study_ids": "HAB_Z_2024_001"})
    assert not m.blocks_chunk({}) and not Mask.chunk_is_maskable({"title": "x"}) and Mask.chunk_is_maskable({"doi": "10.1/a"})
    assert m.blocks_graph_study({"label": "CSA_9"}) and m.blocks_graph_study({"id": "Study:ERA_S1"})
    assert m.blocks_graph_study({"label": "ERA_S7", "doi": "10.1/p1"}) and not m.blocks_graph_study({"label": "ERA_S7"})
    kept = m.filter_rows(store)
    assert set(kept["study_id"]) == {"HAB_Y_2024_001", "HAB_Z_2024_001"}
    ds = pd.DataFrame({"Study_No_": ["ERA_S1", "ERA_S2", "CSA_9"], "x": [1, 2, 3]})
    assert m.filter_rows(ds)["Study_No_"].tolist() == ["ERA_S2"]
    assert Mask.from_dict(json.loads(m.to_json())) == m
    assert m.where_clause() == {"$and": [{"doi": {"$nin": ["10.1/p1"]}}, {"era_code": {"$nin": sorted(m.era_codes)}}]}
    assert Mask.empty().is_empty and Mask.empty().where_clause() is None and Mask.empty().filter_rows(store).equals(store)
    assert group_key("10.1/A ", "S") == "10.1/a" and group_key(None, "S") == "S" and group_key(np.nan, "S") == "S"
    assert era_code_of("ERA_JS0269.2") == "JS0269" and era_code_of("CSA_9") is None
