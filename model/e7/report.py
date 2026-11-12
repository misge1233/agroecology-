"""E7 merges, validity tables, the Part C decision and the methodology comparison report.

``python -m model.e7.report merge`` builds the scored runs every table reads:

* ``e7_validity``: E5 rows (5 x 5) of the baselines and M1 v2, the replicated fold-independent
  ``m2_zero`` of both models and the heuristic baselines (A1, A4);
* ``e7_context``: spatial repetition 0 of ``m2_zero``, ``m2_names`` and ``m2_swap``, both
  models (A2, A3);
* ``e7_all``: every 5 x 5 method on both splits: baselines, M0, M1 v2, E5.1 (post-hoc),
  heuristics, ``m2_zero`` of both models, ``m3_stack`` and ``m3_gate`` (Part B, the decision);
* ``e7_rep0``: spatial repetition 0 of every method including the M2 evidence variants.

``python -m model.e7.report compose`` applies :func:`model.e7.decision.decide` and writes
``model/reports/methodology_comparison_<date>.md`` with ``methodology_comparison_<date>/``
(``metrics.json`` and the PNG figures). Every number is read from the runs.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from model.e7 import decision as dec
from model.harness import REPORTS_DIR, RUNS_DIR
from model.m1 import report as m1r
from model.m2 import report as m2r

Z41 = "m2_zero__gpt-4.1-mini"
LABELS = {
    "practice_prior": "Practice prior (E4)", "nearest_studies": "Nearest studies (E4)", "m0_current+prior": "Current model M0 + prior",
    "m0_current": "Current model M0", "m1_v2": "M1 v2, evidence model (E5)", "m1_v2_e51": "M1 v2 E5.1 (post-hoc, pre-registered 12 Nov)",
    "component_count": "Heuristic: component count", "input_intensity": "Heuristic: input intensity",
    "m2_zero+prior": "M2 no evidence, gpt-4o-mini", f"{Z41}+prior": "M2 no evidence, gpt-4.1-mini",
    "m2_names+prior": "M2 names only, gpt-4o-mini", "m2_names__gpt-4.1-mini+prior": "M2 names only, gpt-4.1-mini",
    "m2_swap+prior": "M2 swapped context, gpt-4o-mini", "m2_swap__gpt-4.1-mini+prior": "M2 swapped context, gpt-4.1-mini",
    "m2_cards+prior": "M2 cards, gpt-4o-mini", "m2_rag+prior": "M2 cards + passages, gpt-4o-mini",
    "m2_graph+prior": "M2 full evidence, gpt-4o-mini", "m2_graph__gpt-4.1-mini+prior": "M2 full evidence, gpt-4.1-mini",
    "m3_stack": "Hybrid m3_stack (B1)", "m3_gate": "Hybrid m3_gate (B2)",
}
ALL_ORDER = ["practice_prior", "nearest_studies", "m0_current+prior", "m1_v2", "m1_v2_e51", "component_count", "input_intensity",
             "m2_zero+prior", f"{Z41}+prior", "m3_stack", "m3_gate"]


# ----------------------------------------------------------------- merges
def merge() -> list[Path]:
    out = [m1r.merge_runs("e7_validity", [("e5_headline", ["m1_v2", "m0_current", "practice_prior"]),
                                          ("e7_m2_zero_5x5", ["m2_zero"]), (f"e7_{Z41}_5x5", [Z41]),
                                          ("e7_heuristics", ["component_count", "input_intensity"])])]
    out.append(m2r.merge_rep0("e7_context", [("e5_headline", ["practice_prior"]), ("e6_m2_zero_et", ["m2_zero"]),
                                             (f"e6_{Z41}_et", [Z41]), ("e7_m2_names_et", ["m2_names"]),
                                             ("e7_m2_names__gpt-4.1-mini_et", ["m2_names__gpt-4.1-mini"]),
                                             ("e7_m2_swap_et", ["m2_swap"]), ("e7_m2_swap__gpt-4.1-mini_et", ["m2_swap__gpt-4.1-mini"])]))
    out.append(m1r.merge_runs("e7_all", [("e5_headline", ["practice_prior", "nearest_studies", "m0_current", "m1_v2"]),
                                         ("e51_m1", ["m1_v2_e51"]), ("e7_heuristics", ["component_count", "input_intensity"]),
                                         ("e7_m2_zero_5x5", ["m2_zero"]), (f"e7_{Z41}_5x5", [Z41]),
                                         ("e7_m3_stack", ["m3_stack"]), ("e7_m3_gate", ["m3_gate"])]))
    out.append(m2r.merge_rep0("e7_rep0", [("e5_headline", ["practice_prior", "m0_current", "m1_v2"]),
                                          ("e7_heuristics", ["component_count", "input_intensity"]),
                                          ("e6_m2_zero_et", ["m2_zero"]), ("e6_m2_cards_et", ["m2_cards"]), ("e6_m2_rag_et", ["m2_rag"]),
                                          ("e6_m2_graph_et", ["m2_graph"]), (f"e6_{Z41}_et", [Z41]),
                                          ("e6_m2_graph__gpt-4.1-mini_et", ["m2_graph__gpt-4.1-mini"]),
                                          ("e7_m2_names_et", ["m2_names"]), ("e7_m2_names__gpt-4.1-mini_et", ["m2_names__gpt-4.1-mini"]),
                                          ("e7_m2_swap_et", ["m2_swap"]), ("e7_m2_swap__gpt-4.1-mini_et", ["m2_swap__gpt-4.1-mini"]),
                                          ("e7_m3_stack", ["m3_stack"]), ("e7_m3_gate", ["m3_gate"])]))
    return out


# ----------------------------------------------------------------- readers
def metrics(run_id: str) -> dict[str, Any]:
    return json.loads((RUNS_DIR / run_id / "metrics.json").read_text(encoding="utf-8"))


def full(run_id: str) -> dict[str, Any]:
    return metrics(run_id)["full_coverage"]["aggregate"]


def point(agg: dict[str, Any], method: str, split: str = "spatial") -> dict[str, float]:
    v = agg[method][split]
    return {k: float(v[k]["mean"]) for k in ("top1_hit", "c_index", "ndcg3", "top1_chance", "coverage80", "width80")
            if k in v and v[k].get("mean") is not None}


def paired(run_id: str, a: str, b: str, split: str = "spatial") -> dict[str, Any] | None:
    """``a`` minus ``b`` with the interval, from a run's paired bootstrap (oriented)."""
    P = metrics(run_id)["paired"]
    key, sign = (f"{a} vs {b}", 1.0) if f"{a} vs {b}" in P else (f"{b} vs {a}", -1.0)
    if key not in P or split not in P[key]:
        return None
    r = P[key][split]
    out: dict[str, Any] = {"n": r["n"]}
    for k in ("top1_hit", "c_index", "ndcg3"):
        v = r[k]
        if v.get("diff") is None:
            out[k] = {"diff": None, "lo": None, "hi": None}
            continue
        lo, hi = sorted([sign * v["lo"], sign * v["hi"]])
        out[k] = {"diff": sign * v["diff"], "lo": lo, "hi": hi}
    return out


def swap_tau(model_suffix: str = "__gpt-4.1-mini") -> dict[str, float]:
    """Mean Kendall tau between the ``m2_swap`` and ``m2_zero`` rankings of the same query."""
    zero = {e["query_id"]: m2r._ranking(e) for e in m2r.responses(f"e6_m2_zero{model_suffix}_et")}
    swap = {e["query_id"]: m2r._ranking(e) for e in m2r.responses(f"e7_m2_swap{model_suffix}_et")}
    taus, top = [], []
    for q, a in swap.items():
        b = zero.get(q)
        if a is None or b is None:
            continue
        top.append(a[0] == b[0])
        t = m2r.kendall_tau(a, b)
        if not math.isnan(t):
            taus.append(t)
    return {"n": len(taus), "mean_tau": float(np.mean(taus)), "top1_agreement": float(np.mean(top))}


def names_tau(model_suffix: str = "__gpt-4.1-mini") -> dict[str, float]:
    zero = {e["query_id"]: m2r._ranking(e) for e in m2r.responses(f"e6_m2_zero{model_suffix}_et")}
    names = {e["query_id"]: m2r._ranking(e) for e in m2r.responses(f"e7_m2_names{model_suffix}_et")}
    taus, top = [], []
    for q, a in names.items():
        b = zero.get(q)
        if a is None or b is None:
            continue
        top.append(a[0] == b[0])
        t = m2r.kendall_tau(a, b)
        if not math.isnan(t):
            taus.append(t)
    return {"n": len(taus), "mean_tau": float(np.mean(taus)), "top1_agreement": float(np.mean(top))}


def recall() -> dict[str, Any]:
    return json.loads((RUNS_DIR / "e7_recall_probes" / "summary.json").read_text(encoding="utf-8"))


def hybrid_params(run_id: str, method: str) -> dict[str, Any]:
    return json.loads((RUNS_DIR / run_id / "config.json").read_text(encoding="utf-8"))["methods"][method]


def apply_decision() -> dec.Decision:
    ctx = full("e7_context")
    sfx = "__gpt-4.1-mini"
    return dec.decide(recall(), point(ctx, f"m2_names{sfx}+prior"), point(ctx, f"m2_swap{sfx}+prior"),
                      point(ctx, f"m2_zero{sfx}+prior"), swap_tau()["mean_tau"],
                      paired("e7_all", "m3_gate", "m1_v2"), paired("e7_all", "m3_stack", "m1_v2"),
                      paired("e7_all", "m3_gate", "m3_stack"), paired("e7_all", "m3_stack", "m3_gate"))


# ----------------------------------------------------------------- figures
def _dot_panel(path: Path, rows: list[tuple[str, dict[str, Any]]], title: str, xlabel_suffix: str) -> Path:
    """Two panels (top-1, C-index): paired difference and 95 % interval per method, zero line."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    surface, ink, muted, grid, series = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df", "#2a78d6"
    fig, axes = plt.subplots(1, 2, figsize=(10, 0.42 * len(rows) + 1.6), sharey=True, facecolor=surface)
    ys = np.arange(len(rows))[::-1]
    for ax, (key, name) in zip(axes, (("top1_hit", "top-1 hit"), ("c_index", "C-index"))):
        ax.set_facecolor(surface)
        ax.axvline(0, color=muted, lw=1, zorder=1)
        for y, (_, r) in zip(ys, rows):
            v = r[key]
            if v["diff"] is None:
                continue
            ax.plot([v["lo"], v["hi"]], [y, y], color=series, lw=2, solid_capstyle="round", zorder=2)
            ax.plot([v["diff"]], [y], "o", ms=8, color=series, mec=surface, mew=2, zorder=3)
        ax.set_xlabel(f"difference in {name} {xlabel_suffix}", color=muted, fontsize=9)
        ax.tick_params(colors=muted, labelsize=9)
        ax.grid(axis="x", color=grid, lw=0.8)
        for s in ("top", "right", "left"):
            ax.spines[s].set_visible(False)
        ax.spines["bottom"].set_color(grid)
    axes[0].set_yticks(ys)
    axes[0].set_yticklabels([lab for lab, _ in rows], color=ink, fontsize=9)
    fig.suptitle(title, x=0.01, ha="left", color=ink, fontsize=11)
    fig.tight_layout()
    fig.savefig(path, dpi=160, facecolor=surface)
    plt.close(fig)
    return path


# ----------------------------------------------------------------- compose
def _f(v: Any, pct: bool = False) -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "-"
    return f"{v:.1%}" if pct else f"{v:.3f}"


def _ci(v: dict[str, Any]) -> str:
    if v["diff"] is None:
        return "-"
    star = " *" if v["lo"] > 0 or v["hi"] < 0 else ""
    return f"{v['diff']:+.3f} [{v['lo']:+.3f}, {v['hi']:+.3f}]{star}"


def headline_table(agg: dict[str, Any], methods: list[str], split: str) -> list[str]:
    L = ["| method | top-1 hit | C-index | NDCG@3 | 80 % coverage | 80 % width |", "|---|---:|---:|---:|---:|---:|"]
    for m in methods:
        if m not in agg or split not in agg[m]:
            continue
        p = point(agg, m, split)
        L.append(f"| {LABELS.get(m, m)} | {_f(p.get('top1_hit'), True)} | {_f(p.get('c_index'))} | {_f(p.get('ndcg3'))} | "
                 f"{_f(p.get('coverage80'), True)} | {_f(p.get('width80'))} |")
    return L


def compose(date: str | None = None) -> Path:
    date = date or _dt.date.today().isoformat()
    out_dir = REPORTS_DIR / f"methodology_comparison_{date}"
    out_dir.mkdir(parents=True, exist_ok=True)
    d = apply_decision()
    allf = full("e7_all")
    rep0 = full("e7_rep0")
    ctx = full("e7_context")
    rc = recall()
    taus = {"gpt-4.1-mini": swap_tau(), "gpt-4o-mini": swap_tau("")}
    ntaus = {"gpt-4.1-mini": names_tau(), "gpt-4o-mini": names_tau("")}
    vs_m1 = {m: paired("e7_all", m, "m1_v2") for m in ("m3_gate", "m3_stack", f"{Z41}+prior", "m2_zero+prior", "component_count",
                                                      "input_intensity", "m1_v2_e51", "m0_current+prior", "practice_prior")}
    study_vs_m1 = {m: paired("e7_all", m, "m1_v2", "study") for m in ("m3_gate", "m3_stack", f"{Z41}+prior", "component_count")}
    other = {"m3_gate vs m3_stack": paired("e7_all", "m3_gate", "m3_stack"),
             "m2_zero 4.1-mini vs component_count": paired("e7_all", f"{Z41}+prior", "component_count"),
             "m3_gate vs m2_zero 4.1-mini": paired("e7_all", "m3_gate", f"{Z41}+prior"),
             "m3_gate vs component_count": paired("e7_all", "m3_gate", "component_count"),
             "m3_gate vs m0_current+prior": paired("e7_all", "m3_gate", "m0_current+prior"),
             "m3_stack vs m2_zero 4.1-mini": paired("e7_all", "m3_stack", f"{Z41}+prior"),
             "m3_stack vs m0_current+prior": paired("e7_all", "m3_stack", "m0_current+prior")}
    hp = {m: hybrid_params(f"e7_{m}", m) for m in ("m3_stack", "m3_gate")}
    from pipelines.evidence import load_fresh

    fresh = load_fresh.status()
    design = d.design
    cal = {s: point(allf, design, s).get("coverage80") for s in ("spatial", "study")}
    cal_ok = all(c is not None and 0.75 <= c <= 0.85 for c in cal.values())
    from model.m2.client import Ledger

    spend = Ledger(Path(__file__).resolve().parents[1] / "m2" / "cache" / "e7" / "ledger.jsonl").total()
    # ---- figures
    fig1 = _dot_panel(out_dir / "fig1_vs_m1v2_spatial.png",
                      [(LABELS[m], vs_m1[m]) for m in ("m3_gate", "m3_stack", f"{Z41}+prior", "m2_zero+prior", "component_count",
                                                       "input_intensity", "m0_current+prior", "practice_prior") if vs_m1[m]],
                      "Each method minus M1 v2: ET queries, spatial split, 5 x 5, full coverage (95 % paired bootstrap)",
                      "vs M1 v2")
    ctx_rows = []
    for m in ("m2_names__gpt-4.1-mini+prior", "m2_swap__gpt-4.1-mini+prior", "m2_names+prior", "m2_swap+prior"):
        base = f"{Z41}+prior" if "4.1" in m else "m2_zero+prior"
        p = paired("e7_context", m, base)
        if p:
            ctx_rows.append((LABELS[m] + " minus no evidence", p))
    fig2 = _dot_panel(out_dir / "fig2_context_tests.png", ctx_rows,
                      "Context tests: hiding or swapping the farm context (spatial repetition 0, full coverage)", "")
    # ---- markdown
    L = [f"# Methodology comparison (E7, {date})", "",
         "Written for the Methodology page (E8) and the manuscript. Every number below is read from the evaluation runs of the "
         "E4 harness (`model/harness/runs/`); `metrics.json` beside this file holds them in machine-readable form.", "",
         "## 1. The protocol in plain words", "",
         "Each test question is one published field trial in Ethiopia: one site, one objective (for example crop yield or soil "
         "loss), one crop and the practices the trial compared. A method sees the site's context, the objective, the crop and the "
         "list of practices, and must put the practice that did best first. The trial's own results are hidden from every method "
         "through every channel: training rows, retrieved passages, the knowledge graph and the prompts of the language model. "
         "There are 375 such questions from 106 study groups.", "",
         "Two ways of hiding trials are used. **Spatial**: whole regions are held out, five times over (5 folds x 5 repetitions), "
         "which tests advice for a place the methods have not seen. **Study**: whole studies are held out the same way. "
         "Scores: **top-1 hit** (the best practice was put first; chance is 39.6 %), **C-index** (the share of practice pairs put "
         "in the right order; 0.5 is chance) and NDCG@3. A method that cannot answer a question is filled by the practice prior "
         "(\"full coverage\"), so every method is scored on every question. Differences between methods are paired query by "
         "query and carry 95 % bootstrap intervals; a difference counts only when its interval excludes zero.", "",
         "Methods: simple baselines (the average effect of each practice; the nearest studies), the current serving model M0, "
         "Methodology 1 (M1 v2: an evidence model trained on 19,753 effect rows with calibrated 80 % intervals), Methodology 2 "
         "(a language model ranking from the same evidence, or from no evidence at all), two heuristics without any model, and "
         "two hybrids in which the language model may change the order while every number still comes from M1 v2.", "",
         "## 2. Headline (ET queries, full coverage, mean of 5 x 5)", "", "*Spatial split*", ""]
    L += headline_table(allf, ALL_ORDER, "spatial")
    L += ["", "*Study split*", ""]
    L += headline_table(allf, ALL_ORDER, "study")
    cs = metrics("e7_all")["common_subset"]
    for split in ("spatial", "study"):
        if split in cs:
            L += ["", f"*Common subset, {split} split: {cs[split]['n']} queries every method answered without the prior fill in "
                      "every repetition (small, because the nearest-studies baseline and M0 often cannot answer; read with "
                      "care)*", "",
                  "| method | top-1 hit | C-index | NDCG@3 |", "|---|---:|---:|---:|"]
            for m in ["practice_prior", "nearest_studies", "m0_current", "m1_v2", "m1_v2_e51", "component_count", "input_intensity",
                      "m2_zero", Z41, "m3_stack", "m3_gate"]:
                v = cs[split]["aggregate"].get(m)
                if v:
                    L.append(f"| {LABELS.get(m, LABELS.get(m + '+prior', m))} | {_f(v['top1_hit']['mean'], True)} | "
                             f"{_f(v['c_index']['mean'])} | {_f(v['ndcg3']['mean'])} |")
    L += ["", "Language-model rows: the no-evidence variants do not depend on the folds, so one answer per question serves all "
          "25 folds (identical rows checked). The evidence variants of M2 ran on spatial repetition 0 only (owner's minimal "
          "design, E6); they are in section 4.", "",
          "## 3. The paired differences that matter (spatial split, 5 x 5, full coverage)", "",
          "![Each method minus M1 v2](methodology_comparison_" + date + "/fig1_vs_m1v2_spatial.png)", "",
          "| comparison | n | top-1 hit | C-index | NDCG@3 |", "|---|---:|---:|---:|---:|"]
    for m, p in vs_m1.items():
        if p:
            L.append(f"| {LABELS.get(m, m)} minus M1 v2 | {p['n']} | {_ci(p['top1_hit'])} | {_ci(p['c_index'])} | {_ci(p['ndcg3'])} |")
    for k, p in other.items():
        if p:
            L.append(f"| {k} | {p['n']} | {_ci(p['top1_hit'])} | {_ci(p['c_index'])} | {_ci(p['ndcg3'])} |")
    L += ["", "*Study split, minus M1 v2:*", "", "| comparison | n | top-1 hit | C-index |", "|---|---:|---:|---:|"]
    for m, p in study_vs_m1.items():
        if p:
            L.append(f"| {LABELS.get(m, m)} | {p['n']} | {_ci(p['top1_hit'])} | {_ci(p['c_index'])} |")
    # ---- rep0 ladder
    L += ["", "## 4. Spatial repetition 0: every method including the M2 evidence variants", "",
          "| method | top-1 hit | C-index | NDCG@3 |", "|---|---:|---:|---:|"]
    for m in ["practice_prior", "m0_current+prior", "m1_v2", "component_count", "input_intensity", "m2_zero+prior", "m2_cards+prior",
              "m2_rag+prior", "m2_graph+prior", f"{Z41}+prior", "m2_graph__gpt-4.1-mini+prior", "m2_names+prior",
              "m2_names__gpt-4.1-mini+prior", "m2_swap+prior", "m2_swap__gpt-4.1-mini+prior", "m3_stack", "m3_gate"]:
        if m in rep0:
            p = point(rep0, m)
            L.append(f"| {LABELS.get(m, m)} | {_f(p['top1_hit'], True)} | {_f(p['c_index'])} | {_f(p['ndcg3'])} |")
    # ---- validity
    a1 = vs_m1[f"{Z41}+prior"]
    L += ["", "## 5. Validity of the language-model result (Part A)", "",
          "E6 found that `gpt-4.1-mini` given no evidence ranked better than every evidence-based method. Three explanations "
          "predict that score: real location-aware knowledge, a generic ordering of practices (including the design of trials, "
          "where combined treatments are usually built to win), or recall of the published studies. The tests below were "
          "fixed before they ran.", "",
          f"**A1, fair reference.** Against M1 v2's five-repetition mean (not repetition 0 only), the no-evidence `gpt-4.1-mini` "
          f"still leads: top-1 {_ci(a1['top1_hit'])}, C-index {_ci(a1['c_index'])} (spatial). On repetition 0 alone (E6) the "
          "top-1 gap was +0.104.", ""]
    zc = {m: point(ctx, m) for m in (f"{Z41}+prior", "m2_names__gpt-4.1-mini+prior", "m2_swap__gpt-4.1-mini+prior",
                                     "m2_zero+prior", "m2_names+prior", "m2_swap+prior")}
    L += ["**A2 and A3, does the model use the farm context?** Spatial repetition 0, full coverage, 375 queries.", "",
          "| model | variant | top-1 hit | C-index | top-1 minus no-evidence | C-index minus no-evidence | Kendall tau vs no-evidence (mean) | same top practice |",
          "|---|---|---:|---:|---:|---:|---:|---:|"]
    for model, sfx in (("gpt-4.1-mini", "__gpt-4.1-mini"), ("gpt-4o-mini", "")):
        z = zc[f"m2_zero{sfx}+prior"]
        L.append(f"| {model} | no evidence (own context) | {_f(z['top1_hit'], True)} | {_f(z['c_index'])} | | | | |")
        for var, tau in (("names", ntaus[model]), ("swap", taus[model])):
            p = zc[f"m2_{var}{sfx}+prior"]
            L.append(f"| {model} | {'names only (no context, no crop)' if var == 'names' else 'most different context'} | "
                     f"{_f(p['top1_hit'], True)} | {_f(p['c_index'])} | {p['top1_hit'] - z['top1_hit']:+.3f} | "
                     f"{p['c_index'] - z['c_index']:+.3f} | {tau['mean_tau']:.2f} (n = {tau['n']}) | {tau['top1_agreement']:.0%} |")
    cc, ii = vs_m1["component_count"], vs_m1["input_intensity"]
    zc_cc = other["m2_zero 4.1-mini vs component_count"]
    L += ["", f"**A4, heuristics without a language model.** Putting the practice with the most components first (ties by the "
          f"practice prior) beats M1 v2 by {_ci(cc['top1_hit'])} top-1 and {_ci(cc['c_index'])} C-index (spatial, 5 x 5); "
          f"ordering by input level beats it by {_ci(ii['top1_hit'])} top-1. The no-evidence `gpt-4.1-mini` minus component "
          f"count: top-1 {_ci(zc_cc['top1_hit'])}, C-index {_ci(zc_cc['c_index'])}: the two cannot be told apart.", "",
          f"**A5, recall probes** (`gpt-4.1-mini`, {rc['n']} queries, one per study group, stratified by objective group and "
          f"source). Identification: the model named the right study (first author and year within one) for "
          f"{rc['identification_rate'][0]:.0%} of them [{rc['identification_rate'][1]:.0%}, {rc['identification_rate'][2]:.0%}]; "
          f"it claimed to know the study for {rc['said_known']:.1%}. Title lift: adding the study's title and DOI changed top-1 "
          f"by {rc['title_lift_top1'][0]:+.3f} [{rc['title_lift_top1'][1]:+.3f}, {rc['title_lift_top1'][2]:+.3f}] on the "
          f"{rc['n_lift_pairs']} queries that had a title or DOI ({rc['title_lift_top1_all80'][0]:+.3f} on all {rc['n_lift_pairs_all80']}).", "",
          f"**A6, fresh test set** (`fresh_2024plus`, Ethiopian trials published after June 2024): **{fresh['status']}**. The loader "
          "(`pipelines/evidence/load_fresh.py`), the query set and a one-fold harness split `fresh` are in place; with at least "
          f"{load_fresh.MIN_QUERIES} queries, A1 and the hybrids run on it with `--query-set fresh_2024plus --split fresh`.", "",
          "![Context tests](methodology_comparison_" + date + "/fig2_context_tests.png)", ""]
    # ---- hybrids
    L += ["## 6. The hybrids (Part B)", "",
          "Both use M1 v2 for every number, interval and citation; the language model (the cached no-evidence `gpt-4.1-mini` "
          "ranking) only changes the order. Their choices are made inside each training fold on M1 v2's inner folds.", ""]
    for m in ("m3_stack", "m3_gate"):
        folds = hp[m].get("folds") or []
        if m == "m3_stack":
            votes = pd.Series([f.get("choice") for f in folds]).value_counts().to_dict()
            L.append(f"- **m3_stack** chose, in the 50 outer fits: {', '.join(f'{k} {v}' for k, v in votes.items())} "
                     "(`e5` = M1 v2 unchanged; `llm_w1`/`llm_w2` = rank averaging with the language model at weight 1 or 2).")
        else:
            votes = pd.Series([f.get("threshold") for f in folds]).value_counts().to_dict()
            L.append(f"- **m3_gate** chose the density threshold {', '.join(f'{k} in {v} fits' for k, v in votes.items())}; the "
                     f"language-model order was used for {_f(hp[m].get('share_llm_ordered'), True)} of the test questions.")
    for m in ("m3_gate", "m3_stack"):
        p = vs_m1[m]
        L.append(f"- {m} minus M1 v2 (spatial): top-1 {_ci(p['top1_hit'])}, C-index {_ci(p['c_index'])}.")
    # ---- calibration
    L += ["", "## 7. Calibration (80 % intervals, held-out effects, 5 x 5)", "", "| method | spatial | study |", "|---|---:|---:|"]
    for m in ("m1_v2", "m1_v2_e51", "m3_stack", "m3_gate", "m0_current+prior", "practice_prior"):
        if m in allf:
            L.append(f"| {LABELS.get(m, m)} | {_f(point(allf, m, 'spatial').get('coverage80'), True)} | "
                     f"{_f(point(allf, m, 'study').get('coverage80'), True)} |")
    L += ["", "The hybrids carry M1 v2's intervals unchanged, so their coverage equals M1 v2's on the same folds. The heuristics and "
          "the language model produce no intervals of their own (their full-coverage rows show the prior fill's intervals only).", ""]
    # ---- cost
    L += ["## 8. Cost and latency", "",
          "| method | model | USD per question | median latency | p95 latency |", "|---|---|---:|---:|---:|"]
    for meth, rid in (("M2 no evidence", "e6_m2_zero_et"), ("M2 no evidence", f"e6_{Z41}_et"), ("M2 full evidence", "e6_m2_graph_et"),
                      ("M2 full evidence", "e6_m2_graph__gpt-4.1-mini_et"), ("M2 names only", "e7_m2_names__gpt-4.1-mini_et"),
                      ("M2 swapped context", "e7_m2_swap__gpt-4.1-mini_et")):
        model = "gpt-4.1-mini" if "4.1" in rid else "gpt-4o-mini"
        c = m2r.cost_latency(m2r.responses(rid), model)
        L.append(f"| {meth} | {model} | {c['usd_per_query']:.5f} | {c['latency_median_s']:.1f} s | {c['latency_p95_s']:.1f} s |")
    L += ["| M1 v2, heuristics | none | 0 (local, no external call) | not measured | |", "",
          f"`m3_gate` in production calls `gpt-4.1-mini` only for thin-evidence requests (the language-model order was used "
          f"for {_f(hp['m3_gate'].get('share_llm_ordered'), True)} of the test questions), once per (rendered context, "
          f"objective, crop, practice list), cached, with an 8 s timeout and the M1 v2 order as fallback. E7 spent "
          f"{spend:.2f} USD of its 20 USD cap.", ""]
    # ---- decision
    L += ["## 9. The decision (Part C, pre-registered branches)", "",
          f"**Branch {d.branch} applied. Production ranking: {LABELS.get(d.design, d.design)}.**", ""]
    L += [f"- {r[0].upper() + r[1:]}." for r in d.reasons]
    if d.design == "m3_gate":
        g_st, g_cc = study_vs_m1["m3_gate"], other["m3_gate vs component_count"]
        L += ["", "What this means, in plain words. The language model's order is the same whatever the farm (it did not change "
              "when the farm context was hidden or replaced), so the gate adds a general ordering of practices where the field "
              "evidence is thin, not location-specific advice. The gain over M1 v2 holds on the spatial split, the split the "
              f"rule uses; on the study split it is top-1 {_ci(g_st['top1_hit'])}, C-index {_ci(g_st['c_index'])}. The "
              f"component-count heuristic, which needs no language model, scores at least as well as the gate (gate minus "
              f"heuristic: top-1 {_ci(g_cc['top1_hit'])}, C-index {_ci(g_cc['c_index'])}); a gate with that heuristic was not "
              "pre-registered and was not run."]
    L += ["", "Branch 1 (recall dominates) is read first: identification above 25 % or a title lift above +0.10 with an interval "
          "excluding zero. Branch 2 (context not used): hiding or swapping the context moves top-1 and C-index by at most 0.02 "
          "(the swap also needs a mean Kendall tau above 0.8). Branch 3 otherwise. How the brief's open points were read (which "
          "model, which coverage, what \"beats\" means) is fixed in `model/e7/decision.py`, written before the results.", "",
          f"Calibration of the chosen design: {_f(cal['spatial'], True)} (spatial) and {_f(cal['study'], True)} (study) of held-out "
          f"effects inside the 80 % intervals: {'within' if cal_ok else 'OUTSIDE'} the 75 to 85 % target.", ""]
    if d.llm_in_ranking:
        L += ["**Doctrine.** The decision lets the language model influence the order of practices; the owner must approve the "
              "amendment drafted in `docs/decisions/evidence_fusion_amendment_DRAFT.md` (not applied).", ""]
    else:
        L += ["**Doctrine.** The decision does not let the language model influence the order of practices: no amendment to "
              "`docs/decisions/evidence_fusion.md` is needed, and none is drafted for adoption.", ""]
    L += ["## 10. Limitations", "",
          "- **The benchmark rewards trial design.** A heuristic that puts the practice with the most components first beats "
          "every evidence-based method, including M1 v2. Trials are usually designed so that the combined treatment wins, so the "
          "within-trial ranking task partly measures that structure rather than advice quality for a new farm. The scores of all "
          "methods should be read with that in mind.",
          f"- **No fresh test set yet.** `fresh_2024plus` is {fresh['status']}; it is the only clean test against recall.",
          "- **M2 evidence variants on one repetition.** They ran on spatial repetition 0 only (owner's minimal design).",
          "- **Deployable models only.** `gpt-4o-mini` and `gpt-4.1-mini` (owner, 12 Nov 2026); frontier models were not tested.",
          "- **One country.** All 375 questions are Ethiopian; the 39 global questions were used only for `m2_graph` in E6.", ""]
    md = REPORTS_DIR / f"methodology_comparison_{date}.md"
    md.write_text("\n".join(L) + "\n", encoding="utf-8")
    payload = {"date": date, "decision": {"branch": d.branch, "design": d.design, "llm_in_ranking": d.llm_in_ranking,
                                          "reasons": d.reasons, "checks": d.checks},
               "calibration_chosen": cal, "calibration_within_target": cal_ok,
               "headline_full_coverage": {m: {s: point(allf, m, s) for s in ("spatial", "study") if s in allf.get(m, {})}
                                          for m in ALL_ORDER if m in allf},
               "rep0_full_coverage": {m: point(rep0, m) for m in rep0},
               "paired_vs_m1_v2_spatial": vs_m1, "paired_vs_m1_v2_study": study_vs_m1, "paired_other_spatial": other,
               "context_tests": {"full_coverage": zc, "swap_tau": taus, "names_tau": ntaus},
               "recall_probes": rc, "fresh_2024plus": fresh, "hybrids": hp, "e7_spend_usd": spend,
               "figures": [fig1.name, fig2.name]}
    (out_dir / "metrics.json").write_text(json.dumps(payload, indent=1, default=str) + "\n", encoding="utf-8")
    return md


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="E7 merges, decision and methodology comparison report")
    ap.add_argument("cmd", choices=("merge", "compose", "decide"))
    ap.add_argument("--date", default=None)
    a = ap.parse_args(argv)
    if a.cmd == "merge":
        for p in merge():
            print(p)
    elif a.cmd == "decide":
        d = apply_decision()
        print(json.dumps({"branch": d.branch, "design": d.design, "llm_in_ranking": d.llm_in_ranking, "reasons": d.reasons,
                          "checks": d.checks}, indent=1, default=str))
    else:
        print(compose(a.date))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
