#!/usr/bin/env python3
"""Compare two mode-report runs pin by pin (U9: conservative vs model ordering).

    python rag/eval/compare_orderings.py rag/eval/results/mode_report_u9_model.json \\
        rag/eval/results/mode_report_u9_conservative.json
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path


def main(a: str, b: str) -> dict:
    ra, rb = (json.loads(Path(p).read_text(encoding="utf-8")) for p in (a, b))
    key = lambda x: (x["f"], x["i"], x["lat"], x["lon"])  # noqa: E731
    ma, mb = {key(x): x for x in ra["advisories"]}, {key(x): x for x in rb["advisories"]}
    common = [k for k in ma if k in mb and ma[k]["top"] and mb[k]["top"]]
    overlap = [len(set(ma[k]["top"]) & set(mb[k]["top"])) / max(len(ma[k]["top"]), 1) for k in common]
    top1 = sum(ma[k]["top"][0] == mb[k]["top"][0] for k in common)
    # The decision's motivating case (P9 report): Physical SWC measures, many soil-loss studies.
    target = ("Erosion control and water management", "soil loss", "physical swc measures")
    has = lambda top: any(p.lower() == target[2] for p in top)  # noqa: E731
    in_a = sum(has(ma[k]["top"]) for k in common if k[:2] == target[:2])
    in_b = sum(has(mb[k]["top"]) for k in common if k[:2] == target[:2])
    n_cell = sum(1 for k in common if k[:2] == target[:2])
    entered = Counter(p for k in common for p in set(mb[k]["top"]) - set(ma[k]["top"]))
    left = Counter(p for k in common for p in set(ma[k]["top"]) - set(mb[k]["top"]))
    out = {
        "n_advisories_compared": len(common),
        "mean_top3_overlap": round(sum(overlap) / max(len(overlap), 1), 3),
        "top1_agreement": round(top1 / max(len(common), 1), 3),
        "physical_swc_soil_loss_in_top3": {ra.get("ordering"): f"{in_a}/{n_cell}", rb.get("ordering"): f"{in_b}/{n_cell}"},
        "most_often_entering_top3": entered.most_common(5),
        "most_often_leaving_top3": left.most_common(5),
    }
    print(json.dumps(out, indent=2))
    if len(sys.argv) > 3:
        Path(sys.argv[3]).write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    return out


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
