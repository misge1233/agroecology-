"""E7 hybrids: nested selection, no outer-fold leakage (canary), numbers from M1 v2 only."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from model.engines.base import RankRequest
from model.harness.mask import Mask
from model.m1 import data as md
from model.m1.engine import M1Config
from model.m1.test_m1 import COMPONENTS, FAMILY, OUTCOME_GROUP, synthetic_store
from model.m3 import engine as m3

FAST = M1Config(tune=False, select=False, inner_folds=3)
CTX = {"ctx_precip_annual": 900.0, "ctx_elevation": 1600.0, "ctx_aez_belt": 6, "release": "ET/2026.1"}


def _cells(store: pd.DataFrame) -> pd.DataFrame:
    rows = md.training_rows(store, Mask.empty(), md.DataConfig(), OUTCOME_GROUP)
    return md.pooled_items(rows)


def _llm(items: pd.DataFrame, flip: set[str] = frozenset(), noise: float = 0.3, seed: int = 0) -> dict:
    """A noisy-but-informative LLM ranking per cell; cells in ``flip`` get the reversed truth."""
    rng = np.random.default_rng(seed)
    out = {}
    for qk, g in items.groupby("qkey"):
        y = g["y"].to_numpy(float) + rng.normal(0, noise, len(g))
        if qk in flip:
            y = -g["y"].to_numpy(float)
        order = np.argsort(-y)
        scores = {str(g["practice_id"].iloc[i]): float(len(g) - r) for r, i in enumerate(order)}
        out[qk] = {"query_id": qk, "valid": True, "abstained": False, "scores": scores}
    return out


def _engine(mode: str, llm: dict) -> m3.M3Engine:
    return m3.M3Engine(mode, llm, {"q": next(iter(llm))}, OUTCOME_GROUP, FAMILY, COMPONENTS, m1_config=FAST)


@pytest.mark.parametrize("mode", ["stack", "gate"])
def test_held_out_query_llm_ranking_never_changes_the_inner_choice(mode):
    """Outer-fold leakage canary: the held-out cell's LLM ranking (perfect or reversed) must not
    change anything learned in the fold; it may only change that cell's own test ranking."""
    store = synthetic_store()
    items = _cells(store)
    held = [k for k in items["qkey"].unique() if k.startswith("10.1/g03")]
    assert held
    mask = Mask.from_groups(["10.1/g03"], store)
    a, b = _engine(mode, _llm(items)), _engine(mode, _llm(items, flip=set(held)))
    a.fit(store, mask)
    b.fit(store, mask)
    fa, fb = a.fold_log[-1], b.fold_log[-1]
    assert fa["n_llm_queries_inner"] >= m3.MIN_SELECT_QUERIES
    assert fa == fb and (a.choice, a.threshold) == (b.choice, b.threshold)
    # the M1 v2 part is identical too: same numbers for the held-out cell
    qk = held[0]
    cands = sorted(items.loc[items["qkey"] == qk, "practice_id"].astype(str))
    req = RankRequest("q", dict(CTX), [], "YIELD", cands, "maize", {}, mask, 1, "productivity")
    a.qkey_of_query, b.qkey_of_query = {"q": qk}, {"q": qk}
    ra, rb = a.rank(req), b.rank(req)
    assert [(i.est_lrr, i.lo, i.hi, i.citations) for i in ra] == [(i.est_lrr, i.lo, i.hi, i.citations) for i in rb]


@pytest.mark.parametrize("mode", ["stack", "gate"])
def test_masked_canary_study_and_its_llm_entry_change_nothing(mode):
    """A held-out canary study with an absurd effect and its own LLM entry: the fold's learned
    choices equal those of the store without the canary."""
    clean, with_canary = synthetic_store(), synthetic_store(canary=True)
    items_c = _cells(with_canary)
    llm = _llm(items_c)
    a, b = _engine(mode, llm), _engine(mode, llm)
    a.fit(clean, Mask.from_groups(["10.1/g03"], clean))
    b.fit(with_canary, Mask.from_groups(["10.1/g03", "10.1/canary"], with_canary))
    assert a.fold_log[-1] == b.fold_log[-1]


def test_numbers_come_from_m1_and_the_gate_orders_by_the_llm_when_evidence_is_thin():
    store = synthetic_store()
    items = _cells(store)
    qk = next(k for k in items["qkey"].unique() if k.startswith("10.1/g05"))
    cands = sorted(items.loc[items["qkey"] == qk, "practice_id"].astype(str))
    llm = _llm(items)
    llm[qk]["scores"] = {p: float(i + 1) for i, p in enumerate(cands)}  # the LLM puts the last candidate first
    mask = Mask.from_groups(["10.1/g05"], store)
    eng = _engine("gate", llm)
    eng.qkey_of_query = {"q": qk}
    eng.fit(store, mask)
    req = RankRequest("q", dict(CTX), [], "YIELD", cands, "maize", {}, mask, 1, "productivity")
    base = {i["practice_id"]: i for i in eng.m1.rank(req.context, cands, "YIELD", "productivity", "maize", {}, qkey="q")}
    eng.threshold = 10**6  # every query is "thin": the LLM order is used
    out = {i.practice_id: i for i in eng.rank(req)}
    assert max(out.values(), key=lambda i: i.score).practice_id == cands[-1] and eng.query_log[-1]["llm_ordered"]
    for p in cands:
        assert (out[p].est_lrr, out[p].lo, out[p].hi, out[p].citations, out[p].lead_source) == \
               (base[p]["est_lrr"], base[p]["lo"], base[p]["hi"], base[p]["citations"], base[p]["lead_source"])
    eng.threshold = 0  # dense: M1 v2's order
    out = {i.practice_id: i for i in eng.rank(req)}
    assert [out[p].score for p in cands] == [base[p]["score"] for p in cands] and not eng.query_log[-1]["llm_ordered"]
    llm[qk]["abstained"] = True  # an abstained LLM answer never orders the query
    eng.llm = llm
    eng.threshold = 10**6
    out = {i.practice_id: i for i in eng.rank(req)}
    assert [out[p].score for p in cands] == [base[p]["score"] for p in cands]


def test_stack_rank_average_and_density_by_hand():
    f = pd.DataFrame({"qkey": ["q"] * 3, "reg": [0.1, 0.3, 0.2], "rank": [3.0, 1.0, 2.0], "matched": [np.nan] * 3,
                      "prior": [0.0, 0.2, 0.1], "llm": [1.0, 2.0, 3.0]})
    # ranks (1 = worst): reg 1,3,2; rank 3,1,2; prior 1,3,2; llm 1,2,3 at weight 2 -> (5 + 2 x llm) / 5
    assert m3.llm_stack_scores(f, 2.0).tolist() == pytest.approx([7 / 5, 11 / 5, 12 / 5])
    pool = pd.DataFrame({"practice_id": ["A", "A", "A", "B", "B"], "outcome_id": ["Y", "Y", "Z", "Z", "Z"],
                         "objective_group": ["g"] * 5, "group": ["s1", "s2", "s3", "s1", "s4"]})
    # A: 2 groups for Y (< 3) -> objective group: 3; B: 0 for Y -> objective group: 2; median 2.5
    assert m3.density(pool, ["A", "B"], "Y", "g") == 2.5
    assert m3.qkey_of("10.1/x", "9.1,38.2", "YIELD", None, "control") == "10.1/x\x1f9.1,38.2\x1fYIELD\x1f\x1fcontrol"
