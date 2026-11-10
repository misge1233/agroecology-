#!/usr/bin/env python3
"""Propose taxonomy mappings by rules; write alias files and review sheets (brief C4).

For each source (ERA, CSA, CAT, HAB) and target taxonomy (practices, outcomes):
normalise (case, punctuation, doses and units, plurals, synonyms), exact and
normalised matches, component matches (practices), ERA outcome codes, keyword
rules (outcomes). Rule mappings go to ``practice_aliases.csv`` /
``outcome_aliases.csv`` with ``accepted`` **empty** (nothing is accepted
automatically); unmatched labels go to
``data/taxonomy/review/<source>_<taxonomy>_review.csv`` with their row count,
the top-3 candidates by rapidfuzz token-set ratio and empty
``accepted, <id>, reviewer, date`` columns.

``--llm`` (optional; needs ``OPENAI_API_KEY`` in ``app/backend/.env``): one
constrained call per unmatched label listing the candidate ids and ``NEW``;
JSON output cached in ``review/llm_cache.jsonl``; fills ``llm_suggestion`` only.
Sending labels to the API sends partner text to a third party: the owner decides.

``--apply-review`` ingests reviewed rows (``accepted = yes``, an id and a
reviewer) into the alias files.

Usage::

    python pipelines/taxonomy/propose_mappings.py [--dry-run] [--llm] [--apply-review]
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import sys
from pathlib import Path

import pandas as pd

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pipelines.evidence import common  # noqa: E402
from pipelines.taxonomy import seed as seeding  # noqa: E402
from pipelines.taxonomy import taxonomy_io as tio  # noqa: E402

logger = logging.getLogger(__name__)

REVIEW_SHEETS = {"HAB_practices": "practice_id", "HAB_outcomes": "outcome_id"}
LLM_CONCURRENCY = 6


def review_path(name: str) -> Path:
    """``review/<source>_<taxonomy>_review.csv``."""
    return tio.REVIEW_DIR / f"{name}_review.csv"


def merge_seeded(s: seeding.Seeded, root: Path = tio.TAXONOMY_DIR) -> dict[str, pd.DataFrame]:
    """Merge freshly seeded tables with the files under ``root`` (human edits win)."""
    out = {}
    specs = [
        ("practices", s.practices, root / tio.PRACTICES.name, tio.PRACTICE_COLUMNS, ["practice_id"], tio.protect_taxonomy_row),
        ("outcomes", s.outcomes, root / tio.OUTCOMES.name, tio.OUTCOME_COLUMNS, ["outcome_id"], tio.protect_taxonomy_row),
        ("challenges", s.challenges, root / tio.CHALLENGES.name, tio.CHALLENGE_COLUMNS, ["challenge_id"], tio.protect_taxonomy_row),
        ("practice_aliases", s.practice_aliases, root / tio.PRACTICE_ALIASES.name, tio.alias_columns("practice_id"),
         ["source", "alias"], tio.protect_alias_row),
        ("outcome_aliases", s.outcome_aliases, root / tio.OUTCOME_ALIASES.name, tio.alias_columns("outcome_id"),
         ["source", "alias"], tio.protect_alias_row),
        ("practice_merges", s.merges, root / "review" / tio.PRACTICE_MERGES.name, tio.MERGE_COLUMNS,
         ["practice_id_a", "practice_id_b"], tio.protect_alias_row),
    ]
    for name, new, path, cols, key, protect in specs:
        old = tio.read_csv(path, cols)
        new = new.reindex(columns=cols).astype(object).fillna("").astype(str)
        out[name] = tio.merge_by_key(new, old, key, protect)[cols]
    from pipelines.taxonomy.review_apply import drop_renamed_seed_rows
    from pipelines.taxonomy.seed import ID_RENAMES

    out["outcomes"] = drop_renamed_seed_rows(out["outcomes"], ID_RENAMES)
    for name, sheet in s.reviews.items():
        id_col = REVIEW_SHEETS[name]
        cols = tio.review_columns(id_col)
        old = tio.read_csv(root / "review" / f"{name}_review.csv", cols)
        sheet = sheet.reindex(columns=cols).fillna("").astype(str)
        if not old.empty:
            carried = old.set_index("raw_label")
            for c in ("llm_suggestion", "accepted", id_col, "reviewer", "date"):
                sheet[c] = [carried[c].get(lab, "") if lab in carried.index else v
                            for lab, v in zip(sheet["raw_label"], sheet[c])]
                sheet[c] = sheet[c].where(sheet[c].astype(str) != "", "")
        out[f"review:{name}"] = sheet[cols]
    return out


def write_merged(tables: dict[str, pd.DataFrame], root: Path = tio.TAXONOMY_DIR) -> None:
    """Write merged tables to ``root``."""
    paths = {
        "practices": (root / tio.PRACTICES.name, tio.PRACTICE_COLUMNS),
        "outcomes": (root / tio.OUTCOMES.name, tio.OUTCOME_COLUMNS),
        "challenges": (root / tio.CHALLENGES.name, tio.CHALLENGE_COLUMNS),
        "practice_aliases": (root / tio.PRACTICE_ALIASES.name, tio.alias_columns("practice_id")),
        "outcome_aliases": (root / tio.OUTCOME_ALIASES.name, tio.alias_columns("outcome_id")),
        "practice_merges": (root / "review" / tio.PRACTICE_MERGES.name, tio.MERGE_COLUMNS),
    }
    for name, df in tables.items():
        if name.startswith("review:"):
            sheet = name.split(":", 1)[1]
            tio.write_csv(df, root / "review" / f"{sheet}_review.csv", list(df.columns))
        else:
            path, cols = paths[name]
            tio.write_csv(df, path, cols)
    logger.info("taxonomy written under %s", root)


def taxonomy_from(tables: dict[str, pd.DataFrame]) -> tio.Taxonomy:
    """In-memory :class:`Taxonomy` from merged tables (used by ``--dry-run``)."""
    return tio.Taxonomy(tables["practices"], tables["practice_aliases"], tables["outcomes"],
                        tables["outcome_aliases"], tables["challenges"])


def row_coverage(frames: dict[str, pd.DataFrame], tax: tio.Taxonomy, catalogue: list[dict]) -> dict[str, dict[str, float]]:
    """Share of rows with a mapped practice id / outcome id, per source."""
    pl, ol = tax.practice_lookup(), tax.outcome_lookup()
    cov: dict[str, dict[str, float]] = {"practices": {}, "outcomes": {}}
    for src, df in frames.items():
        cov["practices"][src] = round(float(pd.Series([(src, p) in pl for p in df["practice_raw"]]).mean()), 4)
        cov["outcomes"][src] = round(float(pd.Series([(src, o) in ol for o in df["_outcome_key"]]).mean()), 4)
    if catalogue:
        cov["practices"]["CAT"] = round(sum(("CAT", e["name"]) in pl for e in catalogue) / len(catalogue), 4)
    return cov


# ----------------------------------------------------------------- review in
def apply_review(root: Path = tio.TAXONOMY_DIR) -> int:
    """Ingest accepted Habtamu review rows and practice merges (E2 A2); returns aliases written."""
    from pipelines.taxonomy import review_apply

    res = review_apply.apply_alias_reviews(root)
    merges = review_apply.apply_practice_merges(root)
    print(f"alias reviews: {res.summary()}")
    print(f"practice merges: {merges.summary()}")
    for s_ in res.skipped + merges.skipped:
        print(f"  skipped: {s_}")
    return int(sum(v for k, v in res.applied.items() if k.endswith(":alias")))


# ----------------------------------------------------------------------- LLM
def _cache_key(source: str, taxonomy: str, label: str, candidates: list[str]) -> str:
    h = hashlib.sha256("\x1f".join([source, taxonomy, label] + candidates).encode()).hexdigest()
    return h[:24]


def _read_cache(path: Path = tio.LLM_CACHE) -> dict[str, dict]:
    out = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rec = json.loads(line)
                out[rec["key"]] = rec
    return out


def build_llm_messages(label: str, taxonomy: str, candidates: list[tuple]) -> list[dict]:
    """Constrained prompt: pick one candidate id or NEW, JSON only.

    ``candidates`` are ``(id, name)`` or ``(id, name, components)`` tuples (E2: the
    components are listed so the model can match descriptive labels).
    """
    def line(c: tuple) -> str:
        comps = f" [components: {c[2]}]" if len(c) > 2 and c[2] else ""
        return f"- {c[0]}: {c[1]}{comps}"

    listing = "\n".join(line(c) for c in candidates)
    return [
        {"role": "system", "content": (
            "You map labels from agricultural field-trial papers onto a controlled vocabulary. "
            "Answer with JSON only: {\"id\": <one candidate id or \"NEW\">, \"confidence\": <0..1>, "
            "\"reason\": <one short sentence>}. Choose NEW when no candidate means the same thing. "
            "Never invent an id.")},
        {"role": "user", "content": f"Taxonomy: {taxonomy}\nLabel: {label}\nCandidates:\n{listing}\n- NEW: none of these"},
    ]


def parse_llm_answer(text: str, allowed: set[str]) -> dict | None:
    """Validated ``{"id", "confidence", "reason"}`` or ``None`` (an id outside ``allowed`` is rejected)."""
    try:
        start, end = text.index("{"), text.rindex("}") + 1
        data = json.loads(text[start:end])
    except (ValueError, json.JSONDecodeError):
        return None
    cid = str(data.get("id", "")).strip()
    if cid != "NEW" and cid not in allowed:
        return None
    return {"id": cid, "confidence": data.get("confidence"), "reason": str(data.get("reason", ""))[:300]}


async def _ask_all(jobs: list[tuple[str, list[dict], set[str]]]) -> dict[str, dict | None]:
    common.bootstrap_repo_path()
    backend = str(common.REPO_ROOT / "app" / "backend")
    if backend not in sys.path:
        sys.path.insert(0, backend)
    from app.config import get_settings  # the backend's settings (reads app/backend/.env)
    from app.services.openai_chat import OPENAI_CHAT_COMPLETIONS_URL, OPENAI_CHAT_MODEL, make_client

    settings = get_settings()
    if not settings.openai_api_key:
        raise SystemExit("--llm needs OPENAI_API_KEY in app/backend/.env")
    out: dict[str, dict | None] = {}
    sem = asyncio.Semaphore(LLM_CONCURRENCY)
    async with make_client(settings.openai_api_key, settings.openai_timeout_seconds) as client:
        async def one(key: str, messages: list[dict], allowed: set[str]) -> None:
            async with sem:
                for attempt in range(4):
                    resp = await client.post(OPENAI_CHAT_COMPLETIONS_URL, json={
                        "model": OPENAI_CHAT_MODEL, "messages": messages, "temperature": 0,
                        "response_format": {"type": "json_object"},
                    })
                    if resp.status_code in (429, 500, 502, 503) and attempt < 3:
                        await asyncio.sleep(2 ** attempt)
                        continue
                    resp.raise_for_status()
                    break
                text = resp.json()["choices"][0]["message"]["content"]
                out[key] = parse_llm_answer(text, allowed)

        await asyncio.gather(*(one(k, m, a) for k, m, a in jobs))
    return out


def llm_model() -> str:
    """The fixed chat model used for proposals (the backend's allow-listed model)."""
    common.bootstrap_repo_path()
    backend = str(common.REPO_ROOT / "app" / "backend")
    if backend not in sys.path:
        sys.path.insert(0, backend)
    from app.services.openai_chat import OPENAI_CHAT_MODEL

    return OPENAI_CHAT_MODEL


LLM_AGREEMENT: dict[str, dict[str, float]] = {}


def llm_agreement(sheet: pd.DataFrame) -> dict[str, float]:
    """Sanity figure: share of labels where the LLM picks the rapidfuzz top-1 (and share NEW)."""
    sug = sheet["llm_suggestion"].fillna("")
    answered = sug != ""
    n = int(answered.sum())
    if not n:
        return {"n": 0, "agree_top1": 0.0, "new": 0.0}
    agree = (sug[answered] == sheet.loc[answered, "candidate_1"]).mean()
    return {"n": n, "agree_top1": round(float(agree), 4), "new": round(float((sug[answered] == "NEW").mean()), 4)}


def llm_suggest(tables: dict[str, pd.DataFrame], top_k: int = 10) -> int:
    """Fill ``llm_suggestion`` in the review sheets (cached; one call per uncached label)."""
    from rapidfuzz import fuzz, process

    from pipelines.taxonomy import rules

    cache = _read_cache()
    new_records = []
    n = 0
    for name, id_col in REVIEW_SHEETS.items():
        key = f"review:{name}"
        if key not in tables:
            continue
        tax = tables["practices" if id_col == "practice_id" else "outcomes"]
        tax = tax[~tax["status"].isin(["merged", "excluded"])]
        comps = tax["components"] if "components" in tax.columns else [""] * len(tax)
        names = {rules.normalise_label(nm): (cid, nm, c) for cid, nm, c in zip(tax[id_col], tax["name_en"], comps)}
        sheet = tables[key]
        jobs, keys = [], []
        for label in sheet["raw_label"]:
            top = process.extract(rules.normalise_label(label), list(names), scorer=fuzz.token_set_ratio, limit=top_k)
            cands = [names[t[0]] for t in top]
            ck = _cache_key(name.split("_")[0], id_col, label, [c[0] for c in cands])
            keys.append(ck)
            if ck not in cache:
                jobs.append((ck, build_llm_messages(label, id_col.replace("_id", ""), cands), {c[0] for c in cands}))
        if jobs:
            model = llm_model()
            answers = asyncio.run(_ask_all(jobs))
            for ck, ans in answers.items():
                rec = {"key": ck, "sheet": name, "model": model, "answer": ans}
                cache[ck] = rec
                new_records.append(rec)
        sheet["llm_suggestion"] = [((cache.get(k) or {}).get("answer") or {}).get("id", "") for k in keys]
        n += len(sheet)
        LLM_AGREEMENT[name] = llm_agreement(sheet)
    if new_records:
        tio.LLM_CACHE.parent.mkdir(parents=True, exist_ok=True)
        with open(tio.LLM_CACHE, "a", encoding="utf-8", newline="\n") as fh:
            for rec in new_records:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return n


# ------------------------------------------------------------------------ run
def load_inputs(sources: set[str]) -> tuple[dict[str, pd.DataFrame], list[dict]]:
    """Loader frames for the requested sources plus the parsed catalogue entries."""
    from pipelines.evidence import load_csa, load_era, load_habtamu, parse_catalogue

    frames: dict[str, pd.DataFrame] = {}
    frames["ERA"] = load_era.load()[0]
    frames["CSA"] = load_csa.load()[0]
    if "HAB" in sources and load_habtamu.RAW_PATH.exists():
        frames["HAB"] = load_habtamu.load()[0]
    catalogue: list[dict] = []
    if parse_catalogue.OUT_JSON.exists():
        catalogue = json.loads(parse_catalogue.OUT_JSON.read_text(encoding="utf-8"))
    elif parse_catalogue.RAW_PATH.exists():
        from dataclasses import asdict
        catalogue = [asdict(e) for e in parse_catalogue.parse()]
    return frames, catalogue


def run(frames: dict[str, pd.DataFrame], catalogue: list[dict], write: bool = True,
        llm: bool = False, root: Path = tio.TAXONOMY_DIR) -> tuple[tio.Taxonomy, dict]:
    """Seed, merge with the files on disk, optionally write; return taxonomy and coverage."""
    s = seeding.seed_all(frames["ERA"], frames["CSA"], frames.get("HAB"), catalogue)
    tables = merge_seeded(s, root)
    if llm:
        llm_suggest(tables)
    if write:
        write_merged(tables, root)
    tax = taxonomy_from(tables)
    cov = row_coverage(frames, tax, catalogue)
    return tax, {"rows": cov, "labels": s.coverage,
                 "review_rows": {k.split(":", 1)[1]: int(pd.to_numeric(v["n_rows"]).sum()) for k, v in tables.items()
                                 if k.startswith("review:")},
                 "sizes": {k: int(len(v)) for k, v in tables.items()}}


def print_coverage(cov: dict) -> None:
    """One-screen coverage table."""
    print("Mapping coverage (share of ROWS with a mapped id, by rules):")
    for tax, by_src in cov["rows"].items():
        print(f"  {tax:<10} " + "  ".join(f"{s} {v:.1%}" for s, v in sorted(by_src.items())))
    print("  rows waiting in review sheets: " + ", ".join(f"{k} {v:,}" for k, v in cov["review_rows"].items()))
    print("  table sizes: " + ", ".join(f"{k} {v}" for k, v in cov["sizes"].items()))


def main(argv: list[str] | None = None) -> int:
    """CLI."""
    ap = argparse.ArgumentParser(description="Propose taxonomy mappings by rules (brief C4).")
    ap.add_argument("--sources", default="ERA,CSA,HAB,CAT", help="comma list (ERA and CSA are always loaded)")
    ap.add_argument("--dry-run", action="store_true", help="compute and print coverage, write nothing")
    ap.add_argument("--llm", action="store_true", help="fill llm_suggestion in the review sheets (OpenAI)")
    ap.add_argument("--apply-review", action="store_true", help="ingest accepted review rows into the alias files")
    ap.add_argument("--apply-outcome-review", type=Path, nargs="?", const=None, default=False, metavar="SHEET",
                    help="apply accepted rows of the outcome-direction review sheet "
                         "(default sheet: data/taxonomy/review/outcomes_direction_review.csv)")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    common.setup_logging(args.verbose)
    if args.apply_outcome_review is not False:
        from pipelines.taxonomy import review_apply

        sheet = args.apply_outcome_review or review_apply.OUTCOME_REVIEW
        if args.dry_run:
            print(f"--apply-outcome-review with --dry-run: nothing written ({sheet})")
            return 0
        res = review_apply.apply_outcome_review(Path(sheet))
        print(f"outcome review ({sheet}): {res.summary()}")
        for s_ in res.skipped:
            print(f"  skipped: {s_}")
        return 0
    if args.apply_review:
        if args.dry_run:
            print("--apply-review with --dry-run: nothing written")
            return 0
        n = apply_review()
        print(f"applied {n} reviewed rows")
        return 0
    frames, catalogue = load_inputs(set(args.sources.split(",")))
    _, cov = run(frames, catalogue, write=not args.dry_run, llm=args.llm)
    print_coverage(cov)
    for sheet_name, ag in LLM_AGREEMENT.items():
        print(f"  LLM {sheet_name}: {ag['n']} labels answered; agrees with rapidfuzz top-1 on "
              f"{ag['agree_top1']:.1%}; NEW on {ag['new']:.1%}")
    if args.dry_run:
        print("(dry run: nothing written)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
