"""Retrieval evaluation over the frozen corpus/index (Phase P3, step 2).

Runs the REAL ``rag.retrieve.RagRetriever`` (hybrid dense+BM25, RRF fusion —
the exact retriever behind /explain) over ``queries.jsonl`` and scores the
ranked chunk list against the silver era_code labels:

- Success@4/8/16 — 1.0 iff at least one relevant study's chunk appears
  within the first k retrieved chunks. The PRIMARY metric (did this scenario
  get grounded at all? — research_project_plan.md §2.4).
- Recall@4/8/16 — fraction of a scenario's relevant studies whose chunks
  appear within the first k retrieved chunks (study-level, chunk-depth k).
- MRR — reciprocal rank of the first chunk from any relevant study.

Metrics are reported overall and per practice family / indicator, against
both label sets (strict: family+indicator+practice; family-level:
family+indicator). Needs OPENAI_API_KEY (env or app/backend/.env) for query
embeddings; ~1 embedding call per scenario, no LLM calls.

Usage:  python rag/eval/eval_retrieval.py [--k-max 16] [--limit N]
Writes ``rag/eval/results/retrieval_metrics.json`` and ``.md``.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

EVAL_DIR = Path(__file__).resolve().parent
REPO_ROOT = EVAL_DIR.parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

logger = logging.getLogger(__name__)

QUERIES_PATH = EVAL_DIR / "queries.jsonl"
RESULTS_DIR = EVAL_DIR / "results"
K_LEVELS = (4, 8, 16)


# ------------------------------------------------------------- pure functions
def recall_at_k(ranked_codes: list[str], relevant: set[str], k: int) -> float:
    """|relevant studies seen in the first k chunks| / |relevant|."""
    if not relevant:
        return 0.0
    return len(set(ranked_codes[:k]) & relevant) / len(relevant)


def success_at_k(ranked_codes: list[str], relevant: set[str], k: int) -> float:
    """1.0 iff at least one relevant study appears in the first k chunks."""
    if not relevant:
        return 0.0
    return 1.0 if set(ranked_codes[:k]) & relevant else 0.0


def mrr(ranked_codes: list[str], relevant: set[str]) -> float:
    """1/rank of the first chunk from a relevant study (0 if none)."""
    for i, code in enumerate(ranked_codes, start=1):
        if code in relevant:
            return 1.0 / i
    return 0.0


def score_scenario(
    ranked_codes: list[str], scenario: dict[str, Any]
) -> dict[str, float]:
    """All metrics for one scenario, strict and family-level labels."""
    strict = set(scenario["relevant_era_codes"])
    family = set(scenario.get("relevant_era_codes_family_level") or strict)
    out: dict[str, float] = {"mrr": mrr(ranked_codes, strict),
                             "mrr_family": mrr(ranked_codes, family)}
    for k in K_LEVELS:
        out[f"success@{k}"] = success_at_k(ranked_codes, strict, k)
        out[f"success@{k}_family"] = success_at_k(ranked_codes, family, k)
        out[f"recall@{k}"] = recall_at_k(ranked_codes, strict, k)
        out[f"recall@{k}_family"] = recall_at_k(ranked_codes, family, k)
    return out


def aggregate(per_scenario: list[dict[str, Any]]) -> dict[str, Any]:
    """Mean metrics overall and grouped by family / indicator."""

    def _mean(items: list[dict[str, Any]]) -> dict[str, float]:
        keys = [k for k in items[0]["metrics"]] if items else []
        return {
            k: round(sum(i["metrics"][k] for i in items) / len(items), 4)
            for k in keys
        }

    by_family: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_indicator: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in per_scenario:
        by_family[item["practice_family"]].append(item)
        by_indicator[item["indicator"]].append(item)

    return {
        "n_scenarios": len(per_scenario),
        "overall": _mean(per_scenario),
        "per_family": {
            fam: {"n": len(items), **_mean(items)}
            for fam, items in sorted(by_family.items())
        },
        "per_indicator": {
            ind: {"n": len(items), **_mean(items)}
            for ind, items in sorted(by_indicator.items())
        },
    }


def to_markdown(summary: dict[str, Any]) -> str:
    """Compact md tables for the phase report / paper appendix."""
    cols = (
        [f"success@{k}" for k in K_LEVELS]          # primary metric first
        + [f"recall@{k}" for k in K_LEVELS]
        + ["mrr"]
    )

    def _row(name: str, n: int | str, m: dict[str, float]) -> str:
        return (
            f"| {name} | {n} | "
            + " | ".join(f"{m[c]:.3f}" for c in cols)
            + " | "
            + " | ".join(f"{m[c + '_family']:.3f}" for c in cols)
            + " |"
        )

    header = (
        "| group | n | " + " | ".join(cols) + " | "
        + " | ".join(c + " (fam)" for c in cols) + " |"
    )
    sep = "|" + "---|" * (2 + 2 * len(cols))
    lines = [
        "# Retrieval evaluation — hybrid RagRetriever vs silver era_code labels",
        "",
        "Success@k (≥1 relevant study in the top k — the primary metric) "
        "precedes Recall@k (corpus-coverage diagnostic). Strict labels: "
        "family + indicator + practice. `(fam)` columns: family + indicator "
        "only.",
        "",
        header,
        sep,
        _row("**overall**", summary["n_scenarios"], summary["overall"]),
    ]
    lines.append("")
    lines.append("## Per practice family")
    lines.extend([header, sep])
    for fam, m in summary["per_family"].items():
        lines.append(_row(fam, m["n"], m))
    lines.append("")
    lines.append("## Per indicator")
    lines.extend([header, sep])
    for ind, m in summary["per_indicator"].items():
        lines.append(_row(ind, m["n"], m))
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------- main
def load_queries(path: Path) -> list[dict[str, Any]]:
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--queries", type=Path, default=QUERIES_PATH)
    parser.add_argument("--k-max", type=int, default=max(K_LEVELS))
    parser.add_argument("--limit", type=int, default=0,
                        help="evaluate only the first N scenarios (smoke test)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    from rag.retrieve import default_retriever  # heavy (chromadb) — deferred

    retriever = default_retriever()
    scenarios = load_queries(args.queries)
    if args.limit:
        scenarios = scenarios[: args.limit]

    per_scenario: list[dict[str, Any]] = []
    for s in scenarios:
        chunks = retriever.retrieve(s["query_text"], k=args.k_max)
        ranked_codes = [c.get("era_code") for c in chunks]
        per_scenario.append(
            {
                "scenario_id": s["scenario_id"],
                "practice_family": s["practice_family"],
                "indicator": s["indicator"],
                "practice": s["practice"],
                "n_relevant": len(s["relevant_era_codes"]),
                "retrieved_era_codes": ranked_codes,
                "metrics": score_scenario(ranked_codes, s),
            }
        )
        logger.info(
            "%s  recall@8=%.2f mrr=%.2f  (%s / %s)",
            s["scenario_id"],
            per_scenario[-1]["metrics"]["recall@8"],
            per_scenario[-1]["metrics"]["mrr"],
            s["practice_family"],
            s["indicator"],
        )

    summary = aggregate(per_scenario)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_json = RESULTS_DIR / "retrieval_metrics.json"
    out_json.write_text(
        json.dumps({"summary": summary, "per_scenario": per_scenario}, indent=2)
        + "\n",
        encoding="utf-8",
    )
    out_md = RESULTS_DIR / "retrieval_metrics.md"
    out_md.write_text(to_markdown(summary), encoding="utf-8")
    logger.info("Wrote %s and %s", out_json, out_md)
    logger.info("Overall: %s", json.dumps(summary["overall"]))


if __name__ == "__main__":
    main()
