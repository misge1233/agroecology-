#!/usr/bin/env python3
"""Propose a PracticeComponent -> WOCAT SLM vocabulary crosswalk (Phase P6a).

Writes ``docs/decisions/wocat_crosswalk_proposal.csv``: one row per
**practice component** (the ~44 atomic components, NOT the 100 frozen
combinations), each with proposed WOCAT SLM groups (QT §3.5) and SLM measure
codes (QT §3.6).

Nothing this script writes reaches the graph on its own. Every row is
emitted with ``status=proposed`` and a blank ``owner_decision``; the owner
validates the file in Excel exactly as for
``docs/decisions/practice_family_mapping.md``, and ``build_graph.py`` admits
only rows whose ``owner_decision``/``status`` reads ``validated``.

Two passes:

* **deterministic** (default) — :data:`KEYWORD_RULES`, a hand-written table
  keyed on substrings of the canonical component label, plus
  :data:`FAMILY_PRIORS` as the fallback for a component no rule matches.
  Reproducible, no network, no key.
Re-running is safe: the script **merges onto an existing csv** by
``component``, keeping the owner's ``owner_decision``, ``owner_note`` and any
hand-edited ``proposed_groups``/``proposed_measures``, refreshing only the
measured columns (``aliases``, ``families``, ``n_rows``), appending new
components and reporting exactly what it preserved. ``--no-merge`` forces a
clean overwrite.

* **``--llm``** (optional, the OWNER runs it) — one ``gpt-4o-mini`` call per
  component at ``temperature=0`` with JSON output and the QT definitions in
  the prompt. Codes the model returns are checked against
  ``wocat_taxonomy``; anything unknown is dropped and logged. The API key is
  resolved by the repo's existing fallback
  (``rag.ingest.build_index.find_api_key``) and is never printed or written.

Usage::

    python rag/graph/crosswalk/propose_crosswalk.py
    python rag/graph/crosswalk/propose_crosswalk.py --llm        # owner only
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .. import practice_components as pc
from .. import wocat_taxonomy as wt
from ..build_graph import DATASET_PATH, load_rows

CROSSWALK_DIR = Path(__file__).resolve().parent
GRAPH_DIR = CROSSWALK_DIR.parent
REPO_ROOT = GRAPH_DIR.parents[1]

logger = logging.getLogger(__name__)

OUTPUT_PATH = REPO_ROOT / "docs" / "decisions" / "wocat_crosswalk_proposal.csv"

COLUMNS = (
    "component", "aliases", "families", "n_rows", "proposed_groups",
    "proposed_measures", "confidence", "rationale", "status",
    "owner_decision", "owner_note",
)

# Shorthands for the QT §3.5 group labels used below.
G_AGROFORESTRY = "agroforestry"
G_AREA_CLOSURE = "area closure (stop use, support restoration)"
G_CROP_LIVESTOCK = "integrated crop-livestock management"
G_CROSS_SLOPE = "cross-slope measure"
G_GROUND_COVER = "improved ground/ vegetation cover"
G_IPM = "integrated pest and disease management (incl. organic agriculture)"
G_IRRIGATION = "irrigation management (incl. water supply, drainage)"
G_ISFM = "integrated soil fertility management"
G_MIN_DISTURBANCE = "minimal soil disturbance"
G_PASTORALISM = "pastoralism and grazing land management"
G_ROTATION = "rotational system (crop rotation, fallows, shifting cultivation)"
G_SURFACE_WATER = "surface water management"
G_VARIETIES = "improved plant varieties/ animal breeds"
G_WATER_HARVESTING = "water harvesting"


@dataclass(frozen=True)
class Rule:
    """One keyword rule.

    Fires when any of ``keywords`` is a substring of the component label and
    none of ``exclude`` is — the exclusions keep a generic rule from
    over-proposing on a more specific component (e.g. the water-harvesting
    rule must not offer S5 dams/ponds for *in-situ* water harvesting).
    """

    keywords: tuple[str, ...]
    groups: tuple[str, ...] = ()
    measures: tuple[str, ...] = ()
    rationale: str = ""
    confidence: float = 0.7
    exclude: tuple[str, ...] = ()

    def matches(self, label: str) -> bool:
        lowered = label.lower()
        if any(keyword in lowered for keyword in self.exclude):
            return False
        return any(keyword in lowered for keyword in self.keywords)


#: Hand-written rules. Several may fire for one component; their groups and
#: measures are unioned and the row's confidence is the highest that fired.
#: Each rationale names the QT clause that justifies the mapping.
KEYWORD_RULES: tuple[Rule, ...] = (
    # --- agroforestry / woody cover ---------------------------------------
    Rule(("agroforestry", "alleycropping", "parkland", "multistrata"),
         (G_AGROFORESTRY,), ("V1",),
         "Woody perennials grown with crops: QT §3.5 agroforestry, "
         "§3.6 V1 tree and shrub cover.", 0.9),
    Rule(("pruning",), (), ("M2",),
         "Pruning changes the management intensity of the tree component "
         "(QT §3.6 M2).", 0.75),
    Rule(("exclosure",), (G_AREA_CLOSURE,), ("M1", "S6"),
         "Land withdrawn from use to restore: QT §3.5 area closure, "
         "§3.6 M1 change in land use type, S6 fences/barriers.", 0.9),
    # --- rotation / fallow ------------------------------------------------
    Rule(("rotation", "fallow"), (G_ROTATION,), ("M2",),
         "Successive or rested cropping: QT §3.5 rotational system, "
         "§3.6 M2 change in management/ intensity level.", 0.85),
    Rule(("crop rotation",), (), ("A2",),
         "QT §3.6 lists crop rotation under A2 organic matter/ soil "
         "fertility.", 0.8),
    Rule(("improved fallow",), (), ("V2",),
         "Improved fallows are sown with herbaceous or woody species "
         "(QT §3.6 V2).", 0.7),
    # --- soil fertility ---------------------------------------------------
    Rule(("fertilizer", "biochar", "isfm", "organic amendments", "ph control",
          "residue incorporation"),
         (G_ISFM,), ("A2",),
         "Soil fertility amendment: QT §3.5 integrated soil fertility "
         "management, §3.6 A2 organic matter/ soil fertility.", 0.9),
    Rule(("fertilizer reduction",), (), ("M2",),
         "Reducing input rates is a change in management intensity "
         "(QT §3.6 M2).", 0.75),
    Rule(("residue",), (), ("A6",),
         "QT §3.6 A6 residue management (sub-option 'retained').", 0.85),
    # --- ground cover / tillage -------------------------------------------
    Rule(("mulch",), (G_GROUND_COVER,), ("A1", "A2"),
         "Dead ground cover: QT §3.5 improved ground/ vegetation cover; "
         "§3.6 lists mulching under both A1 and A2.", 0.9),
    Rule(("intercropping",), (G_GROUND_COVER,), ("A1",),
         "QT §3.6 A1 explicitly names mixed cropping and intercropping.", 0.9),
    Rule(("reduced tillage", "conservation tillage"),
         (G_MIN_DISTURBANCE,), ("A3",),
         "QT §3.5 minimal soil disturbance; §3.6 A3 soil surface treatment, "
         "sub-option 'reduced tillage (> 30% soil cover)'.", 0.9),
    Rule(("conservation tillage",), (G_GROUND_COVER,), ("A6",),
         "Conservation tillage retains residue cover (QT §3.6 A6 "
         "'retained').", 0.75),
    # --- varieties / pests ------------------------------------------------
    Rule(("improved varieties", "tolerant crops"), (G_VARIETIES,), ("A5",),
         "QT §3.5 improved plant varieties/ animal breeds; §3.6 A5 seed "
         "management, improved varieties.", 0.9),
    Rule(("weeding",), (G_IPM,), ("A7",),
         "Weed control is a routine agronomic operation with no dedicated "
         "QT §3.6 code; A7 'others' under QT §3.5 integrated pest and "
         "disease management.", 0.45),
    # --- water: harvesting -------------------------------------------------
    Rule(("water harvesting",), (G_WATER_HARVESTING,), ("S4", "S5", "S7"),
         "QT §3.5 water harvesting; §3.6 S4 level ditches/ pits, S5 dams/ "
         "pans/ ponds, S7 water harvesting equipment.", 0.9,
         exclude=("in-situ",)),
    Rule(("in-situ water harvesting",), (G_WATER_HARVESTING,), ("S4", "A3"),
         "In-situ harvesting retains rain where it falls — micro-catchments "
         "and planting pits (QT §3.6 S4) made by working the soil surface "
         "with tied ridges or contour tillage (A3). No storage structure, so "
         "S5/S7 are deliberately not proposed.", 0.85),
    # --- water: irrigation -------------------------------------------------
    Rule(("irrigation",), (G_IRRIGATION,), ("S7",),
         "QT §3.5 irrigation management; §3.6 S7 water supply/ irrigation "
         "equipment.", 0.9),
    Rule(("deficit irrigation", "alternate furrow"), (), ("M2",),
         "Deficit and alternate-furrow scheduling change the management "
         "intensity of irrigation (QT §3.6 M2).", 0.75),
    Rule(("iwm",), (G_SURFACE_WATER, G_WATER_HARVESTING), ("S3", "S5", "M3"),
         "Integrated watershed management: QT §3.5 surface water "
         "management; §3.6 S3 channels, S5 ponds, M3 layout according to "
         "the natural environment.", 0.6),
    # --- soil and water conservation structures ----------------------------
    Rule(("swc",), (G_CROSS_SLOPE,), (),
         "Soil and water conservation on sloping land: QT §3.5 cross-slope "
         "measure.", 0.6),
    Rule(("physical swc", "physical + biological"), (), ("S1", "S2"),
         "Physical SWC structures are terraces and bunds: QT §3.6 S1, S2.", 0.85),
    Rule(("biological swc",), (G_GROUND_COVER,), ("V2",),
         "Biological SWC uses grass strips and perennial herbaceous cover: "
         "QT §3.6 V2.", 0.85),
    Rule(("agronomic/biological",), (), ("A1",),
         "The agronomic half is vegetation/ soil cover (QT §3.6 A1).", 0.8),
    # --- livestock ----------------------------------------------------------
    Rule(("feed",), (G_CROP_LIVESTOCK,), ("M2",),
         "Feeding strategy: QT §3.5 integrated crop-livestock management; "
         "§3.6 M2 change in management/ intensity level.", 0.8),
    Rule(("grazing management", "pasture management"),
         (G_PASTORALISM,), ("M2",),
         "QT §3.5 pastoralism and grazing land management; §3.6 M2 "
         "(adjusting stocking rates, rotational grazing).", 0.9),
    Rule(("pasture management",), (), ("V2",),
         "Improved pasture is sown grass/ legume cover (QT §3.6 V2).", 0.7),
)

#: Fallback when no keyword rule fires: the component's dominant
#: ``practice_family`` suggests a group and a measure, at low confidence.
FAMILY_PRIORS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "Agro-forestry and forest management": ((G_AGROFORESTRY,), ("V1",)),
    "Crop production and management": ((G_GROUND_COVER,), ("A1",)),
    "Erosion control and water management": ((G_CROSS_SLOPE,), ("S2",)),
    "Integrated soil fertility management": ((G_ISFM,), ("A2",)),
    "Livestock production and management": ((G_CROP_LIVESTOCK,), ("M2",)),
}
FAMILY_PRIOR_CONFIDENCE = 0.35


@dataclass
class Proposal:
    """One crosswalk row before it is written out."""

    component: str
    aliases: list[str] = field(default_factory=list)
    families: list[str] = field(default_factory=list)
    n_rows: int = 0
    groups: set[str] = field(default_factory=set)
    measures: set[str] = field(default_factory=set)
    confidence: float = 0.0
    rationales: list[str] = field(default_factory=list)


# ------------------------------------------------------------ deterministic
def component_facts(rows: list[dict[str, str]]) -> dict[str, Proposal]:
    """Component -> row counts, families and observed alias spellings."""
    practice_rows: Counter[str] = Counter()
    practice_family: dict[str, str] = {}
    for row in rows:
        practice_rows[row["CSA_practices"]] += 1
        practice_family[row["CSA_practices"]] = row["practice_family"]

    raw_tokens: set[str] = set()
    counts: Counter[str] = Counter()
    families: dict[str, Counter[str]] = defaultdict(Counter)
    for practice, n in practice_rows.items():
        raw_tokens.update(pc.split_practice(practice))
        for component in pc.decompose(practice):
            counts[component] += n
            families[component][practice_family[practice]] += n

    clusters = pc.alias_clusters(raw_tokens)
    return {
        component: Proposal(
            component=component,
            aliases=clusters.get(component, [component]),
            families=[family for family, _ in families[component].most_common()],
            n_rows=n,
        )
        for component, n in counts.items()
    }


def apply_rules(proposal: Proposal) -> Proposal:
    """Fire every matching keyword rule; fall back to the family prior."""
    fired = [rule for rule in KEYWORD_RULES if rule.matches(proposal.component)]
    for rule in fired:
        proposal.groups.update(rule.groups)
        proposal.measures.update(rule.measures)
        proposal.rationales.append(rule.rationale)
        proposal.confidence = max(proposal.confidence, rule.confidence)
    if not proposal.measures and not proposal.groups:
        dominant = proposal.families[0] if proposal.families else ""
        groups, measures = FAMILY_PRIORS.get(dominant, ((), ()))
        proposal.groups.update(groups)
        proposal.measures.update(measures)
        proposal.confidence = FAMILY_PRIOR_CONFIDENCE
        proposal.rationales.append(
            f"No keyword rule matched; family prior for {dominant!r}."
        )
    return proposal


def validate_codes(proposal: Proposal) -> list[str]:
    """Drop codes/groups that are not in the questionnaire; return warnings."""
    warnings: list[str] = []
    for code in sorted(proposal.measures):
        if code not in wt.MEASURES_BY_CODE:
            proposal.measures.discard(code)
            warnings.append(f"{proposal.component}: dropped unknown measure {code!r}")
    for group in sorted(proposal.groups):
        if group not in wt.SLM_GROUPS:
            proposal.groups.discard(group)
            warnings.append(f"{proposal.component}: dropped unknown group {group!r}")
    return warnings


# ---------------------------------------------------------------- LLM pass
LLM_MODEL = "gpt-4o-mini"
LLM_URL = "https://api.openai.com/v1/chat/completions"
LLM_SYSTEM = (
    "You map agricultural practice names onto the WOCAT 2019 SLM "
    "questionnaire's controlled vocabularies. Answer ONLY with the codes and "
    "labels given to you. If a practice does not fit, return empty lists. "
    "Never invent a code."
)


def _taxonomy_prompt() -> str:
    """The QT definitions the model is allowed to choose from."""
    measures = "\n".join(
        f"  {m.code}: {m.label}" + (f" (e.g. {m.examples})" if m.examples else "")
        for m in wt.SLM_MEASURES
    )
    groups = "\n".join(f"  - {g}" for g in wt.SLM_GROUPS)
    return (
        f"WOCAT QT 2019 §3.6 SLM measures:\n{measures}\n\n"
        f"WOCAT QT 2019 §3.5 SLM groups:\n{groups}\n"
    )


def llm_refine(proposals: list[Proposal], timeout: int = 60) -> list[str]:
    """Ask gpt-4o-mini to review each proposal. Mutates ``proposals`` in place.

    The key is resolved by the repo's existing fallback and never logged.
    Any code the model returns that is not in the questionnaire is dropped.
    """
    import requests  # local import: the deterministic pass needs no network

    from rag.ingest.build_index import find_api_key  # wrap, never fork

    api_key = find_api_key()
    session = requests.Session()
    taxonomy = _taxonomy_prompt()
    warnings: list[str] = []

    for proposal in proposals:
        user = (
            f"{taxonomy}\n"
            f"Practice component: {proposal.component!r}\n"
            f"Appears in these practice families: {', '.join(proposal.families)}\n"
            f"Rule-based proposal: measures={sorted(proposal.measures)}, "
            f"groups={sorted(proposal.groups)}\n\n"
            "Return JSON with keys 'measures' (list of codes), 'groups' (list "
            "of group labels copied verbatim from the list above), "
            "'confidence' (0-1) and 'rationale' (one sentence)."
        )
        try:
            response = session.post(
                LLM_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": LLM_MODEL,
                    "temperature": 0,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": LLM_SYSTEM},
                        {"role": "user", "content": user},
                    ],
                },
                timeout=timeout,
            )
            response.raise_for_status()
            payload = json.loads(
                response.json()["choices"][0]["message"]["content"]
            )
        except Exception as exc:  # degrade to the deterministic proposal
            warnings.append(f"{proposal.component}: LLM pass failed ({exc})")
            continue

        proposal.measures.update(str(c).strip() for c in payload.get("measures") or [])
        proposal.groups.update(str(g).strip() for g in payload.get("groups") or [])
        warnings.extend(validate_codes(proposal))
        rationale = str(payload.get("rationale") or "").strip()
        if rationale:
            proposal.rationales.append(f"[{LLM_MODEL}] {rationale}")
        try:
            proposal.confidence = max(
                proposal.confidence, min(1.0, float(payload.get("confidence", 0)))
            )
        except (TypeError, ValueError):
            pass
    return warnings


# ------------------------------------------------------------------ output
def to_row(proposal: Proposal) -> dict[str, Any]:
    """Serialize one proposal to the csv row the owner validates."""
    return {
        "component": proposal.component,
        "aliases": "; ".join(proposal.aliases),
        "families": "; ".join(proposal.families),
        "n_rows": proposal.n_rows,
        "proposed_groups": "; ".join(sorted(proposal.groups)),
        "proposed_measures": "; ".join(sorted(proposal.measures)),
        "confidence": round(proposal.confidence, 2),
        "rationale": " ".join(proposal.rationales),
        "status": "proposed",
        "owner_decision": "",
        "owner_note": "",
    }


#: Columns the OWNER owns. A re-run never overwrites a non-empty value in
#: these; the script only ever refreshes the derived columns.
OWNER_COLUMNS: tuple[str, ...] = (
    "proposed_groups", "proposed_measures", "owner_decision", "owner_note",
)
#: Columns recomputed from the data on every run.
DERIVED_COLUMNS: tuple[str, ...] = ("aliases", "families", "n_rows")


def read_existing(path: Path) -> dict[str, dict[str, str]]:
    """Existing csv as ``{component: row}``; empty when there is no file."""
    if not path.exists():
        return {}
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return {
            (row.get("component") or "").strip(): row
            for row in csv.DictReader(fh)
            if (row.get("component") or "").strip()
        }


def merge_row(fresh: dict[str, Any], existing: dict[str, str]) -> tuple[dict[str, Any], list[str]]:
    """Merge a freshly computed row onto the owner's existing one.

    The owner validates this file by hand in Excel, so a re-run must never
    discard that work. A row is treated as **owner-owned** once
    ``owner_decision`` is non-empty:

    * ``owner_decision`` and ``owner_note`` are always kept verbatim;
    * ``proposed_groups`` / ``proposed_measures`` are kept verbatim **only on
      an owner-owned row**. On a row the owner has not decided yet they are
      refreshed from the rules — otherwise a stale rule output would be
      frozen in place forever, since the csv alone cannot tell an owner edit
      apart from a rule change;
    * ``status`` follows the decision (``validated`` / ``rejected``);
    * ``aliases``, ``families``, ``n_rows`` are always refreshed from the
      data — they are measurements, not judgements, and the P6a.1
      practice_family fix is exactly why they must be allowed to move.

    Returns ``(row, preserved_field_names)``.
    """
    row = dict(fresh)
    preserved: list[str] = []
    decision = (existing.get("owner_decision") or "").strip()
    owner_owned = bool(decision)

    for column in OWNER_COLUMNS:
        old_value = (existing.get(column) or "").strip()
        if not old_value:
            continue
        if column in ("proposed_groups", "proposed_measures") and not owner_owned:
            continue
        if old_value == str(row.get(column, "")).strip():
            continue          # identical — nothing to preserve
        row[column] = old_value
        preserved.append(column)

    if decision.lower() in ("validated", "rejected"):
        row["status"] = decision.lower()
        preserved.append("status")
    return row, preserved


def write_csv(proposals: list[Proposal], path: Path,
              merge: bool = True) -> tuple[Path, dict[str, list[str]]]:
    """Write the proposal csv, preserving the owner's edits by default.

    Sorted by component so re-runs are stable. Returns
    ``(path, {component: preserved_fields})``.
    """
    existing = read_existing(path) if merge else {}
    preserved_by_component: dict[str, list[str]] = {}
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        # lineterminator="\n": the csv module defaults to CRLF on every
        # platform, which would rewrite the whole file in git on each run.
        writer = csv.DictWriter(fh, fieldnames=list(COLUMNS), lineterminator="\n")
        writer.writeheader()
        for proposal in sorted(proposals, key=lambda p: p.component):
            row = to_row(proposal)
            prior = existing.get(proposal.component)
            if prior:
                row, preserved = merge_row(row, prior)
                if preserved:
                    preserved_by_component[proposal.component] = preserved
            writer.writerow(row)
    return path, preserved_by_component


def propose(rows: list[dict[str, str]], use_llm: bool = False) -> tuple[list[Proposal], list[str]]:
    """Build every component's proposal. Returns ``(proposals, warnings)``."""
    proposals = [apply_rules(p) for p in component_facts(rows).values()]
    warnings: list[str] = []
    for proposal in proposals:
        warnings.extend(validate_codes(proposal))
    if use_llm:
        warnings.extend(llm_refine(proposals))
    return proposals, warnings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--dataset", type=Path, default=DATASET_PATH)
    parser.add_argument("--out", type=Path, default=OUTPUT_PATH)
    parser.add_argument(
        "--llm", action="store_true",
        help="refine with one gpt-4o-mini call per component (owner runs this)",
    )
    parser.add_argument(
        "--no-merge", dest="merge", action="store_false",
        help="overwrite the csv from scratch, DISCARDING the owner's "
             "decisions and edits (default: merge onto them)",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    existing_before = read_existing(args.out) if args.merge else {}
    proposals, warnings = propose(load_rows(args.dataset), use_llm=args.llm)
    for warning in warnings:
        logger.warning("%s", warning)
    path, preserved = write_csv(proposals, args.out, merge=args.merge)

    fresh = {p.component for p in proposals}
    if existing_before:
        added = sorted(fresh - set(existing_before))
        dropped = sorted(set(existing_before) - fresh)
        logger.info(
            "merged onto %d existing row(s): %d preserved the owner's values, "
            "%d new component(s) appended%s, %d gone from the data%s",
            len(existing_before), len(preserved), len(added),
            f" ({', '.join(added)})" if added else "",
            len(dropped), f" ({', '.join(dropped)})" if dropped else "",
        )
        for component, fields in sorted(preserved.items()):
            logger.info("  preserved %-36s %s", component, ", ".join(fields))
    elif args.merge:
        logger.info("no existing csv at %s — writing a fresh proposal", args.out)
    else:
        logger.warning("--no-merge: any previous owner decisions were DISCARDED")

    no_measure = [p.component for p in proposals if not p.measures]
    logger.info("%d components -> %s", len(proposals), path)
    logger.info(
        "mean confidence %.2f; %d component(s) with no measure proposed%s",
        sum(p.confidence for p in proposals) / len(proposals),
        len(no_measure), f": {no_measure}" if no_measure else "",
    )
    statuses: Counter[str] = Counter()
    with open(path, encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            statuses[(row.get("status") or "proposed").strip()] += 1
    logger.info(
        "row status: %s — only status=validated rows enter the graph",
        ", ".join(f"{n} {status}" for status, n in sorted(statuses.items())),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
