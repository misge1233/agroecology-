"""The E6 report: E5.1 and Methodology 2 on the E4 harness (brief Parts 0 and 6).

``merge-rep0`` builds one scored run of every method's predictions on the **spatial
split, repetition 0** (the M2 design): M1 v2, the current model and the practice prior
from the E5 headline (their rep-0 rows), E5.1, and the M2 runs; all on the same 375
queries and folds (checked by hash), re-scored together so the paired differences are
query by query. ``compose`` writes ``model/reports/eval_<date>_m2.md``: E5.1 against E5
(both splits, 5 x 5), the M2 headline (full coverage, common subset, paired), the variant
ladder, memorisation (``m2_zero`` against ``m2_cards``), ``post_2024`` size, stability,
citation validity, cost and latency, and the calibration of the card-derived intervals.
Every number is read from the runs.

Usage::

    python -m model.m2.report merge-e51
    python -m model.m2.report merge-rep0 --out e6_m2_headline --from e5_headline:m1_v2,m0_current,practice_prior e6_m2_zero_et:m2_zero ...
    python -m model.m2.report compose
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

from model import metrics as mm
from model.harness import HARNESS_DIR, REPORTS_DIR, RUNS_DIR
from model.harness import queries as hq
from model.harness import run as hr
from model.m1 import report as m1r
from model.m2.client import load_prices, price_of

E51_LABEL = "E5.1, post-hoc, pre-registered 12 Nov 2026"
E51_RUN, E51_MERGED = "e51_m1", "e6_e51"
HEADLINE = "e6_m2_headline"
GLOBAL = "e6_m2_graph_global"
STABILITY = "e6_m2_stability"
M2_RUNS = {"m2_zero": "e6_m2_zero_et", "m2_cards": "e6_m2_cards_et", "m2_rag": "e6_m2_rag_et", "m2_graph": "e6_m2_graph_et"}
SPLIT, REP = "spatial", 0


# ----------------------------------------------------------------- merges
def merge_rep0(out_id: str, sources: list[tuple[str, list[str]]], runs_dir: Path = RUNS_DIR) -> Path:
    """One run of the spatial repetition-0 predictions of several runs (same queries and spatial folds)."""
    preds, cfg0, methods = [], None, {}
    for run_id, ms in sources:
        d = runs_dir / run_id
        p = pd.read_parquet(d / "predictions.parquet")
        p = p[p["method"].isin(ms) & (p["split"] == SPLIT) & (p["rep"] == REP)].copy()
        missing = set(ms) - set(p["method"])
        if missing:
            raise ValueError(f"{run_id} has no spatial rep-0 predictions for {sorted(missing)}")
        p["run_id"] = out_id
        preds.append(p)
        c = json.loads((d / "config.json").read_text(encoding="utf-8"))
        if cfg0 is None:
            cfg0 = c
        if c.get("query_hash") != cfg0.get("query_hash") or c["fold_files"].get(SPLIT) != cfg0["fold_files"].get(SPLIT):
            raise ValueError(f"{run_id} was run on different queries or spatial folds")
        for m in ms:
            methods[m] = {**(c.get("methods") or {}).get(m, {}), "source_run": run_id}
    out = runs_dir / out_id
    out.mkdir(parents=True, exist_ok=True)
    merged = pd.concat(preds, ignore_index=True)
    merged = merged[~merged["method"].str.endswith(mm.FILL_SUFFIX)]  # re-filled from practice_prior on rescore
    merged.to_parquet(out / "predictions.parquet", engine="pyarrow", index=False)
    cfg = {**cfg0, "run_id": out_id, "methods": methods, "merged_from": [s for s, _ in sources], "splits": [SPLIT], "reps": REP + 1,
           "fold_files": {SPLIT: cfg0["fold_files"][SPLIT]}, "design": "spatial split, repetition 0 (E6 minimal design)"}
    (out / "config.json").write_text(json.dumps(cfg, indent=1, default=str) + "\n", encoding="utf-8")
    return hr.rescore(out, report=False)


def merge_e51() -> Path:
    """E5.1 beside E5, the current model and the prior: both splits, 5 x 5 (E5 report format)."""
    return m1r.merge_runs(E51_MERGED, [("e5_headline", ["m1_v2", "m0_current", "practice_prior"]), (E51_RUN, ["m1_v2_e51"])])


# ----------------------------------------------------------------- readers
def _metrics(run_id: str) -> dict[str, Any]:
    return json.loads((RUNS_DIR / run_id / "metrics.json").read_text(encoding="utf-8"))


def _config(run_id: str) -> dict[str, Any]:
    return json.loads((RUNS_DIR / run_id / "config.json").read_text(encoding="utf-8"))


def responses(run_id: str) -> list[dict[str, Any]]:
    p = RUNS_DIR / run_id / "responses.jsonl"
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()] if p.exists() else []


def e51_beats_e5(head: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    """The rebuild rule: spatial full-coverage top-1 or C-index of E5.1 over E5 with a paired interval above zero."""
    pair = head["paired"].get("m1_v2 vs m1_v2_e51") or head["paired"].get("m1_v2_e51 vs m1_v2")
    sign = -1.0 if "m1_v2 vs m1_v2_e51" in head["paired"] else 1.0
    r = pair["spatial"]
    out = {}
    win = False
    for k in ("top1_hit", "c_index"):
        d, lo, hi = sign * r[k]["diff"], *sorted([sign * r[k]["lo"], sign * r[k]["hi"]])
        out[k] = (d, lo, hi)
        win |= lo > 0
    return win, out


# ----------------------------------------------------------------- M2 measures
def citation_validity(entries: list[dict[str, Any]], card_meta: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    """Share of cited ids whose practice is the ranked item (or shown as related for it), share of
    items with at least one citation, cited ids outside the prompt in final answers, and invented
    ids in first answers."""
    n_items = n_cited_items = n_ids = n_match = n_outside = n_invented_first = 0
    for e in entries:
        if e.get("attempts"):
            n_invented_first += int(e["attempts"][0].get("invented_ids") or 0)
        if not e.get("valid"):
            continue
        shown = set(e.get("prompt_card_ids") or [])
        own = e.get("card_practice") or {}
        for pid, it in (e.get("items") or {}).items():
            n_items += 1
            ids = it.get("card_ids") or []
            n_cited_items += bool(ids)
            for cid in ids:
                n_ids += 1
                if cid not in shown:
                    n_outside += 1
                    continue
                info = own.get(cid) or {}
                if info.get("practice_id") == pid or pid in (info.get("related_for") or []):
                    n_match += 1
    return {"items": n_items, "items_with_citation": n_cited_items / n_items if n_items else float("nan"),
            "cited_ids": n_ids, "cited_matching": n_match / n_ids if n_ids else float("nan"),
            "cited_outside_prompt": n_outside, "invented_in_first_answers": n_invented_first}


def cost_latency(entries: list[dict[str, Any]], model: str) -> dict[str, Any]:
    prices = load_prices()
    p = price_of(model, prices)
    toks_in, toks_out, lat, usd, retries = [], [], [], [], 0
    for e in entries:
        a = e.get("attempts") or []
        retries += max(0, len(a) - 1)
        ti = sum(int((x.get("usage") or {}).get("prompt_tokens", 0)) for x in a)
        to = sum(int((x.get("usage") or {}).get("completion_tokens", 0)) for x in a)
        toks_in.append(ti)
        toks_out.append(to)
        usd.append((ti * float(p["input"]) + to * float(p.get("output", 0))) / 1e6)
        lat.append(sum(float(x.get("latency_s") or 0) for x in a))
    n = len(entries)
    return {"queries": n, "retries": retries, "abstained_invalid": sum(1 for e in entries if not e.get("valid")),
            "input_tokens_per_query": float(np.mean(toks_in)) if n else float("nan"),
            "output_tokens_per_query": float(np.mean(toks_out)) if n else float("nan"),
            "usd_per_query": float(np.mean(usd)) if n else float("nan"), "usd_total": float(np.sum(usd)),
            "latency_median_s": float(np.median(lat)) if n else float("nan"),
            "latency_p95_s": float(np.percentile(lat, 95)) if n else float("nan")}


def _ranking(e: dict[str, Any]) -> list[str] | None:
    if not e.get("valid"):
        return None
    items = e["items"]
    return sorted(items, key=lambda p: items[p]["rank"])


def kendall_tau(a: list[str], b: list[str]) -> float:
    """Kendall tau between two rankings of the same items (1 = identical order)."""
    pos = {p: i for i, p in enumerate(b)}
    n = len(a)
    if n < 2:
        return float("nan")
    conc = disc = 0
    for i in range(n):
        for j in range(i + 1, n):
            s = pos[a[j]] - pos[a[i]]  # a ranks i before j; concordant when b does too
            conc += s > 0
            disc += s < 0
    return (conc - disc) / (n * (n - 1) / 2)


def stability_table(stab_run: str = STABILITY, main_run: str = M2_RUNS["m2_graph"]) -> list[dict[str, Any]]:
    log = [json.loads(l) for l in (RUNS_DIR / stab_run / "stability_log.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    by: dict[str, dict[str, list[str] | None]] = {}
    for e in log:
        cond = ("repeat_" + e["repeat"][-1]) if str(e.get("repeat", "")).startswith("stability_r") else ("shuffle_" + str(e["shuffle_seed"]))
        by.setdefault(cond, {})[e["query_id"]] = _ranking(e)
    main = {e["query_id"]: _ranking(e) for e in responses(main_run)}
    by["main"] = {q: main.get(q) for q in by.get("repeat_1", {})}
    rows = []
    for a, b in (("repeat_1", "repeat_2"), ("main", "repeat_1"), ("main", "repeat_2"), ("shuffle_1", "shuffle_2"),
                 ("main", "shuffle_1"), ("main", "shuffle_2")):
        top, taus, n = [], [], 0
        for q, ra in by.get(a, {}).items():
            rb = by.get(b, {}).get(q)
            if ra is None or rb is None:
                continue
            n += 1
            top.append(ra[0] == rb[0])
            t = kendall_tau(ra, rb)
            if not math.isnan(t):
                taus.append(t)
        rows.append({"pair": f"{a} vs {b}", "n": n, "top1_agreement": float(np.mean(top)) if top else float("nan"),
                     "kendall_tau_mean": float(np.mean(taus)) if taus else float("nan")})
    return rows


def card_calibration(run_id: str, method: str) -> dict[str, Any]:
    p = pd.read_parquet(RUNS_DIR / run_id / "predictions.parquet")
    _, items = hq.load_queries(HARNESS_DIR)
    j = p[(p["method"] == method) & p["lo"].notna() & p["hi"].notna()].merge(items[["query_id", "practice_id", "y"]],
                                                                            on=["query_id", "practice_id"])
    n_all = int((p["method"] == method).sum())
    if j.empty:
        return {"items_with_interval": 0, "items": n_all}
    cov = ((j["lo"] <= j["y"]) & (j["y"] <= j["hi"])).mean()
    return {"items": n_all, "items_with_interval": int(len(j)), "share_with_interval": len(j) / n_all if n_all else float("nan"),
            "coverage80": float(cov), "median_width": float((j["hi"] - j["lo"]).median())}


# ----------------------------------------------------------------- compose
def _f(v: Any, pct: bool = False) -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "-"
    return f"{v:.1%}" if pct else f"{v:.3f}"


def paired_rows(paired: dict[str, Any], a: str, others: list[str], split: str = SPLIT) -> list[str]:
    L = ["| comparison | n | top-1 | C-index | NDCG@3 |", "|---|---:|---:|---:|---:|"]
    for o in others:
        key, sign = (f"{a} vs {o}", 1.0) if f"{a} vs {o}" in paired else (f"{o} vs {a}", -1.0)
        if key not in paired or split not in paired[key]:
            continue
        r = paired[key][split]
        cells = []
        for k in ("top1_hit", "c_index", "ndcg3"):
            v = r[k]
            if v.get("diff") is None:
                cells.append("-")
                continue
            d, lo, hi = sign * v["diff"], *sorted([sign * v["lo"], sign * v["hi"]])
            cells.append(f"{d:+.3f} [{lo:+.3f}, {hi:+.3f}]" + (" *" if lo > 0 or hi < 0 else ""))
        L.append(f"| {a} minus {o} | {r['n']} | " + " | ".join(cells) + " |")
    return L


def compose(date: str | None = None, strong: str | None = None) -> Path:
    date = date or _dt.date.today().isoformat()
    L: list[str] = [f"# E6 evaluation: E5.1 and Methodology 2 ({date})", "",
                    "Every number below is read from the harness runs in `model/harness/runs/` (git-ignored). "
                    "Paired differences are query-level bootstrap 95 % intervals (1,000 draws, seeded); * = the interval excludes zero.", ""]
    # ---- E5.1
    e = _metrics(E51_MERGED)
    full = e["full_coverage"]["aggregate"]
    labels = {"m1_v2_e51": f"M1 v2 E5.1 ({E51_LABEL})", "m1_v2": "M1 v2 (E5)", "m0_current+prior": "current model + prior",
              "practice_prior": "practice prior"}
    L += [f"## 1. E5.1 ({E51_LABEL})", "",
          "Two changes fixed before the run (E6 brief Part 0): the inner stacker choice among ridge, rank averaging over four "
          "components, rank averaging over ranker, regressor and prior, and ranker-weighted averages (weight 2 or 3), scored by "
          "the mean of inner top-1 and C-index; Mondrian conformal quantiles per objective group (at least 30 inner residuals, "
          "else pooled). ET set, both splits, 5 x 5, one variant per process.", "",
          "**Full coverage** (mean ± sd across 5 x 5):", ""]
    L += m1r.metric_table(full, [m for m in ("m1_v2_e51", "m1_v2", "m0_current+prior", "practice_prior") if m in full], labels)
    cs = e["common_subset"]
    L += ["", "**Common subset** (queries every method answered in every repetition):", ""]
    for split, block in cs.items():
        L.append(f"*{split}: {block['n']} queries*")
        L.append("")
        L += m1r.metric_table({m: {split: v} for m, v in block["aggregate"].items()},
                              [m for m in ("m1_v2_e51", "m1_v2", "m0_current", "practice_prior") if m in block["aggregate"]], labels,
                              keys=("top1_hit", "c_index", "ndcg3"))
        L.append("")
    L += ["**Paired differences, E5.1 minus other** (full coverage):", ""]
    for split in ("spatial", "study"):
        L.append(f"*{split}*")
        L.append("")
        L += paired_rows(e["paired"], "m1_v2_e51", ["m1_v2", "m0_current+prior", "practice_prior"], split)
        L.append("")
    win, d = e51_beats_e5(e)
    L += [f"**Rebuild rule** (spatial full-coverage top-1 or C-index over E5 with the paired interval above zero): "
          f"top-1 {d['top1_hit'][0]:+.3f} [{d['top1_hit'][1]:+.3f}, {d['top1_hit'][2]:+.3f}], C-index {d['c_index'][0]:+.3f} "
          f"[{d['c_index'][1]:+.3f}, {d['c_index'][2]:+.3f}]: **{'met, the artifact is rebuilt with E5.1' if win else 'not met, the E5 artifact is kept'}**.", ""]
    cal = pd.concat([m1r.calibration_by_group(E51_MERGED, m).assign(method=m) for m in ("m1_v2", "m1_v2_e51")])
    L += ["**Calibration per objective group** (80 % interval coverage of held-out effects, all 25 folds):", "",
          "| split | objective group | items | E5 coverage | E5.1 coverage | E5 median width | E5.1 median width |", "|---|---|---:|---:|---:|---:|---:|"]
    piv = cal.pivot_table(index=["split", "objective_group"], columns="method", values=["coverage80", "median_width", "n_items"])
    for (split, g), r in piv.iterrows():
        L.append(f"| {split} | {g} | {int(r[('n_items', 'm1_v2')])} | {r[('coverage80', 'm1_v2')]:.3f} | {r[('coverage80', 'm1_v2_e51')]:.3f} | "
                 f"{r[('median_width', 'm1_v2')]:.2f} | {r[('median_width', 'm1_v2_e51')]:.2f} |")
    folds = (_config(E51_RUN)["methods"]["m1_v2_e51"].get("folds") or [])
    votes = pd.Series([f.get("stacker") for f in folds]).value_counts().to_dict()
    L += ["", f"Stacker chosen inside the 50 outer fits of E5.1: {', '.join(f'{k} {v}' for k, v in votes.items())}.", ""]
    # ---- M2 headline
    h = _metrics(HEADLINE)
    hf_ = h["full_coverage"]["aggregate"]
    m2_methods = [m for m in sorted(hf_) if m.startswith("m2_")]
    strong = sorted({m.removesuffix("+prior") for m in m2_methods if "__" in m}, key=lambda m: ("graph" in m, m))
    strong_name = strong[-1] if strong else None
    strong_model = strong_name.split("__")[1] if strong_name else None
    order = [m for m in ("m2_zero+prior", "m2_cards+prior", "m2_rag+prior", "m2_graph+prior", *[s + "+prior" for s in strong],
                         "m2_zero", "m2_cards", "m2_rag", "m2_graph", *strong) if m and m in hf_]
    m1_kept = "m1_v2_e51" if win else "m1_v2"
    base = list(dict.fromkeys(m for m in (m1_kept, "m1_v2", "m0_current+prior", "practice_prior") if m in hf_))
    L += ["## 2. Methodology 2 headline (spatial split, repetition 0, all 375 ET queries)", "",
          "Design (owner, 12 Nov 2026): one call per query per variant, `gpt-4o-mini` for the four variants"
          + (f", `{strong_model}` (the stronger model; owner: deployable low-cost models only) for "
             + " and ".join(f"`{s.split('__')[0]}`" for s in strong) if strong else ", the stronger model pending the owner's go")
          + ". Every other method's predictions are its rows on the same repetition-0 spatial folds. An abstained query (a candidate "
          "classed `unknown`, or two invalid answers) is filled by the practice prior in the full-coverage variant (`+prior`).", "",
          "**Full coverage:**", ""]
    L += m1r.metric_table(hf_, order + base, keys=("top1_hit", "top1_chance", "c_index", "c_index_pooled", "ndcg3", "coverage80", "width80"))
    agg = h["aggregate"]
    L += ["", "**Abstention of the M2 variants before the fill** (share of queries):", "", "| method | abstention | top-1 on answered | C-index on answered |", "|---|---:|---:|---:|"]
    for m in [x for x in ("m2_zero", "m2_cards", "m2_rag", "m2_graph", *strong) if x and x in agg]:
        v = agg[m][SPLIT]
        L.append(f"| {m} | {_f(v['abstention_rate']['mean'], True)} | {_f(v['top1_hit']['mean'])} | {_f(v['c_index']['mean'])} |")
    cs = h["common_subset"].get(SPLIT, {})
    if cs:
        L += ["", f"**Common subset** ({cs['n']} queries every method answered):", ""]
        L += m1r.metric_table({m: {SPLIT: v} for m, v in cs["aggregate"].items()}, sorted(cs["aggregate"]), keys=("top1_hit", "c_index", "ndcg3"))
    L += ["", "**Paired differences** (full coverage):", ""]
    for m in [x for x in order if x.endswith("+prior")] or order:
        L += paired_rows(h["paired"], m, [x for x in base] + [x for x in order if x != m and x.endswith("+prior")])
        L.append("")
    # ---- ladder / memorisation / post_2024
    L += ["## 3. Variant ladder and memorisation", "",
          "`m2_zero` sees only the context, the objective and the candidate names (what the model already knows); each step adds "
          "one kind of evidence. Paired `m2_cards+prior` minus `m2_zero+prior` measures the use of the cards.", ""]
    L += paired_rows(h["paired"], "m2_cards+prior", ["m2_zero+prior"])
    L += paired_rows(h["paired"], "m2_rag+prior", ["m2_cards+prior"])[2:]
    L += paired_rows(h["paired"], "m2_graph+prior", ["m2_rag+prior"])[2:]
    sz, sg = (f"m2_zero__{strong_model}", f"m2_graph__{strong_model}") if strong_model else (None, None)
    if sz and sz in agg and sg in agg:
        L += ["", f"**Stronger model ({strong_model})**: does the evidence effect seen with `gpt-4o-mini` hold? "
              f"`{sg}+prior` minus `{sz}+prior` is the evidence effect with the stronger model; each stronger variant is also "
              "compared with its `gpt-4o-mini` counterpart.", ""]
        L += paired_rows(h["paired"], f"{sg}+prior", [f"{sz}+prior", "m2_graph+prior"] + base)
        L += paired_rows(h["paired"], f"{sz}+prior", ["m2_zero+prior"] + base)[2:]
    n_et_post = int(hr.select_queries(hq.load_queries(HARNESS_DIR)[0], "post_2024").query("query_set == 'ET'").shape[0])
    L += ["", f"`post_2024` queries (published after the model's training data could include them) are reported with their size and "
          f"not interpreted. The ET set has {n_et_post}; the global set has the only ones, scored in the global run:", ""]
    if (RUNS_DIR / GLOBAL / "metrics.json").exists():
        for r in _metrics(GLOBAL)["breakdowns"].get("post_2024", []):
            if str(r.get("post_2024")) == "True" and r.get("metric") in ("top1_hit", "c_index"):
                L.append(f"- {r['method']}: {r['metric']} {r['value'] if isinstance(r.get('value'), str) else _f(r.get('value'))} (n = {r['n']}; the harness withholds cells under 20 queries)")
    # ---- global
    if (RUNS_DIR / GLOBAL / "metrics.json").exists():
        g = _metrics(GLOBAL)["aggregate"]
        L += ["", "**Global set** (39 queries outside Ethiopia, `m2_graph`, `gpt-4o-mini`, spatial repetition 0):", ""]
        L += m1r.metric_table(g, [m for m in ("m2_graph", "m2_graph+prior", "practice_prior") if m in g], keys=("top1_hit", "top1_chance", "c_index", "ndcg3"))
    # ---- stability
    L += ["", "## 4. Stability (40 fixed queries, `m2_graph`, `gpt-4o-mini`)", "",
          "Repeats are fresh calls with their own cache keys; shuffles present the candidates in a different order.", "",
          "| pair | queries | top-1 agreement | Kendall tau (mean) |", "|---|---:|---:|---:|"]
    if (RUNS_DIR / STABILITY / "stability_log.jsonl").exists():
        for r in stability_table():
            L.append(f"| {r['pair']} | {r['n']} | {_f(r['top1_agreement'], True)} | {_f(r['kendall_tau_mean'])} |")
    # ---- citation validity / cost / calibration
    runs = {m: M2_RUNS[m] for m in ("m2_zero", "m2_cards", "m2_rag", "m2_graph")}
    for s in strong:
        runs[s] = f"e6_{s}_et"
    L += ["", "## 5. Citation validity", "",
          "| method | items | items with a citation | cited ids | cited id matches the item (or shown as related) | cited ids outside the prompt (final) | invented ids in first answers |",
          "|---|---:|---:|---:|---:|---:|---:|"]
    for m, rid in runs.items():
        if (RUNS_DIR / rid).exists():
            c = citation_validity(responses(rid))
            L.append(f"| {m} | {c['items']} | {_f(c['items_with_citation'], True)} | {c['cited_ids']} | {_f(c['cited_matching'], True)} | "
                     f"{c['cited_outside_prompt']} | {c['invented_in_first_answers']} |")
    L += ["", "## 6. Cost and latency (per query, the calls of the scored run including retries)", "",
          "| method | model | queries | retries | invalid twice | input tokens | output tokens | USD per query | USD total | median latency s | p95 latency s |",
          "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for m, rid in runs.items():
        if (RUNS_DIR / rid).exists():
            model = _config(rid).get("m2", {}).get("model", "gpt-4o-mini")
            c = cost_latency(responses(rid), model)
            L.append(f"| {m} | {model} | {c['queries']} | {c['retries']} | {c['abstained_invalid']} | {c['input_tokens_per_query']:.0f} | "
                     f"{c['output_tokens_per_query']:.0f} | {c['usd_per_query']:.5f} | {c['usd_total']:.3f} | {c['latency_median_s']:.2f} | {c['latency_p95_s']:.2f} |")
    L += ["", "## 7. Calibration of the card-derived intervals (expected weak; reported, not fixed in E6)", "",
          "| method | items | items with an interval | 80 % coverage | median width |", "|---|---:|---:|---:|---:|"]
    for m in runs:
        c = card_calibration(HEADLINE, m) if (RUNS_DIR / HEADLINE).exists() else {}
        if c:
            L.append(f"| {m} | {c['items']} | {c['items_with_interval']} ({_f(c.get('share_with_interval'), True)}) | "
                     f"{_f(c.get('coverage80'), True)} | {_f(c.get('median_width'))} |")
    # sections 2 to 7 are one repetition: the sd across repetitions does not exist there
    cut = next(i for i, l in enumerate(L) if l.startswith("## 2."))
    L = L[:cut] + [l.replace(" ± 0.0%", "").replace(" ± 0.000", "") for l in L[cut:]]
    out = REPORTS_DIR / f"eval_{date}_m2.md"
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="E6 report")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("merge-e51")
    mg = sub.add_parser("merge-rep0")
    mg.add_argument("--out", required=True)
    mg.add_argument("--from", dest="sources", nargs="+", required=True, help="RUN_ID:method,method ...")
    cp = sub.add_parser("compose")
    cp.add_argument("--date", default=None)
    a = ap.parse_args(argv)
    if a.cmd == "merge-e51":
        print(merge_e51())
    elif a.cmd == "merge-rep0":
        print(merge_rep0(a.out, [(s.split(":")[0], s.split(":")[1].split(",")) for s in a.sources]))
    else:
        print(compose(a.date))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
