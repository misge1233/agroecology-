"""The evaluation report of one harness run (E4 Part 5).

``model/reports/eval_<date>_<run_id>.md``: a plain-words "how to read this" paragraph,
the headline table (methods by metrics for every split, mean +- sd across repetitions
with the query-level bootstrap interval of the top-1 hit and the C-index), the random
expectation, the breakdowns (objective group, challenge, belt, source, precision, query
set, post-2024; cells under 20 queries show ``n < 20``), the coverage-accuracy curve and
the calibration plot (PNG, matplotlib) and the configuration hashes. Every number also
sits in ``metrics.json`` so the Methodology page can render it later.
"""
from __future__ import annotations

import datetime as _dt
import json
import math
from pathlib import Path
from typing import Any

import pandas as pd

from model import metrics as mm
from model.harness import REPORTS_DIR

HEADLINE_COLS = (("top1_hit", "top-1 hit"), ("top1_chance", "chance"), ("tophalf_hit", "top-half"), ("c_index", "C-index"),
                 ("ndcg3", "NDCG@3"), ("spearman_median", "Spearman (median)"), ("rmse", "RMSE lrr"), ("sign_acc", "sign acc."),
                 ("coverage80", "80% coverage"), ("width80", "80% width"), ("abstention_rate", "abstained"))
BREAKDOWN_TITLES = {"objective_group": "Objective group", "challenge_ids": "Challenge (a query counts in every challenge of its outcome)",
                    "belt": "Belt (attribute only)", "sources": "Source", "loc_precision": "Location precision",
                    "query_set": "ET versus global", "post_2024": "Published 2024 or later (memorisation check)"}
HOW_TO_READ = (
    "How to read this. Every method answered the same queries: one query is one study site, one outcome and the "
    "practices that study compared, and the method had to rank those practices from the site's context alone, "
    "never seeing the study's own rows, passages or graph edges. Top-1 hit is how often the method's first choice "
    "was the practice that did best in the trial (chance is what guessing would give); the C-index is the share of "
    "practice pairs it ordered the right way (0.5 is a coin flip); NDCG@3 rewards putting strong practices in the "
    "top three; the median Spearman is the typical rank agreement within a query. RMSE, sign accuracy and the 80 % "
    "interval figures apply only to methods that give a number. 'Abstained' is the share of queries a method "
    "declined; its other figures are computed on the queries it answered. Figures are the mean across the fold "
    "repetitions with the spread (sd) that fold choice alone produces; the bracket is a bootstrap interval over "
    "queries. The spatial split holds out whole 1-degree blocks, which is the harder and more honest test for a "
    "new site; the study split holds out papers."
)


def _fmt(stat: dict[str, Any] | None, pct: bool = False, places: int = 3) -> str:
    if not isinstance(stat, dict) or stat.get("mean") is None or (isinstance(stat.get("mean"), float) and math.isnan(stat["mean"])):
        return "-"
    m, sd = float(stat["mean"]), float(stat.get("sd") or 0.0)
    return f"{m:.1%} +- {sd:.1%}" if pct else f"{m:.{places}f} +- {sd:.{places}f}"


def _boot(b: dict[str, Any] | None, pct: bool = False) -> str:
    if not b or b.get("lo") is None or (isinstance(b.get("lo"), float) and math.isnan(b["lo"])):
        return ""
    return f" [{b['lo']:.1%}, {b['hi']:.1%}]" if pct else f" [{b['lo']:.3f}, {b['hi']:.3f}]"


def headline_table(metrics: dict[str, Any], split: str) -> list[str]:
    agg, boot = metrics["aggregate"], metrics.get("bootstrap95", {})
    L = ["| method | n queries | " + " | ".join(t for _, t in HEADLINE_COLS) + " |",
         "|---|---:|" + "|".join("---:" for _ in HEADLINE_COLS) + "|"]
    for method in sorted(agg):
        v = agg[method].get(split)
        if not v:
            continue
        cells = []
        for key, _ in HEADLINE_COLS:
            pct = key in ("top1_hit", "top1_chance", "tophalf_hit", "sign_acc", "coverage80", "abstention_rate")
            cell = _fmt(v.get(key), pct=pct)
            if key in ("top1_hit", "c_index"):
                cell += _boot(boot.get(method, {}).get(split, {}).get(key), pct=pct)
            cells.append(cell)
        L.append(f"| {method} | {v['n_queries']['mean']:.0f} | " + " | ".join(cells) + " |")
    return L


def breakdown_tables(metrics: dict[str, Any], split: str) -> list[str]:
    L: list[str] = []
    for by, title in BREAKDOWN_TITLES.items():
        recs = [r for r in metrics.get("breakdowns", {}).get(by, []) if r["split"] == split]
        if not recs:
            continue
        df = pd.DataFrame(recs)
        methods = sorted(df["method"].unique())
        cells = sorted(df[by].unique(), key=str)
        L += ["", f"### {title} ({split} split; top-1 hit / C-index)", "",
              "| cell | n | " + " | ".join(methods) + " |", "|---|---:|" + "|".join("---:" for _ in methods) + "|"]
        for cell in cells:
            sub = df[df[by] == cell]
            n = int(sub["n"].iloc[0])
            row = []
            for m in methods:
                t = sub[(sub["method"] == m) & (sub["metric"] == "top1_hit")]["value"]
                c = sub[(sub["method"] == m) & (sub["metric"] == "c_index")]["value"]
                row.append(f"{_cell(t)} / {_cell(c)}")
            L.append(f"| {cell} | {n} | " + " | ".join(row) + " |")
    return L


def _cell(v: pd.Series) -> str:
    if v.empty:
        return "-"
    x = v.iloc[0]
    if isinstance(x, str):
        return x
    return "-" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{float(x):.2f}"


def plot_curves(run_dir: Path, preds: pd.DataFrame, items: pd.DataFrame, pq: pd.DataFrame, split: str) -> list[Path]:
    """Coverage-accuracy curve (every method) and calibration plot (methods with estimates)."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out: list[Path] = []
    methods = sorted(preds["method"].unique())
    fig, ax = plt.subplots(figsize=(6, 4))
    drawn = False
    for m in methods:
        curve = mm.coverage_accuracy_curve(pq, preds, items, m, split)
        if not curve.empty:
            ax.plot(curve["coverage"], curve["accuracy"], marker="o", ms=3, label=m)
            drawn = True
    ax.set_xlabel("share of queries answered (most confident first)")
    ax.set_ylabel("top-1 hit rate")
    ax.set_title(f"Coverage-accuracy ({split} split)")
    ax.set_ylim(0, 1)
    if drawn:
        ax.legend(fontsize=8)
    p = run_dir / f"coverage_accuracy_{split}.png"
    fig.tight_layout()
    fig.savefig(p, dpi=120)
    plt.close(fig)
    out.append(p)
    fig, ax = plt.subplots(figsize=(5, 5))
    drawn = False
    for m in methods:
        cal = mm.calibration_table(preds, items, m, split)
        if not cal.empty:
            ax.plot(cal["est_mean"], cal["y_mean"], marker="s", ms=4, label=m)
            drawn = True
    lim = ax.get_xlim() if drawn else (-1, 1)
    ax.plot(lim, lim, color="grey", lw=0.8, ls="--")
    ax.set_xlabel("estimated oriented lrr (bin mean)")
    ax.set_ylabel("observed oriented lrr (bin mean)")
    ax.set_title(f"Calibration ({split} split)")
    if drawn:
        ax.legend(fontsize=8)
    p = run_dir / f"calibration_{split}.png"
    fig.tight_layout()
    fig.savefig(p, dpi=120)
    plt.close(fig)
    out.append(p)
    return out


def write_report(run_dir: Path, metrics: dict[str, Any], config: dict[str, Any], preds: pd.DataFrame,
                 items: pd.DataFrame, queries: pd.DataFrame, pq: pd.DataFrame,
                 reports_dir: Path = REPORTS_DIR) -> Path:
    """Write ``eval_<date>_<run_id>.md`` (and the PNGs next to the run) and return its path."""
    reports_dir.mkdir(parents=True, exist_ok=True)
    rid = config["run_id"]
    date = _dt.date.today().isoformat()
    splits = [s for s in config["splits"]]
    L = [f"# Evaluation run {rid} ({date})", "",
         f"Query set `{config['query_set']}`: {config['n_queries']} queries; methods: {', '.join(config['methods'])}; "
         f"splits: {', '.join(splits)}; {config['reps']} repetitions x 5 folds. Generated by `model/harness/run.py`; "
         f"every number is in `model/harness/runs/{rid}/metrics.json`. Do not edit by hand.", "", HOW_TO_READ, ""]
    exp = metrics.get("random_expectation") or {}
    if exp:
        L += [f"Random expectation on these queries: top-1 {exp['top1_hit']:.1%}, top-half {exp['tophalf_hit']:.1%}, "
              f"C-index 0.500, NDCG@3 {exp['ndcg3']:.3f}, median Spearman 0.", ""]
    full = metrics.get("full_coverage") or {}
    if full.get("methods"):
        L += ["Full coverage (E5 Part 0): every method is scored on all queries; where a method abstained, "
              "its ranking is filled by `practice_prior` and the method is labelled `<method>+prior`. The common "
              "subset is the set of queries every compared method answered in every repetition. Paired differences "
              "are query-level bootstrap intervals (1,000 draws) of the mean difference; a method beats another "
              "only when the interval excludes zero on the spatial split.", ""]
        for split in splits:
            L += [f"## Headline, full coverage ({split} split)", ""]
            L += headline_table({**metrics, "aggregate": full["aggregate"]}, split) + [""]
        for split in splits:
            cs = (metrics.get("common_subset") or {}).get(split)
            if cs:
                L += [f"## Common subset ({split} split, n = {cs['n']} queries answered by every method)", ""]
                L += headline_table({**metrics, "aggregate": cs["aggregate"], "bootstrap95": {}}, split) + [""]
        paired = metrics.get("paired") or {}
        if paired:
            L += ["## Paired differences (a minus b; mean [95 % bootstrap]; * = interval excludes zero)", "",
                  "| pair | split | n | top-1 hit | C-index | NDCG@3 |", "|---|---|---:|---:|---:|---:|"]
            for pair, by_split in paired.items():
                for split, r in by_split.items():
                    cells = []
                    for m in ("top1_hit", "c_index", "ndcg3"):
                        v = r.get(m) or {}
                        if v.get("diff") is None or (isinstance(v.get("diff"), float) and math.isnan(v["diff"])):
                            cells.append("-")
                        else:
                            star = "*" if (v["lo"] > 0 or v["hi"] < 0) else ""
                            cells.append(f"{v['diff']:+.3f} [{v['lo']:+.3f}, {v['hi']:+.3f}]{star}")
                    L.append(f"| {pair} | {split} | {r.get('n', 0)} | " + " | ".join(cells) + " |")
            L.append("")
        L += ["## Per-method answered metrics (secondary: each method on the queries it answered)", ""]
    for split in splits:
        L += [f"### Answered ({split} split)" if full.get("methods") else f"## Headline ({split} split)", ""]
        L += headline_table(metrics, split) + [""]
    fig_dir = reports_dir / "figures" / rid  # next to the report (the run folder itself is git-ignored)
    fig_dir.mkdir(parents=True, exist_ok=True)
    for split in splits:
        figs = plot_curves(fig_dir, preds, items, pq, split)
        L += [f"## Figures ({split} split)", ""]
        for p in figs:
            L.append(f"![{p.stem}](figures/{rid}/{p.name})")
        L.append("")
    L += ["## Breakdowns", "",
          f"Cells with fewer than {metrics.get('min_cell', mm.MIN_CELL)} queries are shown as `n < {metrics.get('min_cell', mm.MIN_CELL)}`."]
    for split in splits:
        L += breakdown_tables(metrics, split)
    um = metrics.get("unmaskable_chunks") or {}
    L += ["", "## Masking", "",
          f"Chunks without study metadata met under a mask: {um.get('n_distinct', 0)} distinct ({um.get('hits', 0)} hits); "
          "they can never be masked and are listed in `metrics.json`." if um.get("n_distinct") else
          "No chunk without study metadata was met under a mask.", ""]
    L += ["## Configuration", "", "| key | value |", "|---|---|"]
    for k in ("run_id", "query_hash", "index_hash", "release", "git_commit", "seed", "started_utc", "elapsed_s"):
        L.append(f"| {k} | `{config.get(k)}` |")
    for s, f in (config.get("fold_files") or {}).items():
        L.append(f"| folds {s} | `{f.get('file')}` sha256 `{(f.get('sha256') or '')[:12]}` |")
    for m, params in (config.get("methods") or {}).items():
        L.append(f"| {m} | `{json.dumps(params, default=str)[:300]}` |")
    for k, v in (config.get("timings_s") or {}).items():
        L.append(f"| time {k} | {v} s |")
    path = reports_dir / f"eval_{date}_{rid}.md"
    path.write_text("\n".join(L) + "\n", encoding="utf-8")
    return path
