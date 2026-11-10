"""Read, write and merge the taxonomy CSVs without losing human review.

Files (``data/taxonomy/``, UTF-8, LF, header row; ids upper snake case and
permanent):

* ``practices.csv``, ``practice_aliases.csv``
* ``outcomes.csv``, ``outcome_aliases.csv``
* ``challenges.csv``
* ``review/<source>_<taxonomy>_review.csv``, ``review/practice_merges.csv``

Merge rule (re-running the seeding never overwrites a human decision):

* taxonomy rows (practices, outcomes, challenges) keyed by id: an existing row
  whose ``status`` is ``reviewed`` or ``frozen`` is kept verbatim; a ``seed`` row
  is refreshed from the rules; ids that the rules no longer produce are kept
  (ids are never reused or renamed);
* alias rows keyed by ``(source, alias)``: an existing row with ``accepted`` set
  (``yes``/``no``) or a ``reviewer`` is kept verbatim; otherwise refreshed;
* review sheets keyed by the raw label: reviewer columns already filled are
  carried over.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from pipelines.evidence import common

logger = logging.getLogger(__name__)

TAXONOMY_DIR = common.TAXONOMY_DIR
REVIEW_DIR = common.REVIEW_DIR

PRACTICES = TAXONOMY_DIR / "practices.csv"
PRACTICE_ALIASES = TAXONOMY_DIR / "practice_aliases.csv"
OUTCOMES = TAXONOMY_DIR / "outcomes.csv"
OUTCOME_ALIASES = TAXONOMY_DIR / "outcome_aliases.csv"
CHALLENGES = TAXONOMY_DIR / "challenges.csv"
PRACTICE_MERGES = REVIEW_DIR / "practice_merges.csv"
LLM_CACHE = REVIEW_DIR / "llm_cache.jsonl"

PRACTICE_COLUMNS = ["practice_id", "name_en", "practice_family", "components", "era_codes", "catalogue_ids",
                    "wocat_group", "wocat_measure", "status", "notes"]
OUTCOME_COLUMNS = ["outcome_id", "name_en", "direction", "unit_class", "objective_group", "legacy_indicator",
                   "status", "notes"]
CHALLENGE_COLUMNS = ["challenge_id", "name_en", "description_en", "objective_groups", "practice_families",
                     "catalogue_problem_terms", "outcome_ids", "status"]
ALIAS_COLUMNS = ["alias", "source", "{id}", "method", "confidence", "accepted", "reviewer", "date", "notes"]
MERGE_COLUMNS = ["practice_id_a", "practice_id_b", "relation", "reason", "accepted", "reviewer", "date"]
REVIEW_COLUMNS = ["raw_label", "n_rows", "candidate_1", "score_1", "candidate_2", "score_2", "candidate_3",
                  "score_3", "llm_suggestion", "accepted", "{id}", "reviewer", "date"]

#: E2: ``excluded`` (no direction, never counts), ``context_dependent`` (direction depends on
#: the site; no direction until a context rule exists), ``merged`` (aliases moved to another id).
STATUSES = ("seed", "reviewed", "frozen", "excluded", "context_dependent", "merged")
UNIT_CLASSES = ("yield", "mass", "fraction", "concentration", "money", "count", "rate", "index", "other")
OBJECTIVE_GROUPS = ("productivity", "soil_health", "water", "economics", "resilience_biodiversity", "livestock",
                    "climate", "other")  # "climate" added in E2 (schema v1.1)
ALIAS_SOURCES = ("CSA", "ERA", "HAB", "CAT", "WOCAT")
ALIAS_METHODS = ("exact", "normalised", "component", "component_primary", "era_code", "catalogue", "keyword",
                 "domain", "seed_new", "llm", "manual")
REVIEWED = ("reviewed", "frozen")


def alias_columns(id_col: str) -> list[str]:
    """Alias file columns with the right id column name."""
    return [c.replace("{id}", id_col) for c in ALIAS_COLUMNS]


def review_columns(id_col: str) -> list[str]:
    """Review sheet columns with the right id column name."""
    return [c.replace("{id}", id_col) for c in REVIEW_COLUMNS]


def read_csv(path: Path, columns: list[str]) -> pd.DataFrame:
    """Read a taxonomy CSV as text (empty frame with ``columns`` when absent)."""
    if not path.exists():
        return pd.DataFrame(columns=columns)
    df = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8")
    for c in columns:
        if c not in df.columns:
            df[c] = ""
    return df[columns + [c for c in df.columns if c not in columns]]


def write_csv(df: pd.DataFrame, path: Path, columns: list[str]) -> None:
    """Write a taxonomy CSV (UTF-8, LF), columns in order."""
    path.parent.mkdir(parents=True, exist_ok=True)
    out = df.copy()
    for c in columns:
        if c not in out.columns:
            out[c] = ""
    out = out[columns].fillna("").astype(str)
    out.to_csv(path, index=False, lineterminator="\n", encoding="utf-8")


def merge_by_key(new: pd.DataFrame, old: pd.DataFrame, key: list[str], keep_old) -> pd.DataFrame:
    """Merge refreshed rows into existing ones; ``keep_old(row) -> bool`` protects human edits."""
    if old.empty:
        return new.reset_index(drop=True)
    new = new.copy()
    old = old.copy()
    new["_k"] = new[key].astype(str).agg("\x1f".join, axis=1)
    old["_k"] = old[key].astype(str).agg("\x1f".join, axis=1)
    protected = old[old.apply(keep_old, axis=1)]
    keep_new = new[~new["_k"].isin(protected["_k"])]
    retained_old = old[~old["_k"].isin(new["_k"]) & ~old["_k"].isin(protected["_k"])]
    out = pd.concat([protected, keep_new, retained_old], ignore_index=True)
    order = {k: i for i, k in enumerate(list(new["_k"]) + list(old["_k"]))}
    out = out.assign(_o=out["_k"].map(order)).sort_values("_o", kind="stable")
    return out.drop(columns=["_k", "_o"]).reset_index(drop=True)


def protect_taxonomy_row(row: pd.Series) -> bool:
    """A row with any human decision (status other than ``seed``) is never overwritten."""
    status = str(row.get("status", "")).strip()
    return bool(status) and status != "seed"


def protect_alias_row(row: pd.Series) -> bool:
    """An alias row with a decision or a reviewer is never overwritten."""
    return str(row.get("accepted", "")).strip().lower() in ("yes", "no") or bool(str(row.get("reviewer", "")).strip())


@dataclass
class Taxonomy:
    """In-memory taxonomy used to fill the store."""

    practices: pd.DataFrame
    practice_aliases: pd.DataFrame
    outcomes: pd.DataFrame
    outcome_aliases: pd.DataFrame
    challenges: pd.DataFrame

    @classmethod
    def load(cls, root: Path = TAXONOMY_DIR) -> "Taxonomy":
        """Read the five taxonomy files from ``root``."""
        return cls(
            read_csv(root / PRACTICES.name, PRACTICE_COLUMNS),
            read_csv(root / PRACTICE_ALIASES.name, alias_columns("practice_id")),
            read_csv(root / OUTCOMES.name, OUTCOME_COLUMNS),
            read_csv(root / OUTCOME_ALIASES.name, alias_columns("outcome_id")),
            read_csv(root / CHALLENGES.name, CHALLENGE_COLUMNS),
        )

    def practice_lookup(self) -> dict[tuple[str, str], str]:
        """``(source, alias) -> practice_id`` for usable aliases (not rejected)."""
        return _lookup(self.practice_aliases, "practice_id")

    def outcome_lookup(self) -> dict[tuple[str, str], str]:
        """``(source, alias) -> outcome_id`` for usable aliases (not rejected)."""
        return _lookup(self.outcome_aliases, "outcome_id")

    def outcome_directions(self) -> dict[str, int | None]:
        """``outcome_id -> direction`` when reviewed/frozen, else ``None`` (brief C2)."""
        out: dict[str, int | None] = {}
        for r in self.outcomes.itertuples():
            d = str(r.direction).strip()
            out[r.outcome_id] = int(d) if (r.status in REVIEWED and d in ("1", "-1", "+1")) else None
        return out


def _lookup(aliases: pd.DataFrame, id_col: str) -> dict[tuple[str, str], str]:
    usable = aliases[(aliases["accepted"].str.lower() != "no") & (aliases[id_col].str.strip() != "")]
    return {(r.source, r.alias): getattr(r, id_col) for r in usable.itertuples()}
