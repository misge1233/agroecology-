"""Serving the E7 decision: the ``m3_gate`` ordering over a fitted M1 v2 (Part D).

The decision of E7 (branch 2, pre-registered) lets the language model order the practices of
**thin-evidence** requests only; every number, interval, lead source and citation stays
M1 v2's. :class:`GateRanker` does this for one request:

1. M1 v2 ranks the candidates (scores, effect estimates, conformal 80 % intervals, citations);
2. density = the median, over the candidates, of distinct training study groups reporting the
   practice for the outcome (objective group below 3): :func:`model.m3.engine.density` on the
   M1 v2 artifact's matched-studies sites;
3. density at or above the served threshold: M1 v2's order, no call;
4. otherwise the ``m2_zero`` prompt of the evaluation (same template, ``gpt-4.1-mini``) is
   sent once per (rendered context, objective, crop, candidate set) and cached; within the
   timeout (8 s) and when the answer is valid and classes no candidate ``unknown``, the
   practices are ordered by the model's ranking; on timeout, error, budget, invalid or
   abstained answers the order falls back to M1 v2's. The cost of every call is logged.

``python -m model.m3.serve --write-config`` writes ``model/artifacts/m3_gate/config.json``
from the E7 run (threshold by the majority-of-folds rule, model, prompt version and hash).
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import datetime as _dt
import json
import logging
import time
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

from model.engines.base import RankRequest
from model.harness import REPO_ROOT, RUNS_DIR
from model.harness.mask import Mask
from model.m2 import prompt as pm
from model.m2.engine import M2Engine
from model.m3.engine import LLM_METHOD, THRESHOLDS, density

logger = logging.getLogger(__name__)

ARTIFACT_DIR = REPO_ROOT / "model" / "artifacts" / "m3_gate"
LLM_MODEL = "gpt-4.1-mini"
TIMEOUT_S = 8.0
_POOL = cf.ThreadPoolExecutor(max_workers=4, thread_name_prefix="m3-llm")


def write_config(run_id: str = "e7_m3_gate", out_dir: Path = ARTIFACT_DIR) -> Path:
    """The served gate: the threshold chosen in the majority of the E7 outer fits."""
    cfg = json.loads((RUNS_DIR / run_id / "config.json").read_text(encoding="utf-8"))
    folds = cfg["methods"]["m3_gate"]["folds"]
    votes = Counter(int(f["threshold"]) for f in folds)
    threshold = max(sorted(votes), key=lambda t: (votes[t], t))  # ties: the higher threshold (closer to M1 v2)
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {"engine": "m3_gate", "built_utc": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
               "threshold": threshold, "threshold_votes": {str(k): v for k, v in sorted(votes.items())},
               "thresholds_considered": list(THRESHOLDS), "llm_model": LLM_MODEL, "llm_variant": "m2_zero",
               "llm_source_in_evaluation": LLM_METHOD, "prompt_version": pm.PROMPT_VERSION, "prompt_hash": pm.prompt_hash(),
               "timeout_s": TIMEOUT_S, "density": "median distinct training groups per candidate (outcome; objective group below 3)",
               "numbers_from": "m1_v2 (model/artifacts/m1_v2)", "decision": "E7 Part C branch 2", "run_id": run_id}
    p = out_dir / "config.json"
    p.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
    return p


def load_config(out_dir: Path = ARTIFACT_DIR) -> dict[str, Any]:
    p = Path(out_dir) / "config.json"
    if not p.exists():
        raise RuntimeError(f"m3 gate config {p} is missing; build it with `python -m model.m3.serve --write-config`")
    return json.loads(p.read_text(encoding="utf-8"))


class GateRanker:
    """M1 v2 numbers, the LLM order on thin-evidence requests (see module doc)."""

    def __init__(self, m1_engine: Any, config: Mapping[str, Any], client: Any, maps: Mapping[str, Any],
                 timeout_s: float | None = None) -> None:
        self.m1 = m1_engine
        self.config = dict(config)
        self.threshold = float(self.config["threshold"])
        self.client = client
        self.timeout_s = float(timeout_s if timeout_s is not None else self.config.get("timeout_s", TIMEOUT_S))
        self.maps = dict(maps)

    def _prompter(self) -> M2Engine:
        """A fresh ``m2_zero`` prompter per request (its log is per request; thread-safe)."""
        eng = M2Engine("m2_zero", self.client, **self.maps, mode="call", name="m3_gate_llm")
        eng.fit(None, Mask.empty())  # m2_zero uses no evidence: nothing is fitted
        return eng

    def density_of(self, candidates: list[str], outcome_id: str, group: str) -> float:
        sites = getattr(getattr(self.m1, "matched", None), "sites", None)
        if sites is None:
            return 0.0
        return density(sites, list(candidates), outcome_id, group)

    def rank(self, context: Mapping[str, Any], candidates: list[str], outcome_id: str, objective_group: str | None,
             crop: str | None, attrs: Mapping[str, Any] | None = None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        group = objective_group or "other"
        items = self.m1.rank(dict(context), list(candidates), outcome_id, objective_group, crop, attrs, qkey="api")
        d = self.density_of(list(candidates), outcome_id, group)
        info: dict[str, Any] = {"engine": "m3_gate", "source": "m1_v2", "density": d, "threshold": self.threshold,
                                "llm": None}
        if d >= self.threshold or len(candidates) < 2:
            return items, info
        req = RankRequest("api", dict(context), [], outcome_id, list(candidates), crop, dict(attrs or {}), Mask.empty(), 1, group)
        t0 = time.time()
        prompter = self._prompter()
        try:
            ranked = _POOL.submit(prompter.rank, req).result(timeout=self.timeout_s)
            entry = prompter.log[-1] if prompter.log else {}
            cost = sum(float(a.get("cost_usd") or 0) for a in entry.get("attempts", []) if not a.get("from_cache"))
            cached = all(a.get("from_cache") for a in entry.get("attempts", [])) if entry.get("attempts") else False
            if not entry.get("valid"):
                outcome = "invalid"
            elif any(r.abstain for r in ranked):
                outcome = "abstained"
            else:
                outcome = "used"
        except cf.TimeoutError:
            ranked, outcome, cost, cached = None, "timeout", 0.0, False
        except Exception as exc:  # noqa: BLE001 - budget, network, key: the M1 v2 order stands
            ranked, outcome, cost, cached = None, f"error:{type(exc).__name__}", 0.0, False
        info["llm"] = {"model": getattr(self.client, "model", None), "outcome": outcome, "from_cache": cached,
                       "latency_s": round(time.time() - t0, 3), "cost_usd": round(cost, 6)}
        logger.info("m3 gate: density %.1f < %.0f, llm %s (cache %s, %.2f s, %.6f USD)", d, self.threshold, outcome,
                    cached, info["llm"]["latency_s"], cost)
        if outcome != "used":
            return items, info
        score = {r.practice_id: r.score for r in ranked}
        info["source"] = "llm_order"
        return [{**it, "score": float(score[it["practice_id"]]), "m1_score": it["score"]} for it in items], info


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="E7 m3_gate serving config")
    ap.add_argument("--write-config", action="store_true")
    ap.add_argument("--run-id", default="e7_m3_gate")
    a = ap.parse_args(argv)
    if a.write_config:
        print(write_config(a.run_id))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
