"""The E5 report: Methodology 1 v2 on the E4 harness (brief Part 5).

``merge_runs`` builds one scored run from the predictions of several runs on the same
queries and folds (the ablations ran one variant per process after a native crash of the
single-process run; merging re-scores them together so the paired differences against
``m1_v2`` are on identical queries). ``compose`` writes ``model/reports/eval_<date>_m1v2.md``
from the headline, component, ablation, all-set and legacy runs: full coverage and common
subset tables for both splits, paired differences, the success criterion stated before the
results, components, ablations, calibration overall and per objective group, breakdowns
and continuity. Every number is read from the runs' ``metrics.json`` and predictions.

Usage::

    python -m model.m1.report merge --out e5_ablations --from e5_headline:practice_prior,m1_v2 e5_abl_m1_nobelt:m1_nobelt ...
    python -m model.m1.report compose
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

from model.harness import HARNESS_DIR, REPORTS_DIR, RUNS_DIR
from model.harness import queries as hq
from model.harness import run as hr

HEADLINE, COMPONENTS, ABLATIONS, ALLSET, LEGACY, REPEAT = ("e5_headline", "e5_components", "e5_ablations", "e5_all",
                                                           "e5_legacy68", "e5_headline_b")
ABLATION_LABEL = {"m1_v2": "M1 v2 (headline)", "m1_notune": "no inner tuning or selection", "m1_nobelt": "belt removed",
                  "m1_legacy11": "context: 11 legacy layers", "m1_nohab": "Habtamu rows removed",
                  "m1_nocountry": "country-precision rows removed", "m1_wquality": "weights: quality default",
                  "m1_noranker": "ranker removed", "m1_nomatched": "matched studies removed",
                  "m1_rankavg": "stacker: rank averaging", "m1_ridge": "stacker: ridge forced"}
COMPONENT_LABEL = {"m1_regressor": "regressor (+ prior fallback)", "m1_ranker": "ranker (+ prior)",
                   "m1_matched": "matched studies (+ prior)", "m1_prior": "shrunken prior alone",
                   "practice_prior": "E4 practice prior", "m1_v2": "M1 v2 (all components)"}


# ----------------------------------------------------------------- merge
def merge_runs(out_id: str, sources: list[tuple[str, list[str]]], runs_dir: Path = RUNS_DIR) -> Path:
    preds, cfg0, methods = [], None, {}
    for run_id, ms in sources:
        d = runs_dir / run_id
        p = pd.read_parquet(d / "predictions.parquet")
        p = p[p["method"].isin(ms)].copy()
        missing = set(ms) - set(p["method"])
        if missing:
            raise ValueError(f"{run_id} has no predictions for {sorted(missing)}")
        p["run_id"] = out_id
        preds.append(p)
        c = json.loads((d / "config.json").read_text(encoding="utf-8"))
        cfg0 = cfg0 or c
        for m in ms:
            methods[m] = {**(c.get("methods") or {}).get(m, {}), "source_run": run_id}
        if c.get("query_hash") != cfg0.get("query_hash") or c.get("fold_files") != cfg0.get("fold_files"):
            raise ValueError(f"{run_id} was run on different queries or folds")
    out = runs_dir / out_id
    out.mkdir(parents=True, exist_ok=True)
    pd.concat(preds, ignore_index=True).to_parquet(out / "predictions.parquet", engine="pyarrow", index=False)
    cfg = {**cfg0, "run_id": out_id, "methods": methods, "merged_from": [s for s, _ in sources]}
    (out / "config.json").write_text(json.dumps(cfg, indent=1, default=str) + "\n", encoding="utf-8")
    return hr.rescore(out)


# ----------------------------------------------------------------- tables
def _m(run_id: str) -> dict[str, Any]:
    return json.loads((RUNS_DIR / run_id / "metrics.json").read_text(encoding="utf-8"))


def _f(v: Any, pct: bool = False, sd: Any = None) -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "-"
    s = f"{v:.1%}" if pct else f"{v:.3f}"
    if sd is not None and not (isinstance(sd, float) and math.isnan(sd)):
        s += f" ± {sd:.1%}" if pct else f" ± {sd:.3f}"
    return s


def metric_table(agg: dict[str, Any], methods: list[str], labels: dict[str, str] | None = None,
                 keys: tuple[str, ...] = ("top1_hit", "top1_chance", "c_index", "c_index_pooled", "ndcg3", "rmse", "sign_acc", "coverage80", "width80")) -> list[str]:
    pct = {"top1_hit", "top1_chance", "sign_acc", "coverage80"}
    head = {"top1_hit": "top-1", "top1_chance": "chance", "c_index": "C-index", "c_index_pooled": "C pooled", "ndcg3": "NDCG@3",
            "rmse": "RMSE", "sign_acc": "sign acc.", "coverage80": "80 % cov.", "width80": "80 % width"}
    L = ["| method | split | " + " | ".join(head[k] for k in keys) + " |", "|---|---|" + "|".join("---:" for _ in keys) + "|"]
    for m in methods:
        for split in ("spatial", "study", "legacy"):
            v = (agg.get(m) or {}).get(split)
            if not v:
                continue
            cells = [_f((v.get(k) or {}).get("mean"), k in pct, (v.get(k) or {}).get("sd") if k in ("top1_hit", "c_index") else None) for k in keys]
            L.append(f"| {(labels or {}).get(m, m)} | {split} | " + " | ".join(cells) + " |")
    return L


def paired_table(paired: dict[str, Any], against: str = "m1_v2", filt: list[str] | None = None) -> list[str]:
    L = ["| comparison (M1 v2 minus other) | split | n | top-1 | C-index | NDCG@3 |", "|---|---|---:|---:|---:|---:|"]
    for pair, by in paired.items():
        a, b = pair.split(" vs ")
        if against not in (a, b):
            continue
        other, sign = (b, 1.0) if a == against else (a, -1.0)
        if filt and other not in filt:
            continue
        for split, r in by.items():
            cells = []
            for k in ("top1_hit", "c_index", "ndcg3"):
                v = r[k]
                if v.get("diff") is None:
                    cells.append("-")
                    continue
                d, lo, hi = sign * v["diff"], *(sorted([sign * v["lo"], sign * v["hi"]]))
                star = " *" if lo > 0 or hi < 0 else ""
                cells.append(f"{d:+.3f} [{lo:+.3f}, {hi:+.3f}]{star}")
            L.append(f"| vs {other} | {split} | {r['n']} | " + " | ".join(cells) + " |")
    return L


def calibration_by_group(run_id: str, method: str = "m1_v2") -> pd.DataFrame:
    p = pd.read_parquet(RUNS_DIR / run_id / "predictions.parquet")
    q, items = hq.load_queries(HARNESS_DIR)
    j = p[p["method"] == method].merge(items[["query_id", "practice_id", "y"]], on=["query_id", "practice_id"])
    j["cov"] = (j["lo"] <= j["y"]) & (j["y"] <= j["hi"])
    j["width"] = j["hi"] - j["lo"]
    j["objective_group"] = j["query_id"].map(q.set_index("query_id")["objective_group"])
    j["lead"] = j["lead_source"]
    rows = []
    for (split, g), b in j.groupby(["split", "objective_group"]):
        rows.append({"split": split, "objective_group": g, "n_items": len(b), "coverage80": b["cov"].mean(), "median_width": b["width"].median()})
    for split, b in j.groupby("split"):
        rows.append({"split": split, "objective_group": "all", "n_items": len(b), "coverage80": b["cov"].mean(), "median_width": b["width"].median()})
    return pd.DataFrame(rows)


def lead_shares(run_id: str, method: str = "m1_v2") -> dict[str, float]:
    p = pd.read_parquet(RUNS_DIR / run_id / "predictions.parquet")
    return {k: round(float(v), 3) for k, v in p[p["method"] == method]["lead_source"].value_counts(normalize=True).items()}


def compose(date: str | None = None) -> Path:
    date = date or _dt.date.today().isoformat()
    head, comp, abl, allset, leg = _m(HEADLINE), _m(COMPONENTS), _m(ABLATIONS), _m(ALLSET), _m(LEGACY)
    hc = json.loads((RUNS_DIR / HEADLINE / "config.json").read_text(encoding="utf-8"))
    full = head["full_coverage"]["aggregate"]
    sp = {p: head["paired"][p]["spatial"] for p in head["paired"] if "m1_v2" in p}

    def beats(other: str, metric: str) -> tuple[bool, float, float, float]:
        for pair, r in sp.items():
            a, b = pair.split(" vs ")
            if {a, b} == {"m1_v2", other}:
                s = 1.0 if a == "m1_v2" else -1.0
                lo, hi = sorted([s * r[metric]["lo"], s * r[metric]["hi"]])
                return lo > 0, s * r[metric]["diff"], lo, hi
        return False, float("nan"), float("nan"), float("nan")

    crit = {o: {m: beats(o, m) for m in ("top1_hit", "c_index")} for o in ("practice_prior", "m0_current+prior")}
    cov = full["m1_v2"]["spatial"]["coverage80"]["mean"]
    met = all(v[0] for o in crit.values() for v in o.values()) and 0.75 <= cov <= 0.85
    L = [f"# Evaluation: Methodology 1 v2 (E5, {date})", "",
         "Generated by `model/m1/report.py` from the harness runs " + ", ".join(f"`{r}`" for r in (HEADLINE, COMPONENTS, ABLATIONS, ALLSET, LEGACY, REPEAT))
         + f". ET set: {hc['n_queries']} queries; folds and queries of E4 (query hash `{hc['query_hash'][:12]}`, Tier 1 index hash "
         f"`{(hc.get('index_hash') or '')[:12]}`, release `{hc['release']}`); 5 repetitions x 5 folds per split. Do not edit by hand.", "",
         "How to read this. Every method ranks the same held-out queries from the site's context alone. **Full coverage** is the "
         "headline: a method that abstains is filled by the practice prior on those queries and shown as `<method>+prior`. The "
         "**common subset** compares the methods only on queries all of them answered. **Paired differences** are bootstrap "
         "intervals over queries of M1 v2 minus the other method; an asterisk means the interval excludes zero. Top-1 is how often "
         "the first choice was the trial's best practice; the C-index is the share of practice pairs ordered right (0.5 = coin); "
         "80 % coverage is the share of held-out effects inside the method's 80 % interval.", "",
         "## Success criterion (stated in the brief before any result)", "",
         "On the ET set, spatial split, full coverage, `m1_v2` beats `practice_prior` and `m0_current+prior` on top-1 hit and C-index "
         "(paired bootstrap interval of the difference excludes zero), and its 80 % intervals cover 75 to 85 % of held-out effects.", "",
         "| requirement | difference [95 %] | met |", "|---|---:|---|"]
    for o, ms in crit.items():
        for m, (ok, d, lo, hi) in ms.items():
            L.append(f"| beats `{o}` on {'top-1' if m == 'top1_hit' else 'C-index'} | {d:+.3f} [{lo:+.3f}, {hi:+.3f}] | {'yes' if ok else '**no**'} |")
    L.append(f"| 80 % coverage in [0.75, 0.85] | {cov:.3f} | {'yes' if 0.75 <= cov <= 0.85 else '**no**'} |")
    L += ["", f"**Verdict: {'met' if met else 'not met'}.**", ""]
    L += ["## Headline, full coverage", ""] + metric_table(full, ["m1_v2", "practice_prior", "nearest_studies+prior", "m0_current+prior"]) + [""]
    L += ["## Common subset (queries every method answered)", ""]
    for split, cs in head["common_subset"].items():
        L += [f"{split} split: n = {cs['n']}", ""] + metric_table({m: {split: v} for m, v in cs["aggregate"].items()},
                                                                   ["m1_v2", "practice_prior", "nearest_studies", "m0_current"],
                                                                   keys=("top1_hit", "top1_chance", "c_index", "ndcg3")) + [""]
    L += ["## Paired differences", ""] + paired_table(head["paired"]) + [""]
    L += ["## Components (each alone, the prior answering what it cannot)", ""]
    L += metric_table(comp["full_coverage"]["aggregate"], ["m1_regressor", "m1_ranker", "m1_matched", "m1_prior", "practice_prior"], COMPONENT_LABEL)
    L += ["", "M1 v2 with all components, for reference:", ""] + metric_table(full, ["m1_v2"], COMPONENT_LABEL) + [""]
    L += ["## Ablations", ""] + metric_table(abl["full_coverage"]["aggregate"], list(ABLATION_LABEL), ABLATION_LABEL)
    L += ["", "Paired differences of M1 v2 against each ablation (positive = the removed piece helped):", ""]
    L += paired_table(abl["paired"], filt=list(ABLATION_LABEL)) + [""]
    cal = calibration_by_group(HEADLINE)
    L += ["## Calibration (80 % intervals, held-out items)", "", "| split | objective group | items | coverage | median width |",
          "|---|---|---:|---:|---:|"]
    for r in cal.sort_values(["split", "objective_group"]).itertuples():
        L.append(f"| {r.split} | {r.objective_group} | {r.n_items} | {r.coverage80:.3f} | {r.median_width:.3f} |")
    L += ["", f"Lead sources of M1 v2 items: {lead_shares(HEADLINE)}.", "",
          "![coverage-accuracy](figures/e5_headline/coverage_accuracy_spatial.png) ![calibration](figures/e5_headline/calibration_spatial.png)", ""]
    L += ["## Breakdowns (spatial split, full coverage; top-1 / C-index; `n < 20` cells not shown as numbers)", ""]
    for by in ("objective_group", "challenge_ids", "belt", "sources", "loc_precision"):
        recs = [r for r in head["breakdowns"].get(by, []) if r["split"] == "spatial" and r["method"] in ("m1_v2", "practice_prior", "m0_current+prior")]
        if not recs:
            continue
        df = pd.DataFrame(recs)
        L += [f"### {by}", "", "| cell | n | m1_v2 | practice_prior | m0_current+prior |", "|---|---:|---:|---:|---:|"]
        for cell in sorted(df[by].unique(), key=str):
            sub = df[df[by] == cell]
            n = int(sub[sub["method"] == "m1_v2"]["n"].max()) if (sub["method"] == "m1_v2").any() else int(sub["n"].max())
            cells = []
            for m in ("m1_v2", "practice_prior", "m0_current+prior"):
                t = sub[(sub["method"] == m) & (sub["metric"] == "top1_hit")]["value"]
                c = sub[(sub["method"] == m) & (sub["metric"] == "c_index")]["value"]
                fmt = lambda s: "-" if s.empty else (s.iloc[0] if isinstance(s.iloc[0], str) else f"{s.iloc[0]:.2f}")
                cells.append(f"{fmt(t)} / {fmt(c)}")
            L.append(f"| {cell} | {n} | " + " | ".join(cells) + " |")
        L.append("")
    L += ["## All set (ET and global, 414 queries)", ""] + metric_table(allset["full_coverage"]["aggregate"], ["m1_v2", "practice_prior", "m0_current+prior"]) + [""]
    L += ["## Continuity: legacy 68 cells, P7 grouped folds (10 x 5)", ""]
    L += metric_table(leg["aggregate"], ["m0_current", "m1_v2"], keys=("top1_hit", "top1_chance", "c_index", "c_index_pooled", "ndcg3")) + [""]
    L += ["## Configuration", "", f"- git `{hc.get('git_commit')}`; started {hc.get('started_utc')}; timings (s) {hc.get('timings_s')}",
          f"- m1_v2 parameters: `{json.dumps({k: v for k, v in hc['methods']['m1_v2'].items() if k not in ('folds',)}, default=str)[:600]}`", ""]
    path = REPORTS_DIR / f"eval_{date}_m1v2.md"
    path.write_text("\n".join(L) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="E5 report: merge runs and compose the M1 v2 evaluation report")
    sub = ap.add_subparsers(dest="cmd", required=True)
    mg = sub.add_parser("merge")
    mg.add_argument("--out", required=True)
    mg.add_argument("--from", dest="sources", nargs="+", required=True, help="RUN_ID:method,method ...")
    cp = sub.add_parser("compose")
    cp.add_argument("--date", default=None)
    a = ap.parse_args(argv)
    if a.cmd == "merge":
        sources = [(s.split(":")[0], s.split(":")[1].split(",")) for s in a.sources]
        print("merged and rescored", merge_runs(a.out, sources))
    else:
        print("wrote", compose(a.date))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
