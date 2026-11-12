"""E7: the decision branches, the heuristic baselines, the fresh-set loader path, the context
swap and the names-only prompt."""
from __future__ import annotations

import json

import pandas as pd
import pytest

from model.e7 import decision as dec
from model.engines.base import RankRequest
from model.engines.heuristics import COMPONENT_INPUT_LEVEL, ComponentCountEngine, InputIntensityEngine, table_hash
from model.harness.mask import Mask

# ----------------------------------------------------------------- decision branches
Z = {"top1_hit": 0.60, "c_index": 0.65}
FAR = {"top1_hit": 0.50, "c_index": 0.60}


def _rc(rate=0.0, lift=(0.0, -0.05, 0.05)):
    return {"identification_rate": [rate, 0.0, rate], "title_lift_top1": list(lift)}


def _pair(t1=(0.0, -0.05, 0.05), c=(0.0, -0.05, 0.05)):
    return {"top1_hit": dict(zip(("diff", "lo", "hi"), t1)), "c_index": dict(zip(("diff", "lo", "hi"), c))}


WIN, TIE, LOSS_C = _pair((0.05, 0.01, 0.09)), _pair(), _pair((0.06, 0.01, 0.1), (-0.05, -0.09, -0.01))


def test_branch_1_recall_by_identification_or_title_lift():
    d = dec.decide(_rc(rate=0.30), FAR, FAR, Z, 0.5, WIN, WIN, TIE, TIE)
    assert d.branch == 1 and d.design == "m1_v2" and not d.llm_in_ranking
    d = dec.decide(_rc(lift=(0.12, 0.02, 0.2)), FAR, FAR, Z, 0.5, WIN, WIN, TIE, TIE)
    assert d.branch == 1
    # a lift above 0.10 whose interval touches zero, or a significant lift under 0.10: not branch 1
    assert dec.decide(_rc(lift=(0.12, -0.01, 0.2)), FAR, FAR, Z, 0.5, TIE, TIE, TIE, TIE).branch == 3
    assert dec.decide(_rc(lift=(0.08, 0.01, 0.15)), FAR, FAR, Z, 0.5, TIE, TIE, TIE, TIE).branch == 3


def test_branch_2_context_not_used_and_the_gate_rule():
    near = {"top1_hit": 0.61, "c_index": 0.66}
    d = dec.decide(_rc(), near, FAR, Z, 0.3, TIE, WIN, TIE, TIE)
    assert d.branch == 2 and d.design == "m1_v2"  # the stack's win does not count in branch 2
    d = dec.decide(_rc(), near, FAR, Z, 0.3, WIN, TIE, TIE, TIE)
    assert d.branch == 2 and d.design == "m3_gate" and d.llm_in_ranking
    # the swap condition needs both the margins and a mean tau above 0.8
    assert dec.decide(_rc(), FAR, near, Z, 0.85, TIE, TIE, TIE, TIE).branch == 2
    assert dec.decide(_rc(), FAR, near, Z, 0.75, TIE, TIE, TIE, TIE).branch == 3
    # 0.02 is inclusive, 0.021 is not
    assert dec.within({"top1_hit": 0.62, "c_index": 0.67}, Z) and not dec.within({"top1_hit": 0.621, "c_index": 0.65}, Z)


def test_branch_3_best_hybrid_or_m1_v2():
    assert dec.decide(_rc(), FAR, FAR, Z, 0.3, TIE, TIE, TIE, TIE).design == "m1_v2"
    assert dec.decide(_rc(), FAR, FAR, Z, 0.3, WIN, TIE, TIE, TIE).design == "m3_gate"
    assert dec.decide(_rc(), FAR, FAR, Z, 0.3, TIE, WIN, TIE, TIE).design == "m3_stack"
    assert dec.decide(_rc(), FAR, FAR, Z, 0.3, WIN, WIN, TIE, TIE).design == "m3_gate"  # tie between hybrids
    assert dec.decide(_rc(), FAR, FAR, Z, 0.3, WIN, WIN, TIE, WIN).design == "m3_stack"
    # "beats" fails when the other metric is significantly worse
    assert not dec.beats(LOSS_C) and dec.beats(WIN) and not dec.beats(TIE) and not dec.beats(None)


# ----------------------------------------------------------------- heuristics
def _req(cands):
    return RankRequest("q", {}, [], "YIELD", list(cands), None, {}, Mask.empty(), 1, "productivity")


def test_component_count_and_input_intensity_orderings():
    comps = {"A": ["Mulch"], "AB": ["Mulch", "Inorganic Fertilizer"], "R": ["Crop Rotation"], "F": ["Inorganic Fertilizer"]}
    fam = {"A": "Erosion control and water management", "AB": "Integrated soil fertility management",
           "R": "Crop production and management", "F": "Integrated soil fertility management"}
    rows = pd.DataFrame({"practice_id": ["A", "R", "F", "AB"], "lrr": [0.5, 0.3, 0.1, 0.0], "direction": [1] * 4,
                         "outcome_id": ["YIELD"] * 4, "practice_family": [fam[p] for p in ("A", "R", "F", "AB")]})
    cc = ComponentCountEngine({"YIELD": "productivity"}, fam, comps)
    cc.fit(rows, Mask.empty())
    order = [i.practice_id for i in sorted(cc.rank(_req(["A", "R", "F", "AB"])), key=lambda i: -i.score)]
    assert order == ["AB", "A", "R", "F"]  # 2 components first; ties by the prior (0.5 > 0.3 > 0.1)
    ii = InputIntensityEngine({"YIELD": "productivity"}, fam, comps)
    ii.fit(rows, Mask.empty())
    items = ii.rank(_req(["A", "R", "F", "AB"]))
    order = [i.practice_id for i in sorted(items, key=lambda i: -i.score)]
    assert order == ["AB", "F", "A", "R"]  # levels 5, 3, 2, 1
    assert all(not i.abstain and i.est_lrr is None for i in items) and len(table_hash()) == 64
    assert COMPONENT_INPUT_LEVEL["Inorganic Fertilizer Reduction"] == 1


# ----------------------------------------------------------------- fresh_2024plus
def test_fresh_date_rule_marker_query_set_and_one_fold_split():
    from model.harness import run as hr
    from model.m1.test_m1 import synthetic_store
    from pipelines.evidence import load_fresh as lf

    assert lf.is_fresh(2025, None) and lf.is_fresh(2024, 7) and not lf.is_fresh(2024, 6) and not lf.is_fresh(2024, None)
    assert not lf.is_fresh(2023, 12) and not lf.is_fresh(None, None)
    assert lf.publication_month("2024-09-03") == 9 and lf.publication_month("Sep 2024") == 9 and lf.publication_month("") is None
    assert lf.is_fresh_extra(json.dumps({"fresh_2024plus": True})) and not lf.is_fresh_extra('{"x": 1}') and not lf.is_fresh_extra(None)
    assert lf.status(lf.FRESH_DIR.parent / "no_such_dir")["status"] == "pending"
    store = synthetic_store(12)
    q = pd.DataFrame({"query_id": ["a", "b"], "group": ["10.1/g01", "10.1/g02"]})
    plan = hr.fold_plan("fresh", q, hr.HARNESS_DIR, 5, store)
    assert len(plan) == 1 and plan[0][:3] == (0, 0, ["a", "b"]) and plan[0][3].groups == frozenset({"10.1/g01", "10.1/g02"})


def test_fresh_loader_reads_habtamu_format_files(tmp_path):
    """The loader path on a Habtamu-format fixture: rows dated 2025 kept, 2023 dropped, marked."""
    from pipelines.evidence import load_fresh as lf
    from pipelines.evidence import load_habtamu as lh

    if not lh.RAW_PATH.exists():
        pytest.skip("Habtamu export not present (partner data)")
    raw = lh.read_raw(lh.RAW_PATH)
    et = raw[raw["Country"].astype(str).str.contains("Ethiop", case=False, na=False)].head(6).copy()
    if len(et) < 2:
        pytest.skip("no Ethiopian rows in the export")
    sid = et["Study_ID"].astype(str).str.replace(r"_(?:19|20)\d{2}(?=(_\d+|[a-z])?$)", "", regex=True)
    et["Study_ID"] = [f"{s}_2025_001" if i % 2 == 0 else f"{s}_2023_001" for i, s in enumerate(sid)]
    et.to_csv(tmp_path / "fresh.csv", index=False)
    df, log = lf.load(tmp_path)
    assert len(df) and (df["year"] >= 2025).all() and df["study_id"].str.startswith(lf.PREFIX).all()
    assert df["extra"].map(lf.is_fresh_extra).all() and log.dropped.get("not_after_june_2024", 0) >= 1
    assert df["row_id"].is_unique


# ----------------------------------------------------------------- swap and names
def test_swap_partner_is_the_most_dissimilar_query_of_the_same_group():
    from model.m2.run import swap_contexts

    q = pd.DataFrame({"query_id": ["a", "b", "c", "d"], "objective_group": ["g", "g", "g", "h"],
                      "context": [json.dumps({"ctx_precip_annual": v, "ctx_elevation": e}) for v, e in
                                  ((500, 1000), (600, 1100), (1500, 3000), (800, 2000))]})
    ctx, partner = swap_contexts(q)
    assert partner == {"a": "c", "b": "c", "c": "a"} and "d" not in partner  # single-query group: no partner
    assert ctx["a"]["ctx_precip_annual"] == 1500 and swap_contexts(q)[1] == partner


def test_names_prompt_hides_context_and_crop_and_zero_prompt_is_unchanged():
    from model.m2.engine import NOT_GIVEN, M2Engine
    from model.m2.test_m2 import MAPS, FakeClient, _answer
    from model.m1.test_m1 import synthetic_store

    store = synthetic_store()
    req = RankRequest("q1", {"ctx_precip_annual": 900.0, "ctx_aez_belt": 6}, [], "YIELD", ["A", "B"], "maize", {},
                      Mask.empty(), 1, "productivity")
    texts = {}
    for v, kw in (("m2_zero", {}), ("m2_names", {}), ("m2_swap", {"context_override": {"q1": {"ctx_precip_annual": 300.0}}})):
        eng = M2Engine(v, FakeClient(lambda m, n: _answer(["A", "B"])), **MAPS, mode="collect", **kw)
        eng.fit(store, Mask.empty())
        texts[v] = eng.build(req).user
    assert f"FARM CONTEXT: {NOT_GIVEN}" in texts["m2_names"] and f"CROP: {NOT_GIVEN}" in texts["m2_names"]
    assert "900 mm" in texts["m2_zero"] and "CROP: maize" in texts["m2_zero"]
    assert "300 mm" in texts["m2_swap"] and "900 mm" not in texts["m2_swap"] and "CROP: maize" in texts["m2_swap"]
    assert texts["m2_zero"].startswith("FARM CONTEXT: Wet Dega, 900 mm rain")  # the E6 template, unchanged
    with pytest.raises(ValueError):
        M2Engine("m2_swap", FakeClient(lambda m, n: _answer(["A"])), **MAPS)
