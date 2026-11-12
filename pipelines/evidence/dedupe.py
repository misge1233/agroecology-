"""Cross-source duplicates in the evidence store (E4 Part 0, item 3).

40 DOIs occur in more than one source (ERA, CSA, HAB). When two sources extracted
the same paper, the same with/without contrast can sit in the store twice and would
count twice in every pooled effect. This module finds those rows, keeps the richer
record and flags the other with ``extra.dup_of`` (the key the E1 loaders already use
for exact repeats inside one source), so every downstream reader that skips
``dup_of`` rows (registry, queries, engines) sees each contrast once.

Rule (brief E4 Part 0.3): two rows of **different sources** report the same contrast
when they share the normalised DOI, the canonical ``practice_id`` and ``outcome_id``,
and either their ``lrr`` differ by at most :data:`LRR_TOL` (0.01) or both means are
within :data:`MEAN_REL_TOL` (1 %) of each other. Of such a pair the row with the
**richer record** is kept: more of the dispersion, sample-size, coordinate and
provenance fields filled (:data:`RICHNESS_FIELDS`); ties go to the source order
ERA, HAB, CSA (ERA carries the most complete extraction) and then to ``row_id``.
Rows already flagged ``dup_of`` by a loader are left as they are and never act as
the kept row. Nothing is deleted: the flagged rows stay in the store with their
provenance.

The harness (Part 1) groups queries by DOI, not by the source study id, so a paper
extracted twice is one group there as well.

Usage::

    python pipelines/evidence/dedupe.py [--dry-run] [--store-dir data/evidence]

Writes the store (parquet, CSV mirror, manifest key ``dedupe``) and the card
``data/evidence/cards/dedupe.md`` with the counts per source pair.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    __package__ = "pipelines.evidence"

from pipelines.evidence import common, schema  # noqa: E402

logger = logging.getLogger(__name__)

LRR_TOL = 0.01
MEAN_REL_TOL = 0.01
SOURCE_PRIORITY = {"ERA": 0, "HAB": 1, "CSA": 2, "WOCAT": 3, "other": 4}
RICHNESS_FIELDS = ("var_lrr", "sd_with", "sd_without", "se_with", "se_without", "n_with", "n_without",
                   "lat", "lon", "evidence_text", "extraction_locator", "duration_years", "crop", "comparator")
KEY = ["doi", "practice_id", "outcome_id"]
PAIR_COLUMNS = ["row_id", "dup_of", "source", "source_kept", "doi", "practice_id", "outcome_id", "rule",
                "richness", "richness_kept"]


def dup_of(extra: Any) -> str | None:
    """``extra.dup_of`` of a row, else ``None``."""
    if not isinstance(extra, str) or not extra:
        return None
    try:
        return json.loads(extra).get("dup_of")
    except (TypeError, ValueError):
        return None


def dup_of_series(df: pd.DataFrame) -> pd.Series:
    """``dup_of`` per row (object dtype, ``None`` when absent)."""
    return pd.Series([dup_of(x) for x in df["extra"]], index=df.index, dtype=object)


def richness(row: pd.Series) -> int:
    """How many of :data:`RICHNESS_FIELDS` the row fills."""
    return int(sum(1 for f in RICHNESS_FIELDS if f in row.index and pd.notna(row[f]) and row[f] != ""))


def _close_rel(a: Any, b: Any, tol: float) -> bool:
    if pd.isna(a) or pd.isna(b):
        return False
    scale = max(abs(float(a)), abs(float(b)))
    return abs(float(a) - float(b)) <= tol * scale if scale > 0 else float(a) == float(b)


def same_contrast(a: pd.Series, b: pd.Series) -> str | None:
    """``"lrr"`` or ``"means"`` when the two rows report the same contrast, else ``None``."""
    if pd.notna(a["lrr"]) and pd.notna(b["lrr"]) and abs(float(a["lrr"]) - float(b["lrr"])) <= LRR_TOL:
        return "lrr"
    if _close_rel(a["mean_with"], b["mean_with"], MEAN_REL_TOL) and _close_rel(a["mean_without"], b["mean_without"],
                                                                               MEAN_REL_TOL):
        return "means"
    return None


def find_duplicates(df: pd.DataFrame) -> pd.DataFrame:
    """Cross-source duplicate pairs: one row per flagged row (``row_id``) with its kept row (``dup_of``).

    Deterministic: within a ``(doi, practice_id, outcome_id)`` group the rows are
    ordered by richness (descending), source priority and ``row_id``; each row in
    turn claims every later row of another source that reports the same contrast.
    """
    existing = dup_of_series(df)
    cand = df[df["doi"].notna() & df["practice_id"].notna() & df["outcome_id"].notna() & existing.isna()]
    out: list[dict[str, Any]] = []
    for key, g in cand.groupby(KEY, sort=True):
        if g["source"].nunique() < 2:
            continue
        rows = g.copy()
        rows["_rich"] = [richness(r) for _, r in rows.iterrows()]
        rows["_prio"] = rows["source"].map(lambda s: SOURCE_PRIORITY.get(s, 9))
        rows = rows.sort_values(["_rich", "_prio", "row_id"], ascending=[False, True, True])
        taken: set[str] = set()
        frames = [rows.iloc[i] for i in range(len(rows))]
        for i, keep in enumerate(frames):
            if keep["row_id"] in taken:
                continue
            for j in range(i + 1, len(frames)):
                dup = frames[j]
                if dup["row_id"] in taken or dup["source"] == keep["source"]:
                    continue
                rule = same_contrast(keep, dup)
                if rule:
                    taken.add(dup["row_id"])
                    out.append({"row_id": dup["row_id"], "dup_of": keep["row_id"], "source": dup["source"],
                                "source_kept": keep["source"], "doi": key[0], "practice_id": key[1],
                                "outcome_id": key[2], "rule": rule, "richness": int(dup["_rich"]),
                                "richness_kept": int(keep["_rich"])})
    return pd.DataFrame(out, columns=PAIR_COLUMNS)


def apply_duplicates(df: pd.DataFrame, pairs: pd.DataFrame) -> pd.DataFrame:
    """Write ``extra.dup_of`` for every flagged row (other ``extra`` keys untouched)."""
    out = df.copy()
    if pairs.empty:
        return out
    kept_by_row = dict(zip(pairs["row_id"], pairs["dup_of"]))
    idx = out.index[out["row_id"].isin(kept_by_row)]
    new_extra = []
    for i in idx:
        raw = out.at[i, "extra"]
        d = json.loads(raw) if isinstance(raw, str) and raw else {}
        d["dup_of"] = kept_by_row[out.at[i, "row_id"]]
        d["dup_rule"] = "cross_source"
        new_extra.append(common.json_extra(d))
    out.loc[idx, "extra"] = new_extra
    return out


def summarise(df: pd.DataFrame, pairs: pd.DataFrame) -> dict[str, Any]:
    """Counts for the card and the manifest."""
    by_doi = df.dropna(subset=["doi"]).groupby("doi")["source"].agg(lambda s: tuple(sorted(set(s))))
    multi = by_doi[by_doi.map(len) > 1]
    pair_counts = Counter(f"{r.source_kept}>{r.source}" for r in pairs.itertuples())
    per_source = Counter(pairs["source"]) if not pairs.empty else Counter()
    return {
        "dois_in_more_than_one_source": int(len(multi)),
        "dois_by_source_set": {"+".join(k): int(v) for k, v in Counter(multi).items()},
        "rows_with_multi_source_doi": int(df["doi"].isin(multi.index).sum()),
        "flagged_rows": int(len(pairs)),
        "flagged_by_source": {k: int(v) for k, v in sorted(per_source.items())},
        "flagged_by_pair_kept_over_dropped": {k: int(v) for k, v in sorted(pair_counts.items())},
        "flagged_by_rule": {k: int(v) for k, v in Counter(pairs["rule"]).items()} if not pairs.empty else {},
        "groups_with_duplicates": int(pairs.groupby(KEY).ngroups) if not pairs.empty else 0,
        "lrr_tolerance": LRR_TOL, "mean_relative_tolerance": MEAN_REL_TOL,
        "richness_fields": list(RICHNESS_FIELDS), "source_priority": dict(SOURCE_PRIORITY),
    }


def card_markdown(summary: dict[str, Any], pairs: pd.DataFrame) -> str:
    """``data/evidence/cards/dedupe.md``."""
    L = ["# Cross-source duplicates (E4 Part 0)", "",
         "Rows of different sources that report the same contrast (same DOI, practice id and outcome id; "
         f"`lrr` within {LRR_TOL} or both means within {MEAN_REL_TOL:.0%}). The richer record is kept "
         "(more of " + ", ".join(f"`{f}`" for f in RICHNESS_FIELDS) + " filled; ties by source order ERA, HAB, CSA, "
         "then `row_id`); the other row keeps its provenance and carries `extra.dup_of` and `extra.dup_rule = "
         "cross_source`. Readers that skip `dup_of` rows (registry, harness queries, engines) see each contrast once.",
         "",
         f"- DOIs in more than one source: **{summary['dois_in_more_than_one_source']}** "
         f"({', '.join(f'{k} {v}' for k, v in summary['dois_by_source_set'].items())}); rows under them: "
         f"{summary['rows_with_multi_source_doi']:,}",
         f"- flagged rows: **{summary['flagged_rows']}** in {summary['groups_with_duplicates']} "
         "(DOI, practice, outcome) groups; by rule: "
         + (", ".join(f"{k} {v}" for k, v in summary["flagged_by_rule"].items()) or "none"),
         "", "| kept source > flagged source | rows |", "|---|---:|"]
    for k, v in summary["flagged_by_pair_kept_over_dropped"].items():
        L.append(f"| {k} | {v} |")
    if not summary["flagged_by_pair_kept_over_dropped"]:
        L.append("| (none) | 0 |")
    L += ["", "| flagged source | rows |", "|---|---:|"]
    for k, v in summary["flagged_by_source"].items():
        L.append(f"| {k} | {v} |")
    if not pairs.empty:
        L += ["", "## Flagged rows", "", "| row_id | dup_of | rule | richness (flagged / kept) |", "|---|---|---|---|"]
        for r in pairs.sort_values(["doi", "practice_id", "outcome_id", "row_id"]).itertuples():
            L.append(f"| `{r.row_id}` | `{r.dup_of}` | {r.rule} | {r.richness} / {r.richness_kept} |")
    return "\n".join(L) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Flag cross-source duplicate contrasts in the evidence store")
    ap.add_argument("--store-dir", type=Path, default=common.EVIDENCE_DIR)
    ap.add_argument("--dry-run", action="store_true", help="report only; write nothing")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args(argv)
    common.setup_logging(a.verbose)
    from pipelines.taxonomy import taxonomy_io as tio

    store = schema.read_store(a.store_dir)
    pairs = find_duplicates(store)
    out = apply_duplicates(store, pairs)
    summary = summarise(out, pairs)
    print(json.dumps({k: v for k, v in summary.items() if k not in ("richness_fields", "source_priority")}, indent=1))
    report = schema.validate(out, strict=False, outcome_directions=tio.Taxonomy.load().outcome_directions())
    print("validation:", report.summary())
    if not report.ok:
        logger.error("store does not validate; nothing written")
        return 1
    if a.dry_run:
        return 0
    manifest_path = a.store_dir / schema.STORE_MANIFEST
    old = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    keep = {k: v for k, v in old.items() if k not in ("schema_version", "built_at", "git_commit", "n_rows",
                                                      "rows_per_source", "columns")}
    keep["dedupe"] = {k: v for k, v in summary.items() if k not in ("richness_fields", "source_priority")}
    schema.write_store(out, a.store_dir, extra_manifest=keep)
    card = common.CARDS_DIR / "dedupe.md"
    card.parent.mkdir(parents=True, exist_ok=True)
    card.write_text(card_markdown(summary, pairs), encoding="utf-8")
    print(f"wrote {a.store_dir / schema.STORE_PARQUET} and {card}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
