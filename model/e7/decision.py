"""The E7 Part C decision branches, as code (pre-registered 12 Nov 2026).

The brief's branches are applied in order; the first that holds decides. Points the brief
leaves open were fixed here **before any Part A result was read** (12 Nov 2026):

* the validity conditions are tested on ``gpt-4.1-mini`` (the model whose result is under
  examination and the only one the hybrids use); ``gpt-4o-mini`` is reported beside it;
* "within 0.02" compares point estimates (mean top-1 hit, mean C-index) under **full
  coverage** (abstentions filled by the practice prior, as every E5 to E7 headline), 375 ET
  queries, spatial repetition 0 (the no-evidence variants do not depend on the folds);
* the mean Kendall tau of ``m2_swap`` against ``m2_zero`` is over the queries both answered
  validly;
* identification rate "above 25 %" and title lift "exceeds +0.10" compare point estimates;
  "interval excludes zero" means the bootstrap 95 % lower bound is above zero;
* "beats" / "better" (branches 2 and 3) is the E5.1 rule: the paired 95 % interval of the
  difference excludes zero on the positive side for top-1 **or** C-index, and neither
  metric's interval lies entirely below zero; spatial split, full coverage, 5 x 5;
* branch 3: a hybrid is a candidate only if it beats M1 v2; if both do and neither beats the
  other, ``m3_gate`` is preferred (it calls the LLM only on thin-evidence queries; M1 v2's
  order everywhere else); if none beats M1 v2, M1 v2 (the brief's tie rule).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

MARGIN = 0.02
TAU_MIN = 0.8
ID_RATE_MAX = 0.25
LIFT_MAX = 0.10


@dataclass
class Decision:
    branch: int
    design: str
    llm_in_ranking: bool
    reasons: list[str] = field(default_factory=list)
    checks: dict[str, Any] = field(default_factory=dict)


def beats(pair: dict[str, Any] | None) -> bool:
    """E5.1 rule on a paired result ``{metric: {diff, lo, hi}}`` oriented as candidate minus other."""
    if not pair:
        return False
    up = any(pair[k]["lo"] is not None and pair[k]["lo"] > 0 for k in ("top1_hit", "c_index"))
    down = any(pair[k]["hi"] is not None and pair[k]["hi"] < 0 for k in ("top1_hit", "c_index"))
    return up and not down


def within(a: dict[str, float], b: dict[str, float], margin: float = MARGIN) -> bool:
    """Both differences at most ``margin`` (inclusive; 1e-9 absorbs floating-point error)."""
    return all(abs(a[k] - b[k]) <= margin + 1e-9 for k in ("top1_hit", "c_index"))


def decide(recall: dict[str, Any], names: dict[str, float], swap: dict[str, float], zero: dict[str, float],
           swap_tau: float, gate_vs_m1: dict[str, Any] | None, stack_vs_m1: dict[str, Any] | None,
           gate_vs_stack: dict[str, Any] | None, stack_vs_gate: dict[str, Any] | None) -> Decision:
    """Apply the branches. ``recall``: identification rate and title lift with intervals;
    ``names``/``swap``/``zero``: full-coverage top-1 and C-index; pairs oriented first minus second."""
    rate = recall["identification_rate"][0]
    lift, lift_lo = recall["title_lift_top1"][0], recall["title_lift_top1"][1]
    checks = {"identification_rate": rate, "title_lift": lift, "title_lift_lo": lift_lo,
              "names_minus_zero": {k: names[k] - zero[k] for k in ("top1_hit", "c_index")},
              "swap_minus_zero": {k: swap[k] - zero[k] for k in ("top1_hit", "c_index")}, "swap_tau": swap_tau,
              "gate_beats_m1": beats(gate_vs_m1), "stack_beats_m1": beats(stack_vs_m1)}
    # 1. recall dominates
    if rate > ID_RATE_MAX or (lift_lo > 0 and lift > LIFT_MAX):
        why = []
        if rate > ID_RATE_MAX:
            why.append(f"the model named the published study for {rate:.0%} of the probe queries (threshold 25 %)")
        if lift_lo > 0 and lift > LIFT_MAX:
            why.append(f"adding the study's title raised top-1 by {lift:+.3f} with an interval above zero (threshold +0.10)")
        return Decision(1, "m1_v2", False, why + ["the LLM is not used for ranking; production ranking is M1 v2; the hybrid "
                                                  "waits for the fresh_2024plus set"], checks)
    # 2. context not used
    names_close = within(names, zero)
    swap_close = within(swap, zero) and swap_tau > TAU_MIN
    if names_close or swap_close:
        why = []
        if names_close:
            why.append("hiding the farm context and crop changed top-1 and C-index by at most 0.02")
        if swap_close:
            why.append(f"giving each query the most different farm context changed top-1 and C-index by at most 0.02 and "
                       f"left the rankings nearly unchanged (mean Kendall tau {swap_tau:.2f} > 0.8)")
        if beats(gate_vs_m1):
            return Decision(2, "m3_gate", True, why + ["the LLM is a generic prior; m3_gate beats M1 v2 on the spatial split, "
                                                       "so it enters only on thin-evidence queries"], checks)
        return Decision(2, "m1_v2", False, why + ["the LLM is a generic prior; m3_gate does not beat M1 v2 on the spatial "
                                                  "split with an interval excluding zero, so production ranking is M1 v2"], checks)
    # 3. context used, no recall signal
    why = ["the recall probes stayed under their thresholds and the model's rankings depend on the farm context"]
    gate_ok, stack_ok = beats(gate_vs_m1), beats(stack_vs_m1)
    if gate_ok and stack_ok:
        if beats(stack_vs_gate):
            return Decision(3, "m3_stack", True, why + ["both hybrids beat M1 v2 and m3_stack beats m3_gate"], checks)
        return Decision(3, "m3_gate", True, why + ["both hybrids beat M1 v2; m3_stack does not beat m3_gate, which calls "
                                                   "the LLM only on thin-evidence queries"], checks)
    if gate_ok:
        return Decision(3, "m3_gate", True, why + ["m3_gate beats M1 v2 on the spatial split; m3_stack does not"], checks)
    if stack_ok:
        return Decision(3, "m3_stack", True, why + ["m3_stack beats M1 v2 on the spatial split; m3_gate does not"], checks)
    return Decision(3, "m1_v2", False, why + ["neither hybrid beats M1 v2 on the spatial split with an interval excluding "
                                              "zero; ties go to M1 v2 (cheaper, deterministic, no external call)"], checks)
