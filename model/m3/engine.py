"""The E7 hybrid engines ``m3_stack`` and ``m3_gate`` (brief Part B, pre-registered 12 Nov 2026).

Both fit Methodology 1 v2 exactly as E5 (``M1Config()`` with ``keep_inner``) inside the outer
training fold and read its inner out-of-fold component predictions of the training queries.
The LLM ranking is the fold-independent ``m2_zero`` answer of ``gpt-4.1-mini`` (E6): a score
per candidate from the rank position, *valid* when the answer passed validation and
*abstained* when any candidate was classed ``unknown``. It is available for the ET queries
only, so on the inner folds it exists for the training queries that are ET queries.

* **B1 ``m3_stack``**: the inner selection chooses among ``e5`` (M1 v2 as fitted, its own
  stacker), ``llm_w1`` and ``llm_w2`` (rank averaging over the four E5 components plus the
  LLM ranking at weight 1 or 2; the LLM enters where its answer is valid), scored by the mean
  of the inner top-1 hit and the pooled C-index; ties go to the earlier configuration.
* **B2 ``m3_gate``**: per query, M1 v2's order when evidence is dense, else the LLM order
  (M1 v2 where the LLM abstained or was invalid). Density is the median, over the query's
  candidates, of the distinct training study groups that report the practice for the query's
  outcome (for the objective group when fewer than 3 groups report the outcome): the pool
  M1 v2's matched-studies estimate draws from. The threshold is chosen among 2, 3 and 5 on
  the inner folds (density from each inner fold's training items) by the same score; ties go
  to the higher threshold (closer to M1 v2).

The selection is scored on the inner training queries that have a valid LLM ranking (the
configurations differ only there); with fewer than 10 such queries the fold keeps ``e5`` /
threshold 5 (recorded). Numbers, intervals, lead source and citations are M1 v2's.
"""
from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd

from model.engines.base import RankedItem, RankRequest
from model.harness import RUNS_DIR
from model.harness.mask import Mask
from model.m1 import inner as mi
from model.m1 import stack as st
from model.m1.engine import M1Config, M1Engine

CONFIGS = ("e5", "llm_w1", "llm_w2")
LLM_WEIGHT = {"llm_w1": 1.0, "llm_w2": 2.0}
THRESHOLDS = (2, 3, 5)
MIN_SELECT_QUERIES = 10
K_MIN = 3
LLM_RUN = "e6_m2_zero__gpt-4.1-mini_et"
LLM_METHOD = "m2_zero__gpt-4.1-mini"


def qkey_of(group: Any, site: Any, outcome_id: Any, crop: Any, comparator_class: Any) -> str:
    """The pooled-item key of :func:`model.m1.data.pooled_items` for a harness query's cell."""
    return "\x1f".join([str(group), str(site), str(outcome_id), str(crop) if isinstance(crop, str) and crop else "",
                        str(comparator_class)])


def load_llm_rankings(queries: pd.DataFrame, run_id: str = LLM_RUN, method: str = LLM_METHOD,
                      runs_dir: Path = RUNS_DIR) -> dict[str, dict[str, Any]]:
    """``qkey -> {query_id, valid, abstained, scores}`` from the E6 run (fold-independent)."""
    p = pd.read_parquet(runs_dir / run_id / "predictions.parquet")
    p = p[p["method"] == method]
    valid = {}
    resp = runs_dir / run_id / "responses.jsonl"
    for line in resp.read_text(encoding="utf-8").splitlines():
        if line.strip():
            e = json.loads(line)
            valid[e["query_id"]] = bool(e.get("valid"))
    keys = {str(r.query_id): qkey_of(r.group, r.site, r.outcome_id, r.crop, r.comparator_class) for r in queries.itertuples()}
    out: dict[str, dict[str, Any]] = {}
    for qid, g in p.groupby("query_id"):
        qid = str(qid)
        if qid not in keys:
            continue
        out[keys[qid]] = {"query_id": qid, "valid": valid.get(qid, False), "abstained": bool(g["abstain"].any()),
                          "scores": {str(a): float(b) for a, b in zip(g["practice_id"], g["score"])}}
    return out


def e5_scores(stacker: st.Stacker, frame: pd.DataFrame) -> np.ndarray:
    """M1 v2's own combination (its fitted stacker) of the component columns of ``frame``."""
    if stacker.chosen == "ridge":
        return stacker._ridge_scores(frame)
    return st.Stacker._rank_scores(frame, stacker.chosen)


def llm_stack_scores(frame: pd.DataFrame, weight: float) -> np.ndarray:
    """Rank averaging over the four E5 components plus the LLM ranking (``llm`` column) at ``weight``."""
    return st.weighted_rank_average(frame, st.RANK_SPECS["rank_avg"] + (("llm", float(weight)),))


def density(pool: pd.DataFrame, candidates: list[str], outcome_id: str, objective_group: str) -> float:
    """Median over candidates of the distinct training groups reporting the practice for the
    outcome (the objective group when fewer than ``K_MIN`` groups report the outcome)."""
    if pool.empty:
        return 0.0
    out = []
    for pid in candidates:
        sel = pool[pool["practice_id"] == pid]
        n = sel.loc[sel["outcome_id"] == outcome_id, "group"].nunique()
        if n < K_MIN:
            n = sel.loc[sel["objective_group"] == objective_group, "group"].nunique()
        out.append(n)
    return float(np.median(out)) if out else 0.0


def _score(frame: pd.DataFrame, pred: np.ndarray) -> tuple[float, dict[str, float]]:
    s = mi.score_items(frame, pred)
    v = 0.5 * (s["top1"] + s["c_pooled"])
    return (float(v) if np.isfinite(v) else float("-inf")), s


class M3Engine:
    """``mode = "stack"`` (B1) or ``"gate"`` (B2) over a fitted M1 v2."""

    def __init__(self, mode: str, llm: Mapping[str, Mapping[str, Any]], qkey_of_query: Mapping[str, str],
                 outcome_group: Mapping[str, str], family_of: Mapping[str, str], components_of: Mapping[str, list[str]],
                 belt_code_of: Mapping[str, int] | None = None, m1_config: M1Config | None = None) -> None:
        if mode not in ("stack", "gate"):
            raise ValueError(f"unknown M3 mode {mode!r}")
        self.mode = mode
        self.name = f"m3_{mode}"
        self.llm = {k: dict(v) for k, v in llm.items()}
        self.qkey_of_query = dict(qkey_of_query)
        self.maps = dict(outcome_group=dict(outcome_group), family_of=dict(family_of),
                         components_of={k: list(v) for k, v in components_of.items()}, belt_code_of=dict(belt_code_of or {}))
        self.m1_config = replace(m1_config or M1Config(), keep_inner=True)
        self.m1: M1Engine | None = None
        self.choice: str = "e5"
        self.threshold: int = THRESHOLDS[-1]
        self.fold_log: list[dict[str, Any]] = []
        self.query_log: list[dict[str, Any]] = []
        self.mask = Mask.empty()

    # ------------------------------------------------------------ helpers
    def _llm_valid(self, qkey: str) -> dict[str, Any] | None:
        e = self.llm.get(qkey)
        return e if e and e.get("valid") else None

    def _with_llm(self, frame: pd.DataFrame) -> pd.DataFrame:
        f = frame.copy()
        vals = []
        for q, p in zip(f["qkey"], f["practice_id"]):
            e = self._llm_valid(str(q))
            vals.append(e["scores"].get(str(p), np.nan) if e else np.nan)
        f["llm"] = vals
        return f

    # ------------------------------------------------------------ fit (nested)
    def fit(self, train_rows: pd.DataFrame, mask: Mask) -> None:
        self.mask = mask
        self.m1 = M1Engine(self.m1_config, **self.maps)
        summary = self.m1.fit(train_rows, mask)
        inner = self.m1.inner or {}
        oof, items, fold_of_item = inner["oof"], inner["items"], inner["fold_of_item"]
        oof = self._with_llm(oof)
        covered = oof.groupby("qkey")["llm"].transform(lambda s: bool(np.isfinite(s.to_numpy(float)).all()))
        sub = oof[covered.astype(bool)]
        n_q = int(sub.groupby("qkey").size().ge(2).sum())
        rec: dict[str, Any] = {"n_rows": summary.get("n_rows"), "m1_stacker": self.m1.stacker.chosen if self.m1.stacker else None,
                               "n_llm_queries_inner": n_q}
        if n_q < MIN_SELECT_QUERIES:
            self.choice, self.threshold = "e5", THRESHOLDS[-1]
            rec.update({"choice": self.choice, "threshold": self.threshold, "note": "too few LLM-covered inner queries"})
            self.fold_log.append(rec)
            return
        base = e5_scores(self.m1.stacker, sub)
        if self.mode == "stack":
            scores = {"e5": _score(sub, base)}
            for c in CONFIGS[1:]:
                scores[c] = _score(sub, llm_stack_scores(sub, LLM_WEIGHT[c]))
            self.choice = max(CONFIGS, key=lambda c: (scores[c][0], -CONFIGS.index(c)))
            rec.update({"choice": self.choice, "scores": {c: {"selection": v[0], **v[1]} for c, v in scores.items()}})
        else:
            fold_sub = pd.Series(fold_of_item, index=items.index).loc[sub.index].to_numpy()
            dens = np.zeros(len(sub))
            for f in np.unique(fold_sub):
                pool = items[np.asarray(fold_of_item) != f]
                block = sub[fold_sub == f]
                for qk, idx in block.groupby("qkey").indices.items():
                    b = block.iloc[idx]
                    d = density(pool, b["practice_id"].astype(str).tolist(), str(b["outcome_id"].iloc[0]),
                                str(b["objective_group"].iloc[0]))
                    dens[np.flatnonzero(fold_sub == f)[idx]] = d
            usable = np.array([bool(self.llm[str(q)]["valid"] and not self.llm[str(q)]["abstained"]) for q in sub["qkey"]])
            llm = sub["llm"].to_numpy(float)
            scores = {}
            for t in THRESHOLDS:
                pred = np.where(usable & (dens < t), llm, base)
                scores[t] = _score(sub, pred)
            self.threshold = max(THRESHOLDS, key=lambda t: (scores[t][0], t))
            rec.update({"threshold": self.threshold, "scores": {str(t): {"selection": v[0], **v[1]} for t, v in scores.items()},
                        "share_llm_ordered_inner": {str(t): float(np.mean([(u and d < t) for u, d in zip(usable, dens)])) for t in THRESHOLDS}})
        self.fold_log.append(rec)

    # ------------------------------------------------------------ rank
    def rank(self, req: RankRequest) -> list[RankedItem]:
        assert self.m1 is not None, "fit first"
        group = req.objective_group or self.maps["outcome_group"].get(req.outcome_id, "other")
        items = self.m1.rank(req.context, req.candidates, req.outcome_id, group, req.crop, req.user_attrs, qkey=req.query_id)
        m1_scores = np.array([it["score"] for it in items], float)
        qkey = self.qkey_of_query.get(req.query_id, "")
        e = self._llm_valid(qkey)
        used_llm, scores = False, m1_scores
        if self.mode == "stack" and self.choice != "e5" and e is not None:
            frame = pd.DataFrame({"qkey": req.query_id, "practice_id": req.candidates})
            for c in st.COMPONENTS:
                frame[c] = [np.nan if it["components"].get(c) is None else it["components"][c] for it in items]
            frame["llm"] = [e["scores"].get(p, np.nan) for p in req.candidates]
            scores = llm_stack_scores(frame, LLM_WEIGHT[self.choice])
            used_llm = True
        elif self.mode == "gate" and e is not None and not e["abstained"]:
            pool = self.m1.matched.sites if self.m1.matched is not None else (self.m1.inner or {}).get("items", pd.DataFrame())
            d = density(pool, list(req.candidates), req.outcome_id, group)
            if d < self.threshold:
                scores = np.array([e["scores"].get(p, np.nan) for p in req.candidates], float)
                used_llm = bool(np.isfinite(scores).all())
                if not used_llm:
                    scores = m1_scores
            self.query_log.append({"query_id": req.query_id, "density": d, "threshold": self.threshold, "llm_ordered": used_llm})
        if self.mode == "stack":
            self.query_log.append({"query_id": req.query_id, "choice": self.choice, "llm_ordered": used_llm})
        return [RankedItem(it["practice_id"], float(s), it["est_lrr"], it["lo"], it["hi"], False, it["lead_source"],
                           list(it["citations"])) for it, s in zip(items, scores)]

    def params(self) -> dict[str, Any]:
        return {"mode": self.mode, "llm_source": f"{LLM_RUN}:{LLM_METHOD}", "configs": list(CONFIGS), "thresholds": list(THRESHOLDS),
                "selection": "mean of inner top-1 and pooled C-index on LLM-covered inner training queries",
                "folds": list(self.fold_log),
                "share_llm_ordered": (float(np.mean([q["llm_ordered"] for q in self.query_log])) if self.query_log else None)}
