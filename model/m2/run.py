"""Runs of Methodology 2: dry run, model listing, prefetch, harness runs, stability (E6 Part 5).

Minimal sufficient design (owner, 12 Nov 2026): **spatial split, repetition 0 only**, all
375 ET queries, one call per query per variant; the global set (39 queries) once for
``m2_graph`` with ``gpt-4o-mini``; stability on 40 fixed queries. Each run:

1. **collect**: fit the engine per fold of the plan (masked cards, masked graph view) and
   build every prompt without calling (passages are retrieved with the fold's mask);
2. **prefetch**: send the uncached prompts concurrently through the capped client (the
   budget cap stops before it would be exceeded);
3. **harness**: :func:`model.harness.run.run` with the engine (answers come from the cache;
   only validation retries call), ``practice_prior`` beside it for the full-coverage fill;
   the engine's per-query log goes to ``responses.jsonl`` in the run folder.

Usage::

    python -m model.m2.run --dry-run [--models gpt-4o-mini,<strong>]
    python -m model.m2.run --list-models
    python -m model.m2.run --variant m2_cards [--model gpt-4o-mini] [--query-set ET] [--budget-usd 100]
    python -m model.m2.run --stability
    python -m model.m2.run --variant m2_cards --offline --run-id e6_m2_cards_b   # rerun from the cache only
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import pandas as pd

from model.harness import HARNESS_DIR, REPO_ROOT, RUNS_DIR
from model.harness import queries as hq
from model.harness import run as hr
from model.m2 import CACHE_DIR
from model.m2 import prompt as pm
from model.m2.client import DEFAULT_BUDGET, ChatClient, Ledger, chat_tokens, cost_usd, load_prices, price_of
from model.m2.engine import SERVING_MODEL, VARIANTS, M2Engine, log_lines, method_name
from model.m2.knowledge import GraphFacts, PassageSource, default_tiered_retriever, n_tokens

logger = logging.getLogger(__name__)

SPLIT, REP = "spatial", 0
STABILITY_N = 40
OUT_PER_CANDIDATE, OUT_BASE = 45, 25   # output-token estimate per answer (ids, class, confidence, cards, reason)


# ----------------------------------------------------------------- shared inputs
class Inputs:
    """Store, queries, taxonomy maps, the retriever and the graph, loaded once per process."""

    def __init__(self, store_dir: Path = REPO_ROOT / "data" / "evidence") -> None:
        self.queries, self.items = hq.load_queries(HARNESS_DIR)
        self.store = hr.load_store(store_dir)
        self.train_rows = hq.eligible_rows(self.store)
        tx = hr.load_taxonomy()
        self.maps = {
            "outcome_group": {str(r.outcome_id): str(r.objective_group) for r in tx.outcomes.itertuples()},
            "practice_name": {str(r.practice_id): str(r.name_en) for r in tx.practices.itertuples()},
            "outcome_name": {str(r.outcome_id): str(r.name_en) for r in tx.outcomes.itertuples()},
            "outcome_direction": {str(r.outcome_id): int(float(r.direction)) if str(r.direction).strip() not in ("", "nan") else 1
                                  for r in tx.outcomes.itertuples()},
            "components_of": {str(r.practice_id): [c.strip() for c in str(r.components).split(";") if c.strip()]
                              for r in tx.practices.itertuples()},
        }
        try:
            from pipelines.geodata.extract import load_aez_lookup

            self.maps["belt_name_of"] = {int(k): v for k, v in load_aez_lookup().items()}
        except Exception:  # noqa: BLE001
            self.maps["belt_name_of"] = {}
        self.taxonomy = tx
        self._passages: PassageSource | None = None
        self._graph: GraphFacts | None = None
        self.embed_ledger: Ledger | None = None

    def passages(self, ledger: Ledger) -> PassageSource:
        if self._passages is None:
            prices = load_prices()

            def on_embed(text: str) -> None:
                n = n_tokens(text)
                ledger.settle(0.0, {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "kind": "embedding", "model": "text-embedding-3-small",
                                    "prompt_tokens": n, "completion_tokens": 0,
                                    "cost_usd": cost_usd("text-embedding-3-small", n, 0, prices)})

            self._passages = PassageSource(default_tiered_retriever(on_embed), cache_dir=CACHE_DIR / "passages")
        return self._passages

    def graph(self) -> GraphFacts:
        if self._graph is None:
            self._graph = GraphFacts()
        return self._graph

    def select(self, query_set: str) -> pd.DataFrame:
        return hr.select_queries(self.queries, query_set).reset_index(drop=True)

    def plan(self, queries: pd.DataFrame) -> list[tuple[int, int, list[str], Any]]:
        return [p for p in hr.fold_plan(SPLIT, queries, HARNESS_DIR, REP + 1, self.store) if p[0] == REP]


def make_engine(inp: Inputs, variant: str, client: Any, mode: str = "call", shuffle_seed: int | None = None,
                repeat: str | None = None, name: str | None = None) -> M2Engine:
    ledger = getattr(client, "ledger", None) or Ledger()
    return M2Engine(variant, client, **inp.maps,
                    passages=inp.passages(ledger) if variant in ("m2_rag", "m2_graph") else None,
                    graph=inp.graph() if variant == "m2_graph" else None, mode=mode, shuffle_seed=shuffle_seed,
                    repeat=repeat, name=name)


def stability_queries(queries: pd.DataFrame, n: int = STABILITY_N) -> list[str]:
    """The 40 fixed queries of the stability check: ET queries ordered by the hash of their id."""
    et = queries[queries["query_set"] == "ET"]["query_id"].astype(str).tolist()
    return sorted(et, key=lambda q: hashlib.sha256(q.encode("utf-8")).hexdigest())[:n]


# ----------------------------------------------------------------- collect / prefetch
def collect(inp: Inputs, engine: M2Engine, queries: pd.DataFrame, only: set[str] | None = None) -> list[dict[str, Any]]:
    """Every prompt of the plan (spatial, repetition 0) built under its fold's mask, no calls."""
    mode = engine.mode
    engine.mode, engine.collected = "collect", []
    for rep, fold, held, mask in inp.plan(queries):
        held = [h for h in held if only is None or h in only]
        if not held:
            continue
        engine.fit(inp.train_rows, mask)
        engine.fold_tag.update({"split": SPLIT, "rep": rep, "fold": fold})
        for _, q in queries[queries["query_id"].isin(held)].iterrows():
            engine.rank(hr.request_of(q, inp.items, mask))
    engine.mode = mode
    return engine.collected


def prefetch(client: ChatClient, prompts: list[dict[str, Any]], workers: int = 8, repeat: str | None = None) -> dict[str, Any]:
    """Send the uncached prompts concurrently; returns calls, cache hits, cost and failures."""
    todo = [p for p in prompts if client.cached(p["messages"], p["schema"], repeat) is None]
    t0, fails = time.time(), []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(client.chat, p["messages"], p["schema"], repeat): p["query_id"] for p in todo}
        for f in as_completed(futs):
            try:
                f.result()
            except Exception as exc:  # noqa: BLE001 - budget or API failure: reported, the run stops below
                fails.append((futs[f], f"{type(exc).__name__}: {exc}"))
    return {"prompts": len(prompts), "sent": len(todo) - len(fails), "cached_before": len(prompts) - len(todo),
            "failures": fails, "seconds": round(time.time() - t0, 1)}


# ----------------------------------------------------------------- dry run
def estimate_rows(prompts: list[dict[str, Any]], model: str, prices: dict[str, Any]) -> dict[str, Any]:
    p = price_of(model, prices)
    n_in = sum(chat_tokens(x["messages"]) for x in prompts)
    n_out = sum(OUT_BASE + OUT_PER_CANDIDATE * len(x["schema"]["schema"]["properties"]["ranking"]["items"]["enum"]) for x in prompts)
    n_out += len(prompts) * int(p.get("reasoning_tokens", 0))
    return {"calls": len(prompts), "input_tokens": n_in, "output_tokens": n_out,
            "mean_input": round(n_in / max(1, len(prompts))), "max_input": max((chat_tokens(x["messages"]) for x in prompts), default=0),
            "usd": round(cost_usd(model, n_in, n_out, prices), 4)}


def dry_run(inp: Inputs, models: list[str], strong: str | None) -> list[dict[str, Any]]:
    prices = load_prices()
    ledger = Ledger()
    spent0 = ledger.total()
    rows = []
    et, gl = inp.select("ET"), inp.select("global")
    stab = set(stability_queries(inp.queries))
    built: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for v in VARIANTS:
        eng = make_engine(inp, v, ChatClient(SERVING_MODEL, offline=True, ledger=ledger), mode="collect")
        built[(v, "ET")] = collect(inp, eng, et)
        logger.info("dry run: %s ET %d prompts", v, len(built[(v, "ET")]))
    eng = make_engine(inp, "m2_graph", ChatClient(SERVING_MODEL, offline=True, ledger=ledger), mode="collect")
    built[("m2_graph", "global")] = collect(inp, eng, gl)
    stab_prompts = [p for p in built[("m2_graph", "ET")] if p["query_id"] in stab]
    for v in VARIANTS:
        rows.append({"run": f"{v} ET", "model": SERVING_MODEL, **estimate_rows(built[(v, "ET")], SERVING_MODEL, prices)})
    rows.append({"run": "m2_graph global", "model": SERVING_MODEL, **estimate_rows(built[("m2_graph", "global")], SERVING_MODEL, prices)})
    # stability: 2 repeated calls and 2 shuffled orders of the 40 queries (shuffling changes only the order)
    rows.append({"run": "stability m2_graph (40 x 4)", "model": SERVING_MODEL, **estimate_rows(stab_prompts * 4, SERVING_MODEL, prices)})
    for m in models:
        if m == SERVING_MODEL:
            continue
        rows.append({"run": "m2_graph ET", "model": m, **estimate_rows(built[("m2_graph", "ET")], m, prices)})
    if strong and strong not in models:
        rows.append({"run": "m2_graph ET", "model": strong, **estimate_rows(built[("m2_graph", "ET")], strong, prices)})
    emb = ledger.total() - spent0
    rows.append({"run": "query embeddings (retrieval, cached)", "model": "text-embedding-3-small", "calls": None,
                 "input_tokens": None, "output_tokens": None, "mean_input": None, "max_input": None, "usd": round(emb, 4)})
    sizes = [p["n_cards"] for p in built[("m2_cards", "ET")]]
    logger.info("cards per prompt: mean %.1f, max %d", sum(sizes) / max(1, len(sizes)), max(sizes, default=0))
    return rows


def print_table(rows: list[dict[str, Any]]) -> None:
    cols = ["run", "model", "calls", "input_tokens", "output_tokens", "mean_input", "max_input", "usd"]
    print("| " + " | ".join(cols) + " |")
    print("|" + "|".join("---" for _ in cols) + "|")
    for r in rows:
        print("| " + " | ".join("" if r.get(c) is None else str(r[c]) for c in cols) + " |")
    tot = sum(r["usd"] for r in rows if r.get("usd") is not None)
    print(f"\nTotal estimate (all rows): {tot:.2f} USD; ledger so far: {Ledger().total():.4f} USD")


# ----------------------------------------------------------------- harness run of one variant
def run_variant(inp: Inputs, variant: str, model: str, query_set: str, budget: float, run_id: str | None,
                workers: int, offline: bool = False) -> Path:
    client = ChatClient(model, budget_usd=budget, offline=offline)
    name = method_name(variant, model)
    rid = run_id or f"e6_{name}_{query_set.lower()}"
    queries = inp.select(query_set)
    engine = make_engine(inp, variant, client)
    if not offline:
        prompts = collect(inp, engine, queries)
        pf = prefetch(client, prompts, workers)
        logger.info("prefetch %s: %s", name, {k: v for k, v in pf.items() if k != "failures"})
        if pf["failures"]:
            for qid, err in pf["failures"][:5]:
                logger.error("prefetch failure %s: %s", qid, err)
            raise SystemExit(f"{len(pf['failures'])} prefetch failures (first: {pf['failures'][0][1]}); nothing scored")
    engine.log = []
    run_dir = hr.run([name, "practice_prior"], [SPLIT], reps=REP + 1, query_set=query_set, run_id=rid, report=False,
                     queries_override=inp.queries, items_override=inp.items, store_override=inp.store,
                     taxonomy_override=inp.taxonomy, engine_overrides={name: engine})
    (run_dir / "responses.jsonl").write_text(log_lines(engine.log), encoding="utf-8")
    cfg = json.loads((run_dir / "config.json").read_text(encoding="utf-8"))
    cfg["m2"] = {"variant": variant, "model": model, "prompt_version": pm.PROMPT_VERSION, "prompt_hash": pm.prompt_hash(),
                 "design": "spatial split, repetition 0, one call per query (owner, 12 Nov 2026)", "offline": offline,
                 "client_stats": client.stats, "ledger_total_usd": round(client.ledger.total(), 4), "budget_usd": budget}
    (run_dir / "config.json").write_text(json.dumps(cfg, indent=1, default=str) + "\n", encoding="utf-8")
    return run_dir


# ----------------------------------------------------------------- stability
def stability(inp: Inputs, model: str, budget: float, workers: int, run_id: str = "e6_m2_stability") -> Path:
    """m2_graph on the 40 fixed queries: 2 repeated calls bypassing the cache (own cache keys)
    and 2 shuffled candidate orders; rankings logged per condition."""
    client = ChatClient(model, budget_usd=budget)
    only = set(stability_queries(inp.queries))
    queries = inp.select("ET")
    conditions = {"repeat_1": {"repeat": "stability_r1"}, "repeat_2": {"repeat": "stability_r2"},
                  "shuffle_1": {"shuffle_seed": 1, "repeat": "stability_s1"},
                  "shuffle_2": {"shuffle_seed": 2, "repeat": "stability_s2"}}
    out: dict[str, list[dict[str, Any]]] = {}
    for cond, kw in conditions.items():
        eng = make_engine(inp, "m2_graph", client, **kw)
        prompts = collect(inp, eng, queries, only)
        pf = prefetch(client, prompts, workers, repeat=kw.get("repeat"))
        if pf["failures"]:
            raise SystemExit(f"stability prefetch failures: {pf['failures'][:3]}")
        eng.log = []
        for rep, fold, held, mask in inp.plan(queries):
            held = [h for h in held if h in only]
            if not held:
                continue
            eng.fit(inp.train_rows, mask)
            for _, q in queries[queries["query_id"].isin(held)].iterrows():
                eng.rank(hr.request_of(q, inp.items, mask))
        out[cond] = eng.log
    run_dir = RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "stability_log.jsonl").write_text("".join(log_lines(v) for v in out.values()), encoding="utf-8")
    (run_dir / "config.json").write_text(json.dumps({"model": model, "variant": "m2_graph", "queries": sorted(only),
                                                     "conditions": conditions, "prompt_version": pm.PROMPT_VERSION,
                                                     "prompt_hash": pm.prompt_hash(), "client_stats": client.stats},
                                                    indent=1) + "\n", encoding="utf-8")
    return run_dir


# ----------------------------------------------------------------- cli
def propose_strong(ids: list[str], prices: dict[str, Any]) -> str | None:
    """The strongest general chat model on the key, by a fixed preference order (priced models only)."""
    order = ["gpt-5", "o3", "gpt-4.1", "gpt-4o", "o4-mini", "gpt-5-mini", "gpt-4.1-mini"]
    for m in order:
        if m in ids and m in prices:
            return m
    return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Methodology 2 runs (E6)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--list-models", action="store_true")
    ap.add_argument("--stability", action="store_true")
    ap.add_argument("--variant", choices=VARIANTS)
    ap.add_argument("--model", default=SERVING_MODEL)
    ap.add_argument("--models", default=SERVING_MODEL, help="dry run: comma list of models to price")
    ap.add_argument("--strong", default=None, help="dry run: the proposed stronger model")
    ap.add_argument("--query-set", default="ET")
    ap.add_argument("--budget-usd", type=float, default=DEFAULT_BUDGET)
    ap.add_argument("--run-id", default=None)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--offline", action="store_true", help="answers from the cache only (no request)")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO if a.verbose else logging.WARNING, format="%(asctime)s %(levelname)s %(message)s")
    if a.list_models:
        ids = ChatClient(SERVING_MODEL).list_models()
        print("\n".join(ids))
        print(f"\nproposed stronger model: {propose_strong(ids, load_prices())}")
        return 0
    inp = Inputs()
    if a.dry_run:
        print_table(dry_run(inp, [m for m in a.models.split(",") if m], a.strong))
        return 0
    if a.stability:
        print(stability(inp, a.model, a.budget_usd, a.workers))
        return 0
    if not a.variant:
        ap.error("--variant, --dry-run, --stability or --list-models")
    print(run_variant(inp, a.variant, a.model, a.query_set, a.budget_usd, a.run_id, a.workers, a.offline))
    return 0


if __name__ == "__main__":
    sys.exit(main())
