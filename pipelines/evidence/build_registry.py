#!/usr/bin/env python3
"""Build the data-driven registry of challenges and objectives for a country (brief D1).

``python pipelines/evidence/build_registry.py --country ET`` ->
``data/evidence/registry_ET.json``.

Counting rule: only store rows with ``country = <CC>``, a **reviewed**
direction (``direction_reviewed``), a computable ``lrr`` and no ``extra.dup_of``
(an exact repeat of an earlier row) count as evidence. A challenge's objectives
are its ``outcome_ids`` (``challenges.csv``) restricted to its objective groups;
its rows are the counted rows on those objectives whose practice family is one
of the challenge's families.

Exposure (roadmap 5.4, thresholds from ``countries/<CC>.yaml``): an item is
``exposed`` when it has at least ``min_rows`` rows across at least
``min_studies`` studies. Below that it carries ``exposed: false`` and
``documented_only: true`` when the knowledge layer documents at least
``min_docs`` practices for the challenge (in this phase: catalogue entries whose
normalised key problems match ``catalogue_problem_terms``; guidelines arrive in
E2), else ``documented_only: false``.

``n_rows_pending_review`` (informative, never used for exposure) counts the
rows that would count once the outcome's proposed direction is reviewed.

Usage::

    python pipelines/evidence/build_registry.py --country ET [--dry-run]
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import logging
import sys
from pathlib import Path
from typing import Any

import pandas as pd

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pipelines.common.country_config import CountryConfig, load_country  # noqa: E402
from pipelines.evidence import common, parse_catalogue, schema  # noqa: E402
from pipelines.taxonomy import taxonomy_io as tio  # noqa: E402

logger = logging.getLogger(__name__)

REGISTRY_VERSION = "1.0"


def registry_path(code: str, out_dir: Path = common.EVIDENCE_DIR) -> Path:
    """``data/evidence/registry_<CC>.json``."""
    return out_dir / f"registry_{code.upper()}.json"


def _split(v: Any) -> list[str]:
    return [x.strip() for x in str(v or "").split(";") if x.strip()]


def counted_rows(store: pd.DataFrame, code: str) -> pd.DataFrame:
    """Rows that count as evidence for ``code`` (see module docstring)."""
    dup = store["extra"].map(lambda s: bool(json.loads(s).get("dup_of")) if isinstance(s, str) else False)
    keep = (
        (store["country"] == code)
        & store["direction_reviewed"].astype("boolean").fillna(False).astype(bool)
        & store["lrr"].notna() & store["outcome_id"].notna() & ~dup
    )
    return store[keep]


def pending_rows(store: pd.DataFrame, code: str, settled: set[str] | frozenset = frozenset()) -> pd.DataFrame:
    """Rows that would count once their outcome's direction is reviewed (informative only).

    Outcomes already settled without a direction (``excluded``, ``context_dependent``,
    ``merged``) are not pending: their rows never count.
    """
    dup = store["extra"].map(lambda s: bool(json.loads(s).get("dup_of")) if isinstance(s, str) else False)
    keep = (
        (store["country"] == code)
        & ~store["direction_reviewed"].astype("boolean").fillna(False).astype(bool)
        & store["lrr"].notna() & store["outcome_id"].notna() & ~dup
        & ~store["outcome_id"].isin(list(settled))
    )
    return store[keep]


NO_DIRECTION_STATUSES = ("excluded", "context_dependent", "merged")


def registry_diff(old: dict[str, Any], new: dict[str, Any]) -> list[dict[str, Any]]:
    """Per-challenge change of counted and pending rows between two registries."""
    before = {c["id"]: c for c in old.get("challenges", [])}
    out = []
    for c in new.get("challenges", []):
        b = before.get(c["id"], {})
        out.append({"id": c["id"], "rows_before": int(b.get("n_rows", 0)), "rows_after": c["n_rows"],
                    "pending_before": int(b.get("n_rows_pending_review", 0)),
                    "pending_after": c.get("n_rows_pending_review", 0),
                    "exposed_before": bool(b.get("exposed", False)), "exposed_after": c["exposed"]})
    return out


def diff_table(diff: list[dict[str, Any]]) -> str:
    """Markdown table of :func:`registry_diff`."""
    lines = ["| Challenge | Rows before | Rows after | Pending before | Pending after | Exposed |",
             "|---|---:|---:|---:|---:|---|"]
    for d in diff:
        exp = ("yes" if d["exposed_after"] else "no") + ("" if d["exposed_before"] == d["exposed_after"] else " (changed)")
        lines.append(f"| {d['id']} | {d['rows_before']:,} | {d['rows_after']:,} | {d['pending_before']:,} | "
                     f"{d['pending_after']:,} | {exp} |")
    return "\n".join(lines)


def _exposure(n_rows: int, n_studies: int, n_docs: int, cfg: CountryConfig) -> dict[str, Any]:
    t = cfg.exposure
    if n_rows >= t.min_rows and n_studies >= t.min_studies:
        return {"exposed": True, "documented_only": False,
                "exposure_reason": f"rows>={t.min_rows} and studies>={t.min_studies}"}
    if n_docs >= t.min_docs:
        return {"exposed": False, "documented_only": True,
                "exposure_reason": f"below rows>={t.min_rows}/studies>={t.min_studies}; "
                                   f"{n_docs} documented practices >= {t.min_docs}"}
    return {"exposed": False, "documented_only": False,
            "exposure_reason": f"below rows>={t.min_rows}/studies>={t.min_studies} and documented practices<{t.min_docs}"}


def build_registry(store: pd.DataFrame, tax: tio.Taxonomy, catalogue: list[dict], cfg: CountryConfig,
                   manifest_ref: str = "") -> dict[str, Any]:
    """Assemble the registry dict (pure: no file access)."""
    rows = counted_rows(store, cfg.code)
    settled = set(tax.outcomes.loc[tax.outcomes["status"].isin(NO_DIRECTION_STATUSES), "outcome_id"])
    pending = pending_rows(store, cfg.code, settled)
    outcomes = tax.outcomes.set_index("outcome_id")
    directions = tax.outcome_directions()
    use_catalogue = "catalogue" in cfg.knowledge_sources
    cat_problems = {e["catalogue_id"]: set(e.get("key_problems") or []) for e in catalogue} if use_catalogue else {}
    practice_cat = {r.practice_id: _split(r.catalogue_ids) for r in tax.practices.itertuples()}

    challenges_out = []
    practice_challenges: dict[str, set[str]] = {}
    for ch in tax.challenges.itertuples():
        groups = set(_split(ch.objective_groups))
        fams = set(_split(ch.practice_families))
        wanted = _split(ch.outcome_ids) or list(outcomes.index[outcomes["objective_group"].isin(groups)])
        objective_ids = [o for o in wanted if o in outcomes.index and outcomes.loc[o, "objective_group"] in groups]
        ch_rows = rows[rows["outcome_id"].isin(objective_ids) & (rows["practice_family"].isin(fams) if fams else True)]
        ch_pend = pending[pending["outcome_id"].isin(objective_ids)
                          & (pending["practice_family"].isin(fams) if fams else True)]
        terms = set(_split(ch.catalogue_problem_terms))
        docs = sorted(cid for cid, probs in cat_problems.items() if probs & terms)
        n_docs = len(docs)
        objectives = []
        for oid in objective_ids:
            o_rows = ch_rows[ch_rows["outcome_id"] == oid]
            n_r, n_s = int(len(o_rows)), int(o_rows["study_id"].nunique())
            exp = _exposure(n_r, n_s, n_docs, cfg)
            objectives.append({
                "id": oid, "name_en": outcomes.loc[oid, "name_en"], "objective_group": outcomes.loc[oid, "objective_group"],
                "direction": directions.get(oid), "n_rows": n_r, "n_studies": n_s,
                "n_practices": int(o_rows["practice_id"].nunique()), "exposed": exp["exposed"],
                "documented_only": exp["documented_only"],
                "n_rows_pending_review": int((ch_pend["outcome_id"] == oid).sum()),
            })
        n_r, n_s = int(len(ch_rows)), int(ch_rows["study_id"].nunique())
        exp = _exposure(n_r, n_s, n_docs, cfg)
        challenges_out.append({
            "id": ch.challenge_id, "name_en": ch.name_en, "description_en": ch.description_en,
            "objective_groups": sorted(groups), "practice_families": sorted(fams),
            "objectives": objectives, "n_rows": n_r, "n_studies": n_s,
            "n_practices_with_evidence": int(ch_rows["practice_id"].nunique()),
            "n_documented_practices": n_docs, "documented_catalogue_ids": docs, **exp,
            "n_rows_pending_review": int(len(ch_pend)),
        })
        for pid in ch_rows["practice_id"].dropna().unique():
            practice_challenges.setdefault(pid, set()).add(ch.challenge_id)
        for pid, cids in practice_cat.items():
            if set(cids) & set(docs):
                practice_challenges.setdefault(pid, set()).add(ch.challenge_id)

    prac = tax.practices.set_index("practice_id")
    n_by_practice = rows["practice_id"].value_counts()
    practices_out = []
    for pid in sorted(set(n_by_practice.index) | {p for p, c in practice_cat.items() if c and use_catalogue}):
        if pid not in prac.index:
            continue
        practices_out.append({
            "id": pid, "name_en": prac.loc[pid, "name_en"], "family": prac.loc[pid, "practice_family"],
            "challenges": sorted(practice_challenges.get(pid, set())), "n_rows": int(n_by_practice.get(pid, 0)),
            "catalogue_ids": practice_cat.get(pid, []),
        })
    return {
        "country": cfg.code,
        "registry_version": REGISTRY_VERSION,
        "built_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "store_manifest": manifest_ref,
        "thresholds": {"min_rows": cfg.exposure.min_rows, "min_studies": cfg.exposure.min_studies,
                       "min_docs": cfg.exposure.min_docs},
        "counting_rule": "country match, reviewed direction, computable lrr, not an exact duplicate",
        "n_counted_rows": int(len(rows)),
        "challenges": challenges_out,
        "practices": practices_out,
    }


def exposure_table(reg: dict[str, Any]) -> str:
    """Markdown table of challenge exposure (for the report)."""
    lines = ["| Challenge | Rows | Studies | Documented practices | Exposed | Documented only | Rows pending direction review |",
             "|---|---:|---:|---:|---|---|---:|"]
    for c in reg["challenges"]:
        lines.append(f"| {c['id']} | {c['n_rows']:,} | {c['n_studies']} | {c['n_documented_practices']} | "
                     f"{'yes' if c['exposed'] else 'no'} | {'yes' if c['documented_only'] else 'no'} | "
                     f"{c['n_rows_pending_review']:,} |")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """CLI."""
    ap = argparse.ArgumentParser(description="Build the challenge/objective registry for a country.")
    ap.add_argument("--country", required=True)
    ap.add_argument("--dry-run", action="store_true", help="build and print, write nothing")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    common.setup_logging(args.verbose)
    cfg = load_country(args.country, check_files=False)
    store = schema.read_store(common.EVIDENCE_DIR)
    tax = tio.Taxonomy.load()
    catalogue = json.loads(parse_catalogue.OUT_JSON.read_text(encoding="utf-8")) if parse_catalogue.OUT_JSON.exists() else []
    manifest_path = common.EVIDENCE_DIR / schema.STORE_MANIFEST
    ref = manifest_path.relative_to(common.REPO_ROOT).as_posix()
    if manifest_path.exists():
        m = json.loads(manifest_path.read_text(encoding="utf-8"))
        ref = f"{ref} (built {m.get('built_at')}, schema {m.get('schema_version')})"
    reg = build_registry(store, tax, catalogue, cfg, manifest_ref=ref)
    print(f"registry {cfg.code}: {reg['n_counted_rows']:,} counted rows, {len(reg['challenges'])} challenges, "
          f"{len(reg['practices'])} practices")
    print(exposure_table(reg))
    path = registry_path(cfg.code)
    if path.exists():
        diff = registry_diff(json.loads(path.read_text(encoding="utf-8")), reg)
        print("\nChange against the registry on disk:")
        print(diff_table(diff))
        fewer = [d["id"] for d in diff if d["rows_after"] < d["rows_before"]]
        if fewer:
            print(f"NOTE: fewer counted rows for {fewer} (expected only when an exclusion removed them)")
    if not args.dry_run:
        common.write_text(path, json.dumps(reg, indent=2, ensure_ascii=False) + "\n")
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
