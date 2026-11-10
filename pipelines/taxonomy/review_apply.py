"""Apply human review sheets to the taxonomy files (brief E2, Part A).

Only rows with ``accepted = yes`` are applied; every other row is left exactly
as it is. Reviewer and date come from the sheet. Applied rows become protected:
``status`` other than ``seed`` (taxonomy rows) or a ``reviewer`` (alias rows), so
a later re-run of the rules never overwrites them
(:func:`taxonomy_io.merge_by_key`).

* :func:`apply_outcome_review`: ``review/outcomes_direction_review.csv``
  (``accept``/``flip`` -> direction, group, ``reviewed``; ``exclude`` ->
  ``excluded``; ``context_dependent`` -> ``context_dependent``; ``merge_into`` ->
  aliases moved, ``merged``).
* :func:`apply_alias_reviews`: the Habtamu review sheets (``practice_id`` or
  ``outcome_id`` of an existing id, or ``NEW:<ID>`` to create a canonical
  practice/outcome from the label).
* :func:`apply_practice_merges`: ``review/practice_merges.csv``
  (``same_practice``: aliases moved, merged id ``status = merged``;
  ``narrower_than``: parent recorded in ``notes``, no alias moves).
"""
from __future__ import annotations

import datetime as _dt
import logging
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from pipelines.evidence import common
from pipelines.taxonomy import rules
from pipelines.taxonomy import taxonomy_io as tio

logger = logging.getLogger(__name__)

OUTCOME_REVIEW = tio.REVIEW_DIR / "outcomes_direction_review.csv"
OUTCOME_DECISIONS = ("accept", "flip", "exclude", "context_dependent", "merge_into")
_NEW_RE = re.compile(r"^NEW:([A-Z][A-Z0-9_]*)$")


@dataclass
class ApplyResult:
    """What one applier did (for the report)."""

    applied: Counter = field(default_factory=Counter)
    skipped: list[str] = field(default_factory=list)
    n_rows_in_sheet: int = 0
    n_accepted: int = 0

    def summary(self) -> str:
        """One line."""
        done = ", ".join(f"{k} {v}" for k, v in sorted(self.applied.items())) or "none"
        return (f"{self.n_accepted} of {self.n_rows_in_sheet} rows accepted; applied: {done}; "
                f"skipped {len(self.skipped)}")


def _accepted(sheet: pd.DataFrame) -> pd.DataFrame:
    return sheet[sheet["accepted"].str.strip().str.lower() == "yes"]


def _stamp(row: pd.Series) -> str:
    who = row.get("reviewer", "").strip() or "unnamed reviewer"
    when = row.get("date", "").strip() or _dt.date.today().isoformat()
    return f"{who} {when}"


def _append_note(old: str, note: str) -> str:
    old = (old or "").strip()
    return f"{old}; {note}" if old else note


def _move_aliases(aliases: pd.DataFrame, id_col: str, old: str, new: str, stamp: str, reviewer: str) -> int:
    hit = aliases[id_col] == old
    aliases.loc[hit, id_col] = new
    aliases.loc[hit, "notes"] = [_append_note(n, f"moved from {old} ({stamp})") for n in aliases.loc[hit, "notes"]]
    aliases.loc[hit, "reviewer"] = reviewer or "review sheet"
    return int(hit.sum())


# ------------------------------------------------------------------ outcomes
def apply_outcome_review(sheet_path: Path = OUTCOME_REVIEW, root: Path = tio.TAXONOMY_DIR,
                         renames: dict[str, str] | None = None) -> ApplyResult:
    """Apply accepted rows of the outcome-direction review sheet."""
    from pipelines.taxonomy.seed import ID_RENAMES

    renames = ID_RENAMES if renames is None else renames
    res = ApplyResult()
    sheet = tio.read_csv(sheet_path, ["outcome_id", "proposed_decision", "proposed_direction", "proposed_group",
                                      "merge_into", "note", "accepted", "reviewer", "date"])
    res.n_rows_in_sheet = len(sheet)
    ok = _accepted(sheet)
    res.n_accepted = len(ok)
    if ok.empty:
        logger.info("outcome review: no accepted rows in %s", sheet_path)
        return res
    out_path, al_path = root / tio.OUTCOMES.name, root / tio.OUTCOME_ALIASES.name
    outcomes = tio.read_csv(out_path, tio.OUTCOME_COLUMNS)
    aliases = tio.read_csv(al_path, tio.alias_columns("outcome_id"))
    idx = {oid: i for i, oid in enumerate(outcomes["outcome_id"])}
    for _, r in ok.iterrows():
        oid = renames.get(r["outcome_id"].strip(), r["outcome_id"].strip())
        decision = r["proposed_decision"].strip()
        if oid not in idx or decision not in OUTCOME_DECISIONS:
            res.skipped.append(f"{oid}: unknown id or decision {decision!r}")
            continue
        i, stamp = idx[oid], _stamp(r)
        note = r.get("note", "").strip()
        if decision in ("accept", "flip"):
            d, g = r["proposed_direction"].strip().replace("+", ""), r["proposed_group"].strip()
            if d not in ("1", "-1") or g not in tio.OBJECTIVE_GROUPS:
                res.skipped.append(f"{oid}: bad direction {d!r} or group {g!r}")
                continue
            outcomes.loc[i, ["direction", "objective_group", "status"]] = [d, g, "reviewed"]
            outcomes.loc[i, "notes"] = _append_note(outcomes.loc[i, "notes"], f"{decision} by {stamp}")
        elif decision == "exclude":
            outcomes.loc[i, ["direction", "status"]] = ["", "excluded"]
            outcomes.loc[i, "notes"] = _append_note(outcomes.loc[i, "notes"], f"excluded by {stamp}: {note}")
        elif decision == "context_dependent":
            outcomes.loc[i, ["direction", "status"]] = ["", "context_dependent"]
            if r["proposed_group"].strip() in tio.OBJECTIVE_GROUPS:
                outcomes.loc[i, "objective_group"] = r["proposed_group"].strip()
            outcomes.loc[i, "notes"] = _append_note(outcomes.loc[i, "notes"], f"context dependent ({stamp}): {note}")
        else:  # merge_into
            target = renames.get(r["merge_into"].strip(), r["merge_into"].strip())
            if target not in idx or target == oid:
                res.skipped.append(f"{oid}: merge target {target!r} unknown")
                continue
            n = _move_aliases(aliases, "outcome_id", oid, target, stamp, r.get("reviewer", ""))
            outcomes.loc[i, ["direction", "status"]] = ["", "merged"]
            outcomes.loc[i, "notes"] = _append_note(outcomes.loc[i, "notes"], f"merged into {target} by {stamp} ({n} aliases)")
        res.applied[decision] += 1
    tio.write_csv(outcomes, out_path, tio.OUTCOME_COLUMNS)
    tio.write_csv(aliases, al_path, tio.alias_columns("outcome_id"))
    logger.info("outcome review: %s", res.summary())
    return res


# ------------------------------------------------------------------- aliases
def apply_alias_reviews(root: Path = tio.TAXONOMY_DIR) -> ApplyResult:
    """Ingest accepted rows of the Habtamu review sheets (existing id or ``NEW:<ID>``)."""
    from pipelines.dataset.build_practice_family import classify_era

    res = ApplyResult()
    specs = (("HAB_practices", "practice_id", tio.PRACTICES.name, tio.PRACTICE_COLUMNS, tio.PRACTICE_ALIASES.name),
             ("HAB_outcomes", "outcome_id", tio.OUTCOMES.name, tio.OUTCOME_COLUMNS, tio.OUTCOME_ALIASES.name))
    for name, id_col, tax_file, tax_cols, alias_file in specs:
        path = root / "review" / f"{name}_review.csv"
        sheet = tio.read_csv(path, tio.review_columns(id_col))
        res.n_rows_in_sheet += len(sheet)
        ok = _accepted(sheet)
        ok = ok[(ok[id_col].str.strip() != "") & (ok["reviewer"].str.strip() != "")]
        res.n_accepted += len(ok)
        if ok.empty:
            continue
        tax = tio.read_csv(root / tax_file, tax_cols)
        aliases = tio.read_csv(root / alias_file, tio.alias_columns(id_col))
        known = set(tax[id_col])
        source = name.split("_", 1)[0]
        new_alias, new_tax = [], []
        for _, r in ok.iterrows():
            target = r[id_col].strip()
            m = _NEW_RE.match(target)
            if m:
                target = m.group(1)
                if target not in known:
                    if id_col == "practice_id":
                        comps = rules.label_components(r["raw_label"])
                        new_tax.append({"practice_id": target, "name_en": r["raw_label"],
                                        "practice_family": classify_era(r["raw_label"])[0],
                                        "components": ";".join(comps), "era_codes": "", "catalogue_ids": "",
                                        "wocat_group": "", "wocat_measure": "", "status": "reviewed",
                                        "notes": f"created from HAB review by {_stamp(r)}"})
                    else:
                        d, unit, group = rules.propose_attrs(r["raw_label"])
                        new_tax.append({"outcome_id": target, "name_en": r["raw_label"], "direction": str(d),
                                        "unit_class": unit, "objective_group": group, "legacy_indicator": "",
                                        "status": "seed",
                                        "notes": f"created from HAB review by {_stamp(r)}; direction proposed"})
                    known.add(target)
                    res.applied[f"{name}:new_id"] += 1
            elif target not in known:
                res.skipped.append(f"{name}: {r['raw_label']!r} -> {target} is not a known id")
                continue
            method = "llm" if r.get("llm_suggestion", "").strip() == target else "manual"
            new_alias.append({"alias": r["raw_label"], "source": source, id_col: target, "method": method,
                              "confidence": "1.00", "accepted": "yes", "reviewer": r["reviewer"].strip(),
                              "date": r["date"].strip() or _dt.date.today().isoformat(), "notes": "from review sheet"})
            res.applied[f"{name}:alias"] += 1
        if new_tax:
            tax = pd.concat([tax, pd.DataFrame(new_tax)], ignore_index=True)
            tio.write_csv(tax, root / tax_file, tax_cols)
        if new_alias:
            aliases = tio.merge_by_key(pd.DataFrame(new_alias), aliases, ["source", "alias"], lambda row: False)
            tio.write_csv(aliases, root / alias_file, tio.alias_columns(id_col))
    logger.info("alias reviews: %s", res.summary())
    return res


def apply_practice_merges(root: Path = tio.TAXONOMY_DIR) -> ApplyResult:
    """Apply accepted rows of ``review/practice_merges.csv``."""
    res = ApplyResult()
    sheet = tio.read_csv(root / "review" / tio.PRACTICE_MERGES.name, tio.MERGE_COLUMNS)
    res.n_rows_in_sheet = len(sheet)
    ok = _accepted(sheet)
    res.n_accepted = len(ok)
    if ok.empty:
        return res
    prac = tio.read_csv(root / tio.PRACTICES.name, tio.PRACTICE_COLUMNS)
    aliases = tio.read_csv(root / tio.PRACTICE_ALIASES.name, tio.alias_columns("practice_id"))
    idx = {p: i for i, p in enumerate(prac["practice_id"])}
    for _, r in ok.iterrows():
        a, b, rel = r["practice_id_a"].strip(), r["practice_id_b"].strip(), r["relation"].strip()
        if a not in idx or b not in idx:
            res.skipped.append(f"{a} -> {b}: unknown id")
            continue
        stamp = _stamp(r)
        if rel == "same_practice":
            n = _move_aliases(aliases, "practice_id", a, b, stamp, r.get("reviewer", ""))
            prac.loc[idx[a], "status"] = "merged"
            prac.loc[idx[a], "notes"] = _append_note(prac.loc[idx[a], "notes"], f"merged into {b} by {stamp} ({n} aliases)")
        else:  # narrower_than: a parent link only
            prac.loc[idx[a], "notes"] = _append_note(prac.loc[idx[a], "notes"], f"parent: {b} ({rel}, {stamp})")
            if prac.loc[idx[a], "status"] == "seed":
                prac.loc[idx[a], "status"] = "reviewed"
        res.applied[rel] += 1
    tio.write_csv(prac, root / tio.PRACTICES.name, tio.PRACTICE_COLUMNS)
    tio.write_csv(aliases, root / tio.PRACTICE_ALIASES.name, tio.alias_columns("practice_id"))
    return res


def drop_renamed_seed_rows(outcomes: pd.DataFrame, renames: dict[str, str]) -> pd.DataFrame:
    """Remove ``seed`` rows left behind under an old (renamed) id."""
    stale = outcomes["outcome_id"].isin(list(renames)) & (outcomes["status"] == "seed")
    return outcomes[~stale].reset_index(drop=True)


__all__ = ["apply_outcome_review", "apply_alias_reviews", "apply_practice_merges", "drop_renamed_seed_rows",
           "ApplyResult", "OUTCOME_REVIEW", "common"]
