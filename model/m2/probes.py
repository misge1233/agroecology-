"""Recall probes of the zero-evidence LLM (E7 Part A5; ``gpt-4.1-mini`` only).

80 ET queries, **one query per study group**, stratified by objective group and source
(pre-registered rule, fixed 12 Nov 2026 before any probe ran):

1. a representative query per study group: the group's ET query with the smallest
   ``sha256(query_id)``;
2. strata are ``(objective_group, sources)`` of the representative; 80 places are allocated
   to strata in proportion to their number of groups (largest remainder, ties by stratum
   name); inside a stratum the groups are taken in ``sha256(group)`` order.

Two probes on the same 80 queries:

* **identification**: the exact ``m2_zero`` user message with its task line replaced by "name
  the published study (first author's surname, year, journal) or say unknown"; a match is the
  first author's surname (accents and case ignored) and the year within one;
* **title lift**: the ``m2_zero`` question again, unchanged except for one added line
  ``STUDY: <title> (DOI: <doi>)`` (title or DOI alone when only one is known); the top-1 hit of
  the model's ranking with the line minus without it (the cached E6 ``m2_zero`` answer) on the
  queries both answered validly. The top-1 hit uses the model's ranked list even where it
  classed a candidate ``unknown`` (the position is the model's order). **The lift is computed
  on the queries that received a line** (fixed before the run: 75 of the 80 have a title or a
  DOI; the 5 without one cannot be treated and would add zeros by construction); the all-80
  figure is reported beside it.

Ground truth: first author and year from the store citation of the group's rows
(:func:`model.m2.cards.short_citation`); titles from the Tier 1 corpus (by DOI, then ERA
code) or parsed from full CSA citations. Rates and the lift carry bootstrap 95 % intervals
(1,000 draws, seeded). Output: ``model/harness/runs/e7_recall_probes/``.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from model.harness import REPO_ROOT, RUNS_DIR
from model.harness.mask import Mask, era_code_of, group_keys
from model.m2.cards import short_citation
from model.m2.client import ChatClient, Ledger
from model.m2.engine import M2Engine, log_lines

N_PROBES = 80
PROBE_VERSION = "probe-p1"
RUN_ID = "e7_recall_probes"
TASK_LINE = "TASK: rank all candidates for the objective in this context and answer in the JSON format."
ID_TASK = ("TASK: this describes one published field trial. Name the published study that reports it: the first author's "
           "surname, the publication year and the journal. If you do not know which study it is, set known to false.")
ID_SYSTEM = ("You are an expert on the published agricultural research literature on Ethiopia. You will see the description "
             "of one field trial: the site context, the objective, the crop and the practices compared. Answer only with the "
             "JSON object requested.")
ID_SCHEMA = {"name": "study_identification", "strict": True, "schema": {
    "type": "object", "additionalProperties": False, "required": ["known", "first_author_surname", "year", "journal"],
    "properties": {"known": {"type": "boolean"}, "first_author_surname": {"type": "string"},
                   "year": {"type": "integer"}, "journal": {"type": "string"}}}}


def _h(s: str) -> str:
    return hashlib.sha256(str(s).encode("utf-8")).hexdigest()


def norm_name(s: Any) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z]", "", s.lower())


# ----------------------------------------------------------------- sample and ground truth
def sample_queries(queries: pd.DataFrame, n: int = N_PROBES) -> pd.DataFrame:
    """The pre-registered stratified sample: one ET query per study group (see module doc)."""
    et = queries[queries["query_set"] == "ET"].copy()
    et["_h"] = et["query_id"].map(_h)
    rep = et.sort_values("_h").groupby("group", sort=True).head(1).copy()
    rep["stratum"] = rep["objective_group"].astype(str) + "|" + rep["sources"].astype(str)
    sizes = rep.groupby("stratum").size().sort_index()
    n = min(n, len(rep))
    quota = sizes / sizes.sum() * n
    alloc = np.floor(quota).astype(int)
    rest = n - int(alloc.sum())
    order = sorted(sizes.index, key=lambda s: (-(quota[s] - alloc[s]), s))
    for s in order[:rest]:
        alloc[s] += 1
    picked = []
    for s, k in alloc.items():
        block = rep[rep["stratum"] == s].assign(_g=lambda d: d["group"].map(_h)).sort_values("_g")
        picked.append(block.head(int(k)))
    return pd.concat(picked).drop(columns=["_h", "_g"], errors="ignore").sort_values("query_id").reset_index(drop=True)


def corpus_titles(path: Path = REPO_ROOT / "rag" / "corpus" / "chunks.jsonl") -> dict[tuple[str, str], tuple[str, str | None]]:
    """``("doi", doi) | ("era_code", code) -> (title, journal)`` from the Tier 1 corpus."""
    out: dict[tuple[str, str], tuple[str, str | None]] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        c = json.loads(line)
        if not c.get("title"):
            continue
        if c.get("doi"):
            out.setdefault(("doi", str(c["doi"]).strip().lower()), (c["title"], c.get("journal")))
        if c.get("era_code"):
            out.setdefault(("era_code", str(c["era_code"])), (c["title"], c.get("journal")))
    return out


def title_from_citation(citation: Any) -> str | None:
    """The title of a full reference ``Author, A. (2009). Title. Journal, ...`` (CSA rows)."""
    m = re.search(r"\((?:19|20)\d{2}[a-z]?\)\.\s*(.+?\.)\s", str(citation or ""))
    if not m:
        return None
    t = m.group(1).rstrip(".").strip()
    return t if len(t.split()) >= 4 else None


def ground_truth(store: pd.DataFrame, groups: list[str]) -> dict[str, dict[str, Any]]:
    """Per study group: first-author surname, year, journal (when known), title and DOI."""
    s = store.assign(group=group_keys(store))
    s = s[s["group"].isin(set(groups))]
    titles = corpus_titles()
    out = {}
    for g, rows in s.groupby("group", sort=True):
        r = rows.iloc[0]
        short = short_citation(r.get("citation"), r.get("year"))
        parts = short.split()
        year = int(parts[-1]) if parts and parts[-1].isdigit() else None
        doi = r["doi"].strip().lower() if isinstance(r.get("doi"), str) and r["doi"].strip() else None
        hit = titles.get(("doi", doi)) if doi else None
        code = era_code_of(str(r["study_id"]))
        if hit is None and code:
            hit = titles.get(("era_code", code))
        title, journal = (hit if hit else (title_from_citation(r.get("citation")), None))
        out[g] = {"surname": parts[0] if parts and parts[0] != "unknown" else None, "year": year, "doi": doi,
                  "title": title, "journal": journal, "citation": str(r.get("citation") or "")[:160]}
    return out


def identified(answer: dict[str, Any] | None, truth: dict[str, Any]) -> bool:
    """Surname match (accents and case ignored, the truth surname as a whole token) and year within one."""
    if not isinstance(answer, dict) or not answer.get("known") or not truth.get("surname") or truth.get("year") is None:
        return False
    want = norm_name(truth["surname"])
    tokens = {norm_name(t) for t in re.split(r"[\s,;.]+", str(answer.get("first_author_surname") or "")) if t}
    try:
        year_ok = abs(int(answer.get("year") or 0) - int(truth["year"])) <= 1
    except (TypeError, ValueError):
        year_ok = False
    return bool(want) and want in tokens and year_ok


def study_line(t: dict[str, Any]) -> str | None:
    if t.get("title") and t.get("doi"):
        return f"{t['title']} (DOI: {t['doi']})"
    if t.get("title"):
        return t["title"]
    if t.get("doi"):
        return f"DOI: {t['doi']}"
    return None


class TitledZero(M2Engine):
    """``m2_zero`` with one added ``STUDY:`` line (the title-lift arm)."""

    def __init__(self, *args: Any, lines: dict[str, str], **kw: Any) -> None:
        super().__init__("m2_zero", *args, name="m2_zero_titled", **kw)
        self.lines = dict(lines)

    def build(self, req: Any) -> Any:
        b = super().build(req)
        line = self.lines.get(req.query_id)
        if line:
            b.user = b.user.replace("\n\nCANDIDATES:", f"\nSTUDY: {line}\n\nCANDIDATES:", 1)
        return b


# ----------------------------------------------------------------- run
def top1(entry: dict[str, Any], truth_y: dict[str, float]) -> float | None:
    if not entry.get("valid"):
        return None
    items = entry["items"]
    best = min(items, key=lambda p: items[p]["rank"])
    ys = [truth_y[p] for p in items if p in truth_y]
    return float(truth_y.get(best, -np.inf) == max(ys)) if ys else None


def bootstrap_mean(v: np.ndarray, n_boot: int = 1000, seed: int = 0) -> tuple[float, float, float]:
    rng = np.random.default_rng(seed)
    v = np.asarray(v, float)
    if len(v) == 0:
        return float("nan"), float("nan"), float("nan")
    means = [v[rng.integers(0, len(v), len(v))].mean() for _ in range(n_boot)]
    return float(v.mean()), float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def run(inp: Any, budget: float, ledger_dir: Path, workers: int = 6, model: str = "gpt-4.1-mini",
        offline: bool = False) -> Path:
    from concurrent.futures import ThreadPoolExecutor

    from model.harness import run as hr
    from model.m2.run import make_engine

    client = ChatClient(model, budget_usd=budget, ledger=Ledger(Path(ledger_dir) / "ledger.jsonl"), offline=offline)
    sample = sample_queries(inp.queries)
    truth = ground_truth(inp.store, sample["group"].astype(str).tolist())
    lines = {q: study_line(truth[g]) for q, g in zip(sample["query_id"], sample["group"])}
    items = inp.items
    reqs = [hr.request_of(q, items, Mask.empty()) for _, q in sample.iterrows()]
    # identification: the m2_zero user message with the identification task
    zero = make_engine(inp, "m2_zero", client)
    zero.fit(inp.train_rows, Mask.empty())
    id_msgs = []
    for req in reqs:
        user = zero.build(req).user.replace(TASK_LINE, ID_TASK)
        id_msgs.append([{"role": "system", "content": ID_SYSTEM}, {"role": "user", "content": user}])
    with ThreadPoolExecutor(max_workers=workers) as ex:
        id_recs = list(ex.map(lambda m: client.chat(m, ID_SCHEMA), id_msgs))
    # title lift: without (the cached E6 m2_zero answer) and with the STUDY line
    titled = TitledZero(client, **inp.maps, lines=lines)
    titled.fit(inp.train_rows, Mask.empty())
    with ThreadPoolExecutor(max_workers=workers) as ex:  # prefetch the titled prompts
        list(ex.map(lambda r: client.chat(titled.build(r).messages(), titled.build(r).schema), reqs))
    zero.log, titled.log = [], []
    for req in reqs:
        zero.rank(req)
        titled.rank(req)
    rows = []
    for i, (req, (_, q)) in enumerate(zip(reqs, sample.iterrows())):
        t = truth[str(q["group"])]
        y = items[items["query_id"] == req.query_id].set_index("practice_id")["y"].to_dict()
        ans = id_recs[i].get("parsed")
        rows.append({"query_id": req.query_id, "group": q["group"], "objective_group": q["objective_group"],
                     "sources": q["sources"], "truth_surname": t["surname"], "truth_year": t["year"],
                     "has_title": bool(t["title"]), "has_doi": bool(t["doi"]),
                     "answer_known": bool((ans or {}).get("known")), "answer_surname": (ans or {}).get("first_author_surname"),
                     "answer_year": (ans or {}).get("year"), "answer_journal": (ans or {}).get("journal"),
                     "identified": identified(ans, t), "top1_without": top1(zero.log[i], y), "top1_with": top1(titled.log[i], y)})
    df = pd.DataFrame(rows)
    rate = bootstrap_mean(df["identified"].astype(float).to_numpy())
    df["has_line"] = df["query_id"].map(lambda q: bool(lines.get(q)))
    pairs = df.dropna(subset=["top1_without", "top1_with"])
    both = pairs[pairs["has_line"]]
    lift = bootstrap_mean((both["top1_with"] - both["top1_without"]).to_numpy(float))
    lift_all = bootstrap_mean((pairs["top1_with"] - pairs["top1_without"]).to_numpy(float))
    out = RUNS_DIR / RUN_ID
    out.mkdir(parents=True, exist_ok=True)
    df.to_csv(out / "probes.csv", index=False)
    (out / "responses_titled.jsonl").write_text(log_lines(titled.log), encoding="utf-8")
    summary = {"model": model, "probe_version": PROBE_VERSION, "n": int(len(df)), "n_groups": int(df["group"].nunique()),
               "with_title": int(df["has_title"].sum()), "with_doi": int(df["has_doi"].sum()),
               "identification_rate": rate, "said_known": float(df["answer_known"].mean()),
               "title_lift_top1": lift, "n_lift_pairs": int(len(both)), "with_line": int(df["has_line"].sum()),
               "title_lift_top1_all80": lift_all, "n_lift_pairs_all80": int(len(pairs)),
               "top1_without": float(both["top1_without"].mean()) if len(both) else None,
               "top1_with": float(both["top1_with"].mean()) if len(both) else None,
               "strata": df.groupby(["objective_group", "sources"]).size().rename("n").reset_index().to_dict("records"),
               "client_stats": client.stats, "rule": __doc__.split("Two probes")[0].strip()}
    (out / "summary.json").write_text(json.dumps(summary, indent=1, default=str) + "\n", encoding="utf-8")
    return out


def main(argv: list[str] | None = None) -> int:
    import argparse

    from model.m2.run import Inputs

    ap = argparse.ArgumentParser(description="E7 A5 recall probes (gpt-4.1-mini)")
    ap.add_argument("--budget-usd", type=float, default=20.0)
    ap.add_argument("--ledger-dir", type=Path, default=REPO_ROOT / "model" / "m2" / "cache" / "e7")
    ap.add_argument("--offline", action="store_true")
    a = ap.parse_args(argv)
    print(run(Inputs(), a.budget_usd, a.ledger_dir, offline=a.offline))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
