"""Run an E7 hybrid through the harness (one hybrid per process; E5 native-crash rule).

Usage::

    python -m model.m3.run --mode stack   # e7_m3_stack: ET, spatial and study, 5 x 5
    python -m model.m3.run --mode gate    # e7_m3_gate
    python -m model.m3.run --mode gate --query-set fresh_2024plus --split fresh   # A6, when the set exists
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from model.harness import HARNESS_DIR, REPO_ROOT
from model.harness import queries as hq
from model.harness import run as hr
from model.m3.engine import M3Engine, load_llm_rankings, qkey_of


def build_engine(mode: str, queries, taxonomy) -> M3Engine:
    from pipelines.geodata.extract import load_aez_lookup

    llm = load_llm_rankings(queries)
    qkeys = {str(r.query_id): qkey_of(r.group, r.site, r.outcome_id, r.crop, r.comparator_class) for r in queries.itertuples()}
    return M3Engine(mode, llm, qkeys,
                    outcome_group={str(r.outcome_id): str(r.objective_group) for r in taxonomy.outcomes.itertuples()},
                    family_of={str(r.practice_id): str(r.practice_family) for r in taxonomy.practices.itertuples()},
                    components_of={str(r.practice_id): [c.strip() for c in str(r.components).split(";") if c.strip()]
                                   for r in taxonomy.practices.itertuples()},
                    belt_code_of={name: code for code, name in load_aez_lookup().items()})


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="E7 hybrid run")
    ap.add_argument("--mode", choices=("stack", "gate"), required=True)
    ap.add_argument("--split", default="spatial,study")
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--query-set", default="ET")
    ap.add_argument("--run-id", default=None)
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO if a.verbose else logging.WARNING, format="%(asctime)s %(levelname)s %(message)s")
    queries, items = hq.load_queries(HARNESS_DIR)
    store = hr.load_store(REPO_ROOT / "data" / "evidence")
    taxonomy = hr.load_taxonomy()
    engine = build_engine(a.mode, queries, taxonomy)
    rid = a.run_id or f"e7_m3_{a.mode}" + ("" if a.query_set == "ET" else f"_{a.query_set}")
    run_dir = hr.run([engine.name], [s for s in a.split.split(",") if s], reps=a.reps, query_set=a.query_set, run_id=rid,
                     report=False, queries_override=queries, items_override=items, store_override=store,
                     taxonomy_override=taxonomy, engine_overrides={engine.name: engine}, fill_prior=False)
    (run_dir / "query_log.json").write_text(json.dumps(engine.query_log, indent=0) + "\n", encoding="utf-8")
    print(run_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
