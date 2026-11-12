"""Hand-computed fixtures for every metric of the harness (E4 Part 5, Appendix B)."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from model import metrics as mm


def _items(y, score, est=None, lo=None, hi=None, abstain=None):
    n = len(y)
    return pd.DataFrame({"practice_id": [f"P{i}" for i in range(n)], "y": y, "score": score,
                         "est_lrr": est if est is not None else [np.nan] * n,
                         "lo": lo if lo is not None else [np.nan] * n, "hi": hi if hi is not None else [np.nan] * n,
                         "abstain": abstain if abstain is not None else [False] * n})


def test_perfect_and_reversed_rankings():
    y = [1.0, 2.0, 3.0]
    perfect = mm.query_metrics(_items(y, [0.1, 0.2, 0.3]))
    assert perfect["top1_hit"] == 1 and perfect["tophalf_hit"] == 1 and perfect["c_index"] == 1
    assert perfect["ndcg3"] == pytest.approx(1.0) and perfect["spearman"] == pytest.approx(1.0)
    assert perfect["top1_chance"] == pytest.approx(1 / 3) and perfect["abstained"] == 0
    rev = mm.query_metrics(_items(y, [0.3, 0.2, 0.1]))
    assert rev["top1_hit"] == 0 and rev["tophalf_hit"] == 0 and rev["c_index"] == 0 and rev["spearman"] == pytest.approx(-1.0)
    # NDCG@3 by hand: gains 0, 1, 2; ranked order y=1 (g 0), y=2 (g 1, 1/log2 3), y=3 (g 2, 1/log2 4)
    dcg = 0 + 1 / math.log2(3) + 2 / math.log2(4)
    idcg = 2 + 1 / math.log2(3)
    assert rev["ndcg3"] == pytest.approx(dcg / idcg)


def test_ties_count_half_and_top1_accepts_any_observed_best():
    tie = mm.query_metrics(_items([1.0, 2.0, 3.0], [0.5, 0.5, 0.5]))
    assert tie["c_index"] == pytest.approx(0.5) and math.isnan(tie["spearman"])
    # two observed bests: the top-ranked one is a hit either way
    both = mm.query_metrics(_items([3.0, 3.0, 1.0], [0.1, 0.9, 0.2]))
    assert both["top1_hit"] == 1
    # ties in the truth are not comparable pairs: (0,2) and (1,2) discordant -> 0
    tt = mm.query_metrics(_items([1.0, 1.0, 2.0], [3.0, 2.0, 1.0]))
    assert tt["c_index"] == 0 and tt["top1_hit"] == 0
    assert mm.concordance([1, 1, 2], [3, 2, 1]) == (0, 2)
    # top-half: n=4, ranks 1..4; the top-ranked practice has rank 3 (> 2) -> hit; rank 2 -> miss
    assert mm.tophalf_hit([1, 2, 3, 4], [0, 0, 1, 0]) == 1 and mm.tophalf_hit([1, 2, 3, 4], [0, 1, 0, 0]) == 0
    assert mm.top1_hit([1, 2, 3, 4], [0, 0, 0, 1]) == 1


def test_numeric_metrics_and_intervals():
    m = mm.query_metrics(_items([1.0, -1.0, 2.0], [1.0, 0.0, 2.0], est=[0.5, -0.5, 1.0],
                                lo=[0.0, -2.0, 1.5], hi=[2.0, 0.0, 2.5]))
    assert m["rmse"] == pytest.approx(math.sqrt((0.25 + 0.25 + 1.0) / 3))
    assert m["sign_acc"] == pytest.approx(1.0)
    assert m["coverage80"] == pytest.approx(1.0)     # y=1 in [0,2], y=-1 in [-2,0], y=2 in [1.5,2.5]
    assert m["width80"] == pytest.approx(2.0)        # widths 2, 2, 1 -> median 2
    assert m["n_estimates"] == 3


def test_coverage_by_hand():
    m = mm.query_metrics(_items([1.0, -1.0, 2.0], [1.0, 0.0, 2.0], est=[0.5, -0.5, 1.0],
                                lo=[0.0, -2.0, 2.5], hi=[2.0, 0.0, 3.0]))
    assert m["coverage80"] == pytest.approx(2 / 3)  # y=2 is outside [2.5, 3.0]
    assert m["width80"] == pytest.approx(2.0)       # widths 2, 2, 0.5 -> median 2


def test_abstention_rules():
    allab = mm.query_metrics(_items([1.0, 2.0], [0.1, 0.2], abstain=[True, True]))
    assert allab["abstained"] == 1 and math.isnan(allab["c_index"]) and allab["n_estimates"] == 0
    # a partial answer (one candidate abstained) is an abstained query: it is not scored
    part = mm.query_metrics(_items([1.0, 2.0, 3.0], [0.9, 0.5, 0.95], abstain=[False, False, True]))
    assert part["abstained"] == 1 and math.isnan(part["top1_hit"]) and math.isnan(part["c_index"])
    full = mm.query_metrics(_items([1.0, 2.0, 3.0], [0.9, 0.5, 0.95]))
    assert full["abstained"] == 0 and full["top1_hit"] == 1
    one = mm.query_metrics(_items([1.0], [0.5]))
    assert math.isnan(one["c_index"]) and one["n_candidates"] == 1


def _pred_rows(method, split, rep, qid, scores, fold=0, abstain=False):
    return [{"method": method, "split": split, "rep": rep, "fold": fold, "query_id": qid, "practice_id": p,
             "score": s, "est_lrr": np.nan, "lo": np.nan, "hi": np.nan, "abstain": abstain} for p, s in scores.items()]


def test_per_query_table_aggregate_bootstrap_and_breakdowns():
    items = pd.DataFrame([{"query_id": "q1", "practice_id": p, "y": y} for p, y in (("A", 1.0), ("B", 2.0), ("C", 3.0))]
                         + [{"query_id": "q2", "practice_id": p, "y": y} for p, y in (("A", 2.0), ("B", 1.0))])
    preds = pd.DataFrame(
        _pred_rows("m", "study", 0, "q1", {"A": 0.1, "B": 0.2, "C": 0.3})
        + _pred_rows("m", "study", 0, "q2", {"A": 0.9, "B": 0.1})
        + _pred_rows("m", "study", 1, "q1", {"A": 0.3, "B": 0.2, "C": 0.1})
        + _pred_rows("m", "study", 1, "q2", {"A": 0.9, "B": 0.1})
        + _pred_rows("m", "study", 2, "q1", {"A": 0.1, "B": 0.2, "C": 0.3})
        + _pred_rows("m", "study", 2, "q2", {"A": 0.0, "B": 0.0}, abstain=True)  # the method abstains on q2 in rep 2
    )
    pq = mm.per_query_table(preds, items)
    assert len(pq) == 6 and set(pq["query_id"]) == {"q1", "q2"}
    agg = mm.aggregate(pq)["m"]["study"]
    # rep0: top1 (1, 1) -> 1; rep1: (0, 1) -> .5; rep2: q1 only -> 1  => mean .8333
    assert agg["top1_hit"]["mean"] == pytest.approx((1 + 0.5 + 1) / 3) and agg["top1_hit"]["n_reps"] == 3
    assert agg["abstention_rate"]["mean"] == pytest.approx((0 + 0 + 0.5) / 3)
    # pair-pooled C (P7 definition): rep1 has q1 reversed (0 of 3 pairs) and q2 right (1 of 1) -> 1/4
    reps = {r: mm.summarise_rep(b) for r, b in pq.groupby("rep")}
    assert reps[1]["c_index_pooled"] == pytest.approx(1 / 4) and reps[1]["c_index"] == pytest.approx(0.5)
    assert reps[0]["c_index_pooled"] == pytest.approx(1.0)
    assert agg["n_queries"]["mean"] == pytest.approx((2 + 2 + 2) / 3)
    b = mm.bootstrap(pq, "top1_hit", n_boot=200, seed=1)
    assert 0.0 <= b["lo"] <= b["hi"] <= 1.0 and b["n"] == 2
    assert mm.bootstrap(pq, "top1_hit", n_boot=200, seed=1) == b  # seeded
    queries = pd.DataFrame({"query_id": ["q1", "q2"], "objective_group": ["productivity", "water"],
                            "challenge_ids": ["LOW_CROP_PRODUCTIVITY;SOIL_FERTILITY_DECLINE", ""]})
    bd = mm.breakdown(pq, queries, "objective_group", metrics=("top1_hit",), min_cell=1)
    v = bd.set_index("objective_group")["value"]
    assert v["productivity"] == pytest.approx(2 / 3) and v["water"] == pytest.approx(1.0)
    small = mm.breakdown(pq, queries, "objective_group", metrics=("top1_hit",))
    assert (small["value"] == "n < 20").all()  # the default floor
    ch = mm.breakdown(pq, queries, "challenge_ids", metrics=("top1_hit",), min_cell=1, explode=";")
    assert set(ch["challenge_ids"]) == {"LOW_CROP_PRODUCTIVITY", "SOIL_FERTILITY_DECLINE", "none"}


def test_curve_and_calibration_shapes():
    items = pd.DataFrame([{"query_id": f"q{i}", "practice_id": p, "y": y} for i in range(4)
                          for p, y in (("A", 1.0), ("B", 2.0))])
    preds = pd.DataFrame(sum((_pred_rows("m", "study", 0, f"q{i}", {"A": 0.1 * i, "B": 0.5}) for i in range(4)), []))
    preds["est_lrr"] = preds["score"]
    preds["lo"] = preds["score"] - 1
    preds["hi"] = preds["score"] + 1
    pq = mm.per_query_table(preds, items)
    curve = mm.coverage_accuracy_curve(pq, preds, items, "m", "study", steps=4)
    assert list(curve["coverage"]) == pytest.approx([0.25, 0.5, 0.75, 1.0]) and 0 <= curve["accuracy"].min() <= 1
    cal = mm.calibration_table(preds, items, "m", "study", bins=2)
    assert len(cal) == 2 and cal["n"].sum() == 8 and (cal["coverage80"] >= 0).all()


def test_expected_random_values():
    e = mm.expected_random([2, 3, 4])
    assert e["top1_hit"] == pytest.approx((1 / 2 + 1 / 3 + 1 / 4) / 3)
    assert e["tophalf_hit"] == pytest.approx((1 / 2 + 2 / 3 + 2 / 4) / 3)  # ranks above n/2: 1, 2, 2 of 2, 3, 4
    assert e["c_index"] == 0.5 and e["spearman_median"] == 0.0
    # n = 3, gains 2,1,0: the mean NDCG@3 over all 6 permutations by hand
    disc = [1.0, 1 / math.log2(3), 1 / math.log2(4)]
    idcg = 2 * disc[0] + 1 * disc[1]
    from itertools import permutations
    vals = [sum(g * d for g, d in zip([ [2, 1, 0][i] for i in perm ], disc)) / idcg for perm in permutations(range(3))]
    assert mm.expected_random([3])["ndcg3"] == pytest.approx(sum(vals) / 6)


# ------------------------------------------------------------ E5 Part 0: fair comparison
def _preds(method, split, rep, qid, scores, abstain=False, lead="x"):
    return [{"method": method, "split": split, "rep": rep, "fold": 0, "query_id": qid, "practice_id": p, "score": s,
             "est_lrr": s, "lo": s - 1, "hi": s + 1, "abstain": abstain, "lead_source": lead, "citations": ""}
            for p, s in scores.items()]


def test_fill_abstentions_builds_full_coverage_variants():
    preds = pd.DataFrame(
        _preds("practice_prior", "s", 0, "q1", {"A": 0.2, "B": 0.1}, lead="prior")
        + _preds("practice_prior", "s", 0, "q2", {"A": 0.3, "B": 0.4}, lead="prior")
        + _preds("m0", "s", 0, "q1", {"A": 0.9, "B": 0.8})
        + _preds("m0", "s", 0, "q2", {"A": 0.0, "B": 0.0}, abstain=True)   # m0 abstains on q2
        + _preds("full", "s", 0, "q1", {"A": 0.5, "B": 0.6}) + _preds("full", "s", 0, "q2", {"A": 0.5, "B": 0.6})
    )
    out = mm.fill_abstentions(preds)
    assert set(out["method"]) == {"practice_prior", "m0", "full", "m0+prior"}  # 'full' never abstains: no variant
    v = out[out["method"] == "m0+prior"].set_index(["query_id", "practice_id"])
    assert v.loc[("q1", "A"), "score"] == 0.9 and v.loc[("q2", "B"), "score"] == 0.4
    assert v.loc[("q2", "B"), "lead_source"] == "prior_fill:prior" and not v["abstain"].any()
    assert mm.fill_abstentions(out).equals(out) or set(mm.fill_abstentions(out)["method"]) == set(out["method"])  # idempotent


def test_common_subset_and_paired_bootstrap():
    items = pd.DataFrame([{"query_id": q, "practice_id": p, "y": y} for q in ("q1", "q2", "q3", "q4")
                          for p, y in (("A", 1.0), ("B", 2.0), ("C", 3.0))])
    rows = []
    for q in ("q1", "q2", "q3", "q4"):
        rows += _preds("good", "s", 0, q, {"A": 0.1, "B": 0.2, "C": 0.3})          # perfect
        rows += _preds("bad", "s", 0, q, {"A": 0.3, "B": 0.2, "C": 0.1})           # reversed
    rows += _preds("partial", "s", 0, "q1", {"A": 0.1, "B": 0.2, "C": 0.3})
    rows += _preds("partial", "s", 0, "q2", {"A": 0.1, "B": 0.2, "C": 0.3})
    rows += _preds("partial", "s", 0, "q3", {"A": 0.0, "B": 0.0, "C": 0.0}, abstain=True)
    rows += _preds("partial", "s", 0, "q4", {"A": 0.0, "B": 0.0, "C": 0.0}, abstain=True)
    pq = mm.per_query_table(pd.DataFrame(rows), items)
    cs = mm.common_subset(pq, ["good", "bad", "partial"])["s"]
    assert cs["n"] == 2 and cs["query_ids"] == ["q1", "q2"]
    agg = mm.aggregate(cs["per_query"])
    assert agg["good"]["s"]["top1_hit"]["mean"] == 1.0 and agg["bad"]["s"]["top1_hit"]["mean"] == 0.0
    pb = mm.paired_bootstrap(pq, "good", "bad")["s"]
    assert pb["n"] == 4 and pb["top1_hit"]["diff"] == 1.0 and pb["top1_hit"]["beats"] and pb["c_index"]["lo"] > 0
    same = mm.paired_bootstrap(pq, "good", "good")["s"]
    assert same["top1_hit"]["diff"] == 0.0 and not same["top1_hit"]["beats"]
    assert mm.paired_bootstrap(pq, "good", "partial")["s"]["n"] == 2
