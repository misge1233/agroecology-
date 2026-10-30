#!/usr/bin/env python3
"""Offline mode report for the evidence-tiered advisory (Phase P9, item G).

For every challenge × objective cell (5 families × 7 indicators = 35) and
every scenario pin of ``rag/eval/queries_v2.jsonl`` (deduplicated lat/lon),
call ``advisory_service.advise()`` and tabulate:

* the mode distribution per cell and overall (model-led / hybrid / knowledge-led),
* knowledge-candidate counts per source,
* a guard: no candidate rationale contains a number other than its counts.

Needs the raster stack and the model artefacts (it runs the real engine) and
the knowledge graph store. Tier-2 guidance retrieval needs chromadb + an
OpenAI key for query embeddings and is OFF by default (``--guidance`` turns
it on); without it the guidance source simply reports 0 — the mode decision
does not depend on it.

Run from the repo root with the backend venv:

    python rag/eval/mode_report.py                # -> rag/eval/results/mode_report.{json,md}
    python rag/eval/mode_report.py --guidance     # also retrieve Tier-2 candidates
    python rag/eval/mode_report.py --max-pins 10  # quick look
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "app" / "backend"
for p in (str(ROOT), str(BACKEND)):
    if p not in sys.path:
        sys.path.insert(0, p)

MODES = ("model-led", "hybrid", "knowledge-led")


def load_pins(path: Path, max_pins: int | None) -> list[tuple[float, float]]:
    seen: dict[tuple[float, float], None] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        seen.setdefault((float(rec["lat"]), float(rec["lon"])), None)
    pins = list(seen)
    return pins[:max_pins] if max_pins else pins


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--queries", type=Path, default=ROOT / "rag" / "eval" / "queries_v2.jsonl")
    ap.add_argument("--out-dir", type=Path, default=ROOT / "rag" / "eval" / "results")
    ap.add_argument("--max-pins", type=int, default=None)
    ap.add_argument("--guidance", action="store_true", help="retrieve Tier-2 candidates (needs chromadb + key)")
    ap.add_argument("--out-name", default="mode_report", help="basename of the .json/.md written to --out-dir")
    args = ap.parse_args(argv)

    from app.services import advisory_service as adv
    from app.services import evidence_service as ev
    from app.services import explain_service as es
    from app.services import recommender_service as svc

    svc.warmup()
    gq = es.get_graph_query()
    if gq is None:
        sys.exit("ERROR: knowledge graph not available — build rag/graph/store/graph.json first.")
    guidance = es.get_guidance_retriever() if args.guidance else None

    class _NoGuidance:
        def retrieve(self, query, k=8):
            return []

    pins = load_pins(args.queries, args.max_pins)
    cells = [(f, i) for f in svc.PRACTICE_FAMILIES for i in svc.INDICATORS]
    print(f"{len(cells)} cells x {len(pins)} pins = {len(cells) * len(pins)} advisories")

    per_cell: dict[tuple[str, str], Counter] = defaultdict(Counter)
    per_cell_cands: dict[tuple[str, str], Counter] = defaultdict(Counter)
    # Why a cell is in its mode: how many pins carried each reason key
    # (strong_evidence vs thin_evidence, in_zone vs other_zones_only ...).
    per_cell_reasons: dict[tuple[str, str], Counter] = defaultdict(Counter)
    funnel = Counter()
    overall = Counter()
    sources = Counter()
    n_cands = []
    guard_failures: list[dict] = []
    errors: list[dict] = []
    t0 = time.time()
    for ci, (family, indicator) in enumerate(cells, 1):
        for lat, lon in pins:
            try:
                out = adv.advise(lat, lon, family, indicator, top_n=3, language="en",
                                 graph_query=gq, guidance_retriever=guidance or _NoGuidance())
            except Exception as exc:  # should not happen: rank-impossible pairs are knowledge-led
                errors.append({"family": family, "indicator": indicator, "lat": lat, "lon": lon, "error": str(exc)[:200]})
                continue
            mode = out["mode"]
            per_cell[(family, indicator)][mode] += 1
            overall[mode] += 1
            for r in out["reasons"]:
                per_cell_reasons[(family, indicator)][r["key"].replace("mode.reason.", "")] += 1
            for k, v in (out.get("funnel") or {}).items():
                if isinstance(v, (int, float)):
                    funnel[k] += v
                elif isinstance(v, dict):  # the guidance quality funnel is nested
                    for k2, v2 in v.items():
                        if isinstance(v2, (int, float)):
                            funnel[f"{k}.{k2}"] += v2
            cands = out["knowledge_candidates"]
            n_cands.append(len(cands))
            for c in cands:
                for s in c["sources"]:
                    sources[s] += 1
                    per_cell_cands[(family, indicator)][s] += 1
                if not ev.rationale_numbers_are_counts(c):
                    guard_failures.append({"family": family, "indicator": indicator, "lat": lat, "lon": lon,
                                           "candidate": c["key"], "rationale": c["rationale_text"]})
        print(f"  [{ci:2d}/{len(cells)}] {family[:28]:28s} x {indicator:22s} {dict(per_cell[(family, indicator)])}", flush=True)

    elapsed = time.time() - t0
    table = []
    for family, indicator in cells:
        c = per_cell[(family, indicator)]
        total = sum(c.values()) or 1
        dominant = max(MODES, key=lambda m: c[m]) if total else "-"
        table.append({
            "family": family, "indicator": indicator, "n": sum(c.values()),
            **{m: c[m] for m in MODES},
            "dominant": dominant,
            "reasons": dict(per_cell_reasons[(family, indicator)]),
            "candidates_by_source": dict(per_cell_cands[(family, indicator)]),
        })
    report = {
        "generated": date.today().isoformat(),
        "queries": str(args.queries.relative_to(ROOT)),
        "n_pins": len(pins), "n_cells": len(cells), "n_advisories": sum(overall.values()),
        "guidance_retrieval": bool(guidance),
        "thresholds": ev.thresholds(),
        "overall": {m: overall[m] for m in MODES},
        "cells_by_dominant_mode": dict(Counter(row["dominant"] for row in table)),
        "candidates": {"mean_per_advisory": round(sum(n_cands) / max(1, len(n_cands)), 2),
                       "by_source": dict(sources)},
        "rationale_number_guard": {"checked": sum(n_cands), "failures": len(guard_failures),
                                   "examples": guard_failures[:5]},
        "guidance_funnel": dict(funnel),
        "reasons_overall": dict(sum((per_cell_reasons[c] for c in cells), Counter())),
        "errors": errors[:20], "n_errors": len(errors),
        "elapsed_s": round(elapsed, 1),
        "cells": table,
    }
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / f"{args.out_name}.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    md = [
        "# Advisory mode report (P9)", "",
        f"Generated {report['generated']} · {report['n_cells']} cells × {report['n_pins']} pins = "
        f"{report['n_advisories']} advisories · thresholds {report['thresholds']} · "
        f"guidance retrieval {'on' if report['guidance_retrieval'] else 'off'} · {report['elapsed_s']} s", "",
        f"**Overall:** " + " · ".join(f"{m} {overall[m]}" for m in MODES)
        + f" · cells by dominant mode: {report['cells_by_dominant_mode']}", "",
        f"**Knowledge candidates:** mean {report['candidates']['mean_per_advisory']} per advisory; by source "
        f"{report['candidates']['by_source']} · rationale-number guard: {report['rationale_number_guard']['failures']} "
        f"failures in {report['rationale_number_guard']['checked']} candidates", "",
        f"**Reasons over all advisories (pins carrying each key):** {report['reasons_overall']}"
        + (f" · guidance funnel {report['guidance_funnel']}" if funnel else ""), "",
        "| challenge | objective | pins | model-led | hybrid | knowledge-led | dominant | reasons (pins) | candidates by source |",
        "|---|---|---:|---:|---:|---:|---|---|---|",
    ]
    for row in table:
        md.append(f"| {row['family']} | {row['indicator']} | {row['n']} | {row['model-led']} | {row['hybrid']} | "
                  f"{row['knowledge-led']} | {row['dominant']} | {row['reasons'] or '—'} | {row['candidates_by_source'] or '—'} |")
    if errors:
        md += ["", f"**Errors ({len(errors)}):**"] + [f"- {e}" for e in errors[:10]]
    (args.out_dir / f"{args.out_name}.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"wrote {args.out_dir / (args.out_name + '.md')}; overall {dict(overall)}; errors {len(errors)}; "
          f"guard failures {len(guard_failures)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
