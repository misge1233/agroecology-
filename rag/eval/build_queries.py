"""Build the retrieval-evaluation query set (Phase P3, step 1).

Scenarios are sampled from the frozen model-ready dataset
(``data/processed/CSA_ERA_final_model_ready.csv``): each scenario is a real
ERA study location crossed with the practice family x indicator studied
there, stratified across the 5 practice families and 7 indicators.

Silver relevance labels come from the era_code linkage the corpus was built
on: for each scenario the relevant studies are the ERA-source era_codes
(``Study_No_`` minus the ``ERA_`` prefix) whose dataset rows match the
scenario's practice family + indicator + top practice, restricted to studies
that actually contribute chunks to the corpus. Scenarios whose relevant set
is empty after that restriction are skipped and counted.

The retrieval query text is composed with the REAL ``rag.retrieve
.build_query_text`` over a recommendation-shaped dict, so the evaluation
exercises exactly the query the app would send (wrap, never fork).

Usage (from repo root or rag/eval, any Python with ``requests`` installed):
    python rag/eval/build_queries.py [--n-target 50] [--seed 42]
Writes ``rag/eval/queries.jsonl`` and ``rag/eval/results/queries_build_report.json``.
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import random
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

EVAL_DIR = Path(__file__).resolve().parent
REPO_ROOT = EVAL_DIR.parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from rag.retrieve import build_query_text  # noqa: E402  (real query composer)

logger = logging.getLogger(__name__)

DATASET_PATH = REPO_ROOT / "data" / "processed" / "CSA_ERA_final_model_ready.csv"
CHUNKS_PATH = REPO_ROOT / "rag" / "corpus" / "chunks.jsonl"
QUERIES_PATH = EVAL_DIR / "queries.jsonl"
REPORT_PATH = EVAL_DIR / "results" / "queries_build_report.json"

ERA_PREFIX = "ERA_"


# ------------------------------------------------------------- pure functions
def strip_era_prefix(study_no: str) -> str:
    """``ERA_NN0206`` -> ``NN0206`` (non-ERA ids returned unchanged)."""
    return study_no[len(ERA_PREFIX):] if study_no.startswith(ERA_PREFIX) else study_no


def load_rows(csv_path: Path) -> list[dict[str, str]]:
    """All dataset rows (dicts keyed by the frozen column names)."""
    with open(csv_path, encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def load_corpus_codes(chunks_path: Path) -> set[str]:
    """era_codes that contribute at least one chunk to the corpus."""
    codes: set[str] = set()
    with open(chunks_path, encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                codes.add(json.loads(line)["era_code"])
    return codes


def era_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """ERA-source rows only — the ones with an era_code-linkable Study_No_."""
    return [r for r in rows if r.get("source") == "ERA"]


def relevant_studies(
    rows: list[dict[str, str]],
    practice_family: str,
    indicator: str,
    practice: str | None,
    corpus_codes: set[str],
) -> list[str]:
    """Silver labels: corpus-backed era_codes whose rows match the scenario.

    Match = same practice family + indicator, and same top practice when one
    is given. Only ERA-source rows carry era_codes; only studies with chunks
    in the corpus can ever be retrieved, so others are excluded up front.
    """
    codes: set[str] = set()
    for r in rows:
        if r.get("source") != "ERA":
            continue
        if r["practice_family"] != practice_family or r["Indicator"] != indicator:
            continue
        if practice is not None and r["CSA_practices"] != practice:
            continue
        code = strip_era_prefix(r["Study_No_"])
        if code in corpus_codes:
            codes.add(code)
    return sorted(codes)


def make_recommendation_stub(anchor: dict[str, str]) -> dict[str, Any]:
    """Recommendation-shaped dict for ``build_query_text`` / the retriever.

    Mirrors the fields of ``recommend.py`` output that query composition
    reads (query.practice_family/indicator/crop_type, recommendations[0]
    .practice, details.context.aez_belt/Rainfall/slope). Effect numbers are
    deliberately absent — retrieval evaluation never needs them.
    """

    def _f(key: str) -> float | None:
        try:
            return round(float(anchor[key]), 2)
        except (KeyError, TypeError, ValueError):
            return None

    return {
        "query": {
            "lat": _f("latitude"),
            "lon": _f("longitude"),
            "practice_family": anchor["practice_family"],
            "indicator": anchor["Indicator"],
            "crop_type": anchor.get("crop_type") or None,
        },
        "recommendations": [{"practice": anchor["CSA_practices"]}],
        "details": {
            "context": {
                "aez_belt": anchor.get("aez_belt") or None,
                "Rainfall": _f("Rainfall"),
                "slope": _f("slope"),
            }
        },
    }


def build_scenarios(
    rows: list[dict[str, str]],
    corpus_codes: set[str],
    n_target: int = 50,
    seed: int = 42,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Sample ~n_target scenarios stratified over (family, indicator) cells.

    Deterministic for a given seed. Anchors are drawn from the cell's ERA
    study rows (distinct studies first), so every scenario is a real study
    location. Candidates whose relevant-study set contributes zero chunks to
    the corpus are skipped and counted. Returns (scenarios, report).
    """
    rng = random.Random(seed)
    era = era_rows(rows)

    cells: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for r in era:
        cells[(r["practice_family"], r["Indicator"])].append(r)

    per_cell = max(1, round(n_target / max(1, len(cells))))
    scenarios: list[dict[str, Any]] = []
    n_skipped_no_relevant = 0
    families: set[str] = set()
    indicators: set[str] = set()

    for (family, indicator), cell_rows in sorted(cells.items()):
        # One candidate anchor row per distinct study, then sample cell picks.
        by_study: dict[str, list[dict[str, str]]] = defaultdict(list)
        for r in cell_rows:
            by_study[r["Study_No_"]].append(r)
        study_ids = sorted(by_study)
        rng.shuffle(study_ids)

        taken = 0
        for study_id in study_ids:
            if taken >= per_cell:
                break
            anchor = rng.choice(by_study[study_id])
            relevant = relevant_studies(
                rows, family, indicator, anchor["CSA_practices"], corpus_codes
            )
            if not relevant:
                n_skipped_no_relevant += 1
                continue
            rec = make_recommendation_stub(anchor)
            scenarios.append(
                {
                    "scenario_id": f"S{len(scenarios) + 1:03d}",
                    "practice_family": family,
                    "indicator": indicator,
                    "practice": anchor["CSA_practices"],
                    "crop_type": anchor.get("crop_type") or None,
                    "anchor_study": anchor["Study_No_"],
                    "lat": rec["query"]["lat"],
                    "lon": rec["query"]["lon"],
                    "aez_belt": anchor.get("aez_belt") or None,
                    "recommendation": rec,
                    "query_text": build_query_text(
                        rec, practice=anchor["CSA_practices"]
                    ),
                    "relevant_era_codes": relevant,
                    "relevant_era_codes_family_level": relevant_studies(
                        rows, family, indicator, None, corpus_codes
                    ),
                }
            )
            families.add(family)
            indicators.add(indicator)
            taken += 1

    report = {
        "n_scenarios": len(scenarios),
        "n_target": n_target,
        "per_cell_quota": per_cell,
        "n_cells_with_scenarios": len(
            {(s["practice_family"], s["indicator"]) for s in scenarios}
        ),
        "n_cells_total": len(cells),
        "n_skipped_no_relevant_in_corpus": n_skipped_no_relevant,
        "n_families_covered": len(families),
        "n_indicators_covered": len(indicators),
        "seed": seed,
    }
    return scenarios, report


# --------------------------------------------------------------------- main
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--n-target", type=int, default=50)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--dataset", type=Path, default=DATASET_PATH)
    parser.add_argument("--chunks", type=Path, default=CHUNKS_PATH)
    parser.add_argument("--out", type=Path, default=QUERIES_PATH)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    rows = load_rows(args.dataset)
    corpus_codes = load_corpus_codes(args.chunks)
    scenarios, report = build_scenarios(
        rows, corpus_codes, n_target=args.n_target, seed=args.seed
    )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        for s in scenarios:
            fh.write(json.dumps(s, ensure_ascii=False) + "\n")
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    logger.info("Wrote %d scenarios to %s", len(scenarios), args.out)
    logger.info(
        "Skipped %d scenario candidates whose relevant studies contribute "
        "zero chunks to the corpus.",
        report["n_skipped_no_relevant_in_corpus"],
    )
    logger.info("Build report: %s", json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
