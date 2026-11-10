"""Seed the practice, outcome and challenge taxonomies from the sources (brief C1 to C3).

Practices, in order (C1):

1. the 100 frozen ``CSA_practices`` labels -> canonical practices (id from the
   label, family from ``build_practice_family.classify``, components from
   ``rag.graph.practice_components.decompose``). Two labels that differ only by
   case (``Deficit Irrigation`` ERA, ``Deficit irrigation`` CSA) would share an
   id; both get a source suffix and a merge is *proposed*, never applied;
2. ERA ``PrName`` values (and CSA categories) identical to a frozen label map to
   it; the rest become new canonical practices; ERA ``T1..T14`` codes are listed
   per practice (``era_codes``);
3. catalogue names map by normalised match, otherwise become new practices
   (components by keyword match; a narrower catalogue technology sharing its
   component set with a frozen category is *proposed* as a merge);
4. Habtamu ``Intervention_type`` labels map by rules (normalised match, exact
   component set, first-mentioned component); the rest go to the review sheet.

Outcomes (C2): the 7 legacy indicators (direction = ``recommend.DIRECTION``,
status ``frozen``), the 59 ERA outcome names (``Outcode``), the rule targets of
:data:`rules.OUTCOME_CANON`, CSA indicator labels by rules else new seeds, and
Habtamu ``Outcome_name`` by rules (normalised, keyword, biodiversity-domain
fallback), rest to review. Every non-legacy direction is a proposal.

Challenges (C3): the 13 seeded challenges of :data:`CHALLENGES`.
"""
from __future__ import annotations

import datetime as _dt
import json
import logging
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
from rapidfuzz import fuzz, process

from pipelines.dataset.build_practice_family import classify, classify_era
from pipelines.evidence import common
from pipelines.taxonomy import rules
from rag.graph.indicator_map import direction_map
from rag.graph.practice_components import decompose

logger = logging.getLogger(__name__)

FINAL_PATH = common.DATA_DIR / "processed" / "CSA_ERA_final_model_ready.csv"
WOCAT_PROPOSAL = common.REPO_ROOT / "docs" / "decisions" / "wocat_crosswalk_proposal.csv"
TODAY = _dt.date.today().isoformat()

ORIGIN_PRIORITY = {"frozen": 0, "era": 1, "csa": 1, "catalogue": 2}

#: One-time renames of seed ids generated from typo labels (brief E2 A1: a ``seed`` id may
#: be renamed once; the alias row records the old id in ``notes``). Never reused.
ID_RENAMES: dict[str, str] = {"MEAN_TREE_HEIGHT_DIFFERENCXE": "TREE_HEIGHT"}


@dataclass
class Seeded:
    """Output of one seeding run (before merging with the files on disk)."""

    practices: pd.DataFrame
    practice_aliases: pd.DataFrame
    outcomes: pd.DataFrame
    outcome_aliases: pd.DataFrame
    challenges: pd.DataFrame
    merges: pd.DataFrame
    reviews: dict[str, pd.DataFrame] = field(default_factory=dict)
    coverage: dict[str, dict[str, float]] = field(default_factory=dict)


# ----------------------------------------------------------------- helpers
def _alias(alias: str, source: str, id_col: str, oid: str, method: str, conf: float) -> dict:
    return {"alias": alias, "source": source, id_col: oid, "method": method,
            "confidence": f"{conf:.2f}", "accepted": "", "reviewer": "", "date": TODAY}


def _extra_list(frame: pd.DataFrame, key: str) -> pd.Series:
    return frame["extra"].map(lambda s: json.loads(s).get(key) if isinstance(s, str) else None)


def _wocat_by_component(path: Path = WOCAT_PROPOSAL) -> dict[str, tuple[list[str], list[str]]]:
    if not path.exists():
        return {}
    t = pd.read_csv(path, dtype=str, keep_default_na=False)
    out = {}
    for r in t.itertuples():
        groups = [g.strip() for g in r.proposed_groups.split(";") if g.strip()]
        measures = [m.strip() for m in r.proposed_measures.split(";") if m.strip()]
        out[r.component] = (groups, measures)
    return out


def _review_sheet(labels: Counter, choices: dict[str, str], id_col: str, ignore: set[str] = frozenset()) -> pd.DataFrame:
    """Unmatched labels with their row count and top-3 candidates (rapidfuzz token-set ratio)."""
    names = list(choices)
    rows = []
    for label, n in labels.most_common():
        if label in ignore:
            continue
        row = {"raw_label": label, "n_rows": n}
        top = process.extract(rules.normalise_label(label), names, scorer=fuzz.token_set_ratio, limit=3) if names else []
        for i in range(3):
            if i < len(top):
                row[f"candidate_{i + 1}"] = choices[top[i][0]]
                row[f"score_{i + 1}"] = f"{top[i][1]:.0f}"
            else:
                row[f"candidate_{i + 1}"] = ""
                row[f"score_{i + 1}"] = ""
        row.update({"llm_suggestion": "", "accepted": "", id_col: "", "reviewer": "", "date": ""})
        rows.append(row)
    return pd.DataFrame(rows)


def _coverage(labels: Counter, mapped: set[str]) -> float:
    total = sum(labels.values())
    return round(sum(n for lab, n in labels.items() if lab in mapped) / total, 4) if total else 1.0


# --------------------------------------------------------------- practices
def seed_practices(era: pd.DataFrame, csa: pd.DataFrame, hab: pd.DataFrame | None,
                   catalogue: list[dict], final_path: Path = FINAL_PATH) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict, dict]:
    """Return ``(practices, aliases, merges, reviews, coverage)``."""
    final = pd.read_csv(final_path, usecols=["source", "CSA_practices", "practice_family"])
    frozen = final.drop_duplicates(["source", "CSA_practices"])
    frozen_family = final.groupby("CSA_practices")["practice_family"].agg(lambda s: sorted(set(s)))
    wocat = _wocat_by_component()

    era_codes: dict[str, set[str]] = defaultdict(set)
    for label, codes in zip(era["practice_raw"], _extra_list(era, "T_codes")):
        for c in codes or []:
            era_codes[label].add(c)

    practices: dict[str, dict] = {}
    origin: dict[str, str] = {}
    aliases: list[dict] = []
    merges: list[dict] = []

    def add_practice(pid: str, name: str, family: str, comps: tuple[str, ...], org: str, notes: str,
                     codes: set[str] | None = None, cat_ids: list[str] | None = None) -> None:
        groups, measures = [], []
        for c in comps:
            g, m = wocat.get(c, ([], []))
            groups += [x for x in g if x not in groups]
            measures += [x for x in m if x not in measures]
        practices[pid] = {
            "practice_id": pid, "name_en": name, "practice_family": family,
            "components": ";".join(comps), "era_codes": ";".join(sorted(codes or [])),
            "catalogue_ids": ";".join(cat_ids or []), "wocat_group": "; ".join(groups),
            "wocat_measure": "; ".join(measures), "status": "seed", "notes": notes,
        }
        origin[pid] = org

    # (1) frozen labels
    ids = Counter(common.upper_snake(l) for l in frozen["CSA_practices"].unique())
    label_id: dict[str, str] = {}
    for r in frozen.itertuples():
        label, src = r.CSA_practices, r.source
        if label in label_id:
            aliases.append(_alias(label, src, "practice_id", label_id[label], "exact", 1.0))
            continue
        base = common.upper_snake(label)
        pid = f"{base}_{src}" if ids[base] > 1 else base
        fam = classify(src, label)
        if [fam] != frozen_family[label]:
            raise AssertionError(f"family of {label!r}: classify gives {fam}, frozen data {frozen_family[label]}")
        add_practice(pid, label, fam, decompose(label), "frozen",
                     "frozen CSA_practices label (data contract)" + (f"; source-suffixed id ({src})" if pid != base else ""),
                     codes=era_codes.get(label) if src == "ERA" else None)
        label_id[label] = pid
        aliases.append(_alias(label, src, "practice_id", pid, "exact", 1.0))
    for base, n in ids.items():
        if n > 1:
            pair = sorted(p for p in practices if p.startswith(base + "_"))
            merges.append({"practice_id_a": pair[0], "practice_id_b": pair[1], "relation": "same_practice",
                           "reason": "labels differ only by case across sources; same component in the component layer",
                           "accepted": "", "reviewer": "", "date": TODAY})

    norm_index: dict[str, str] = {rules.normalise_label(p["name_en"]): pid for pid, p in practices.items()}

    # (2) ERA PrName and CSA categories not in the frozen set
    for src, frame in (("ERA", era), ("CSA", csa)):
        for label in sorted(set(frame["practice_raw"].dropna()) - set(label_id)):
            n = rules.normalise_label(label)
            if n in norm_index:
                aliases.append(_alias(label, src, "practice_id", norm_index[n], "normalised", 0.95))
                continue
            pid = common.upper_snake(label)
            if pid in practices:
                pid = f"{pid}_{src}"
            fam = classify_era(label)[0]
            add_practice(pid, label, fam, decompose(label), src.lower(),
                         f"{src} label outside the frozen set (rows outside the model's 7-indicator scope)",
                         codes=era_codes.get(label) if src == "ERA" else None)
            norm_index[n] = pid
            label_id[label] = pid
            aliases.append(_alias(label, src, "practice_id", pid, "exact", 1.0))

    # (3) catalogue
    for e in catalogue:
        name = e["name"]
        n = rules.normalise_label(name)
        if n in norm_index:
            pid = norm_index[n]
            practices[pid]["catalogue_ids"] = ";".join(filter(None, [practices[pid]["catalogue_ids"], e["catalogue_id"]]))
            aliases.append(_alias(name, "CAT", "practice_id", pid, "normalised", 0.95))
            continue
        pid = common.upper_snake(rules._PAREN.sub(" ", name))
        if pid in practices:
            pid = f"{pid}_CAT"
        cats = [c.strip().lower() for c in (e.get("category") or "").split(",") if c.strip()]
        fam = next((rules.CATEGORY_FAMILY[c] for c in cats if c in rules.CATEGORY_FAMILY), classify_era(name)[0])
        comps = tuple(rules.label_components(name)) or tuple(rules.label_components(e.get("description") or ""))[:2]
        add_practice(pid, name, fam, comps, "catalogue", f"catalogue entry {e['catalogue_id']} ({e.get('category')})",
                     cat_ids=[e["catalogue_id"]])
        norm_index[n] = pid
        aliases.append(_alias(name, "CAT", "practice_id", pid, "catalogue", 1.0))
        for fid, fp in practices.items():
            if origin.get(fid) == "frozen" and fp["components"] and set(fp["components"].split(";")) == set(comps):
                merges.append({"practice_id_a": pid, "practice_id_b": fid, "relation": "narrower_than",
                               "reason": f"catalogue technology shares the component set {sorted(comps)} with the frozen category",
                               "accepted": "", "reviewer": "", "date": TODAY})

    # index by component set (prefer frozen, then ERA/CSA, then catalogue)
    by_comps: dict[frozenset, str] = {}
    for pid, p in sorted(practices.items(), key=lambda kv: (ORIGIN_PRIORITY.get(origin[kv[0]], 9), kv[0])):
        key = frozenset(filter(None, p["components"].split(";")))
        if key and key not in by_comps:
            by_comps[key] = pid
    single: dict[str, str] = {next(iter(k)): v for k, v in by_comps.items() if len(k) == 1}

    coverage = {
        "ERA": _coverage(Counter(era["practice_raw"]), {a["alias"] for a in aliases if a["source"] == "ERA"}),
        "CSA": _coverage(Counter(csa["practice_raw"]), {a["alias"] for a in aliases if a["source"] == "CSA"}),
        "CAT": _coverage(Counter(e["name"] for e in catalogue), {a["alias"] for a in aliases if a["source"] == "CAT"}),
    }
    reviews: dict[str, pd.DataFrame] = {}

    # (4) Habtamu
    if hab is not None:
        labels = Counter(hab["practice_raw"])
        mapped: set[str] = set()
        for label in labels:
            n = rules.normalise_label(label)
            if n in norm_index:
                aliases.append(_alias(label, "HAB", "practice_id", norm_index[n], "normalised", 0.95))
                mapped.add(label)
                continue
            if rules.is_negated(label):
                continue
            comps = rules.label_components(label)
            if not comps:
                continue
            key = frozenset(comps)
            if key in by_comps:
                aliases.append(_alias(label, "HAB", "practice_id", by_comps[key], "component", 0.85))
                mapped.add(label)
            elif comps[0] in single:
                aliases.append(_alias(label, "HAB", "practice_id", single[comps[0]], "component_primary", 0.6))
                mapped.add(label)
        coverage["HAB"] = _coverage(labels, mapped)
        choices = {rules.normalise_label(p["name_en"]): pid for pid, p in practices.items()}
        reviews["HAB_practices"] = _review_sheet(labels, choices, "practice_id", ignore=mapped)

    cols = ["practice_id", "name_en", "practice_family", "components", "era_codes", "catalogue_ids",
            "wocat_group", "wocat_measure", "status", "notes"]
    return (pd.DataFrame(list(practices.values()))[cols], pd.DataFrame(aliases), pd.DataFrame(merges),
            reviews, coverage)


# ----------------------------------------------------------------- outcomes
def seed_outcomes(era: pd.DataFrame, csa: pd.DataFrame, hab: pd.DataFrame | None) -> tuple[pd.DataFrame, pd.DataFrame, dict, dict]:
    """Return ``(outcomes, aliases, reviews, coverage)``."""
    directions = direction_map()  # recommend.DIRECTION (wrapped by rag.graph.indicator_map)
    outcomes: dict[str, dict] = {}
    aliases: list[dict] = []

    def add(oid: str, name: str, d: int, unit: str, group: str, legacy: str = "", status: str = "seed",
            notes: str = "") -> None:
        if oid in outcomes:
            return
        outcomes[oid] = {"outcome_id": oid, "name_en": name, "direction": str(d), "unit_class": unit,
                         "objective_group": group, "legacy_indicator": legacy, "status": status, "notes": notes}

    for legacy, oid in rules.LEGACY_IDS.items():
        name, _, unit, group = rules.OUTCOME_CANON[oid]
        add(oid, name, directions[legacy], unit, group, legacy=legacy, status="frozen",
            notes="legacy model indicator; direction from recommend.DIRECTION")

    era_names = sorted(set(era["_outcome_key"].dropna()))
    era_codes = {}
    for name, code in zip(era["_outcome_key"], _extra_list(era, "Outcode")):
        era_codes.setdefault(name, code)
    for name in era_names:
        if name in rules.ERA_LEGACY:
            oid = rules.ERA_LEGACY[name]
            o = outcomes[oid]
            o["notes"] += f"; ERA Outcode {era_codes.get(name)} ({name})"
        else:
            oid = common.upper_snake(name)
            d, unit, group = rules.ERA_OUTCOME_ATTRS.get(name, rules.propose_attrs(name))
            note = f"ERA Outcode {era_codes.get(name)}; direction proposed"
            if name in rules.ERA_OUTCOME_NOTES:
                note += f" ({rules.ERA_OUTCOME_NOTES[name]})"
            add(oid, name, d, unit, group, notes=note)
        aliases.append(_alias(name, "ERA", "outcome_id", oid, "era_code", 1.0))

    for oid, (name, d, unit, group) in rules.OUTCOME_CANON.items():
        add(oid, name, d, unit, group, notes="keyword-rule target; direction proposed")

    norm_index = {rules.normalise_label(o["name_en"]): oid for oid, o in outcomes.items()}
    for legacy, oid in rules.LEGACY_IDS.items():
        norm_index[rules.normalise_label(legacy)] = oid

    from pipelines.evidence.reconcile import CSA_SCOPE

    csa_labels = Counter(csa["_outcome_key"])
    for label in csa_labels:
        if label in CSA_SCOPE:
            aliases.append(_alias(label, "CSA", "outcome_id", rules.LEGACY_IDS[CSA_SCOPE[label]], "exact", 1.0))
            continue
        n = rules.normalise_label(label)
        if n in norm_index:
            aliases.append(_alias(label, "CSA", "outcome_id", norm_index[n], "normalised", 0.95))
            continue
        oid, _ = rules.outcome_rule(label)
        if oid:
            aliases.append(_alias(label, "CSA", "outcome_id", oid, "keyword", 0.8))
            continue
        raw_id = common.upper_snake(label)
        new_id = ID_RENAMES.get(raw_id, raw_id)
        d, unit, group = rules.propose_attrs(label)
        note = "CSA indicator label with no rule match; new seed, direction proposed"
        if new_id != raw_id:
            note += f"; renamed from {raw_id} (E2)"
        add(new_id, label, d, unit, group, notes=note)
        norm_index[n] = new_id
        al = _alias(label, "CSA", "outcome_id", new_id, "seed_new", 1.0)
        if new_id != raw_id:
            al["notes"] = f"old id {raw_id}"
        aliases.append(al)

    coverage = {
        "ERA": _coverage(Counter(era["_outcome_key"]), {a["alias"] for a in aliases if a["source"] == "ERA"}),
        "CSA": _coverage(csa_labels, {a["alias"] for a in aliases if a["source"] == "CSA"}),
    }
    reviews: dict[str, pd.DataFrame] = {}
    if hab is not None:
        labels = Counter(hab["_outcome_key"])
        domain = dict(zip(hab["_outcome_key"], _extra_list(hab, "Outcome_type(domain)")))
        mapped: set[str] = set()
        for label in labels:
            n = rules.normalise_label(label)
            if n in norm_index:
                aliases.append(_alias(label, "HAB", "outcome_id", norm_index[n], "normalised", 0.95))
                mapped.add(label)
                continue
            oid, _ = rules.outcome_rule(label)
            if oid:
                aliases.append(_alias(label, "HAB", "outcome_id", oid, "keyword", 0.8))
                mapped.add(label)
                continue
            dom = (domain.get(label) or "").lower()
            if rules.BIODIVERSITY_DOMAINS.search(dom) and rules.BIODIVERSITY_LABEL_HINT.search(label.lower()):
                aliases.append(_alias(label, "HAB", "outcome_id", "BIODIVERSITY", "domain", 0.5))
                mapped.add(label)
        coverage["HAB"] = _coverage(labels, mapped)
        choices = {rules.normalise_label(o["name_en"]): oid for oid, o in outcomes.items()}
        reviews["HAB_outcomes"] = _review_sheet(labels, choices, "outcome_id", ignore=mapped)
    cols = ["outcome_id", "name_en", "direction", "unit_class", "objective_group", "legacy_indicator", "status", "notes"]
    return pd.DataFrame(list(outcomes.values()))[cols], pd.DataFrame(aliases), reviews, coverage


# --------------------------------------------------------------- challenges
CPM, LPM, ISFM, ECWM, FAF = (
    "Crop production and management", "Livestock production and management",
    "Integrated soil fertility management", "Erosion control and water management",
    "Agro-forestry and forest management",
)
#: id -> (name, description, objective groups, families, problem terms, outcome ids)
CHALLENGES: dict[str, tuple[str, str, list[str], list[str], list[str], list[str]]] = {
    "SOIL_EROSION": ("Soil erosion (sheet and rill)", "Topsoil washed off cropland and grazing land by rain and runoff.",
                     ["water", "soil_health"], [ECWM, FAF, CPM], ["soil erosion"], ["SOIL_LOSS", "RUNOFF", "VEGETATION_COVER"]),
    "GULLY_EROSION": ("Gully erosion", "Concentrated runoff cutting gullies that destroy land and spread.",
                      ["water"], [ECWM, FAF], ["gully erosion", "landslide"], ["SOIL_LOSS", "RUNOFF"]),
    "SOIL_FERTILITY_DECLINE": ("Soil fertility decline", "Nutrient and organic matter depletion that lowers soil productivity.",
                               ["soil_health", "productivity"], [ISFM, CPM, FAF, ECWM],
                               ["soil fertility depletion", "soil nutrient depletion"],
                               ["SOM_CONTENT", "SOIL_ORGANIC_CARBON", "SOIL_TOTAL_NITROGEN", "SOIL_AVAILABLE_NITROGEN",
                                "SOIL_NITROGEN", "AVAILABLE_PHOSPHORUS", "CATION_EXCHANGE_CAPACITY", "YIELD"]),
    "MOISTURE_STRESS_DROUGHT": ("Soil moisture stress and drought", "Too little plant-available water during the season.",
                                ["water", "productivity"], [ECWM, CPM], ["soil moisture stress"],
                                ["SOIL_MOISTURE", "WATER_USE_EFFICIENCY", "INFILTRATION_RATE", "YIELD"]),
    "WATERLOGGING_EXCESS_RUNOFF": ("Waterlogging and excess runoff", "Water that runs off or stands on the field instead of infiltrating.",
                                   ["water"], [ECWM], ["excessive runoff"], ["RUNOFF", "INFILTRATION_RATE", "SOIL_LOSS"]),
    "LOW_CROP_PRODUCTIVITY": ("Low crop productivity", "Yields below what the site can support.",
                              ["productivity"], [CPM, ISFM, ECWM, FAF], [],
                              ["YIELD", "BIOMASS_YIELD", "LAND_EQUIVALENT_RATIO", "CROP_RESIDUE_YIELD"]),
    "FEED_SHORTAGE": ("Feed shortage", "Not enough fodder or feed of adequate quality for livestock.",
                      ["livestock", "productivity"], [LPM, FAF, ECWM], ["feed shortage"],
                      ["BIOMASS_YIELD", "WEIGHT_GAIN", "MILK_YIELD", "MEAT_YIELD", "CROP_RESIDUE_YIELD"]),
    "PESTS_AND_DISEASES": ("Pests, diseases and weeds", "Crop losses to insects, pathogens and weeds.",
                           ["productivity", "resilience_biodiversity"], [CPM], [],
                           ["PEST_DAMAGE", "NATURAL_PEST_CONTROL", "WEED_PRESSURE", "WEED_SUPPRESSION"]),
    "DEFORESTATION_FUELWOOD": ("Deforestation and fuelwood shortage", "Loss of tree cover and of wood for fuel and construction.",
                               ["resilience_biodiversity", "other"], [FAF], ["deforestation", "fuelwood shortage"],
                               ["ABOVEGROUND_CARBON_BIOMASS", "BIODIVERSITY", "VEGETATION_COVER"]),
    "DEGRADED_HILLSIDES": ("Land degradation on hillsides", "Steep, bare or overgrazed slopes losing soil, water and vegetation.",
                           ["water", "resilience_biodiversity"], [FAF, ECWM], ["degraded hillsides"],
                           ["SOIL_LOSS", "RUNOFF", "VEGETATION_COVER", "BIODIVERSITY"]),
    "LOW_INCOME_MARKET_ACCESS": ("Low income and market access", "Farm returns too low to cover costs and invest.",
                                 ["economics"], [CPM, LPM, ISFM, ECWM, FAF], [],
                                 ["INCOME", "GROSS_MARGIN", "GROSS_RETURN", "BENEFIT_COST_RATIO", "NET_PRESENT_VALUE",
                                  "PRODUCTION_COST", "RETURN_TO_LABOUR"]),
    "SOIL_ACIDITY": ("Soil acidity", "Acidic soils (low pH) limiting nutrient availability and yield; lime and organic inputs.",
                     ["soil_health"], [ISFM], [], ["SOIL_PH", "SOIL_ACIDITY", "YIELD"]),
    "WATER_SCARCITY_IRRIGATION": ("Water scarcity for crops and irrigation", "Too little water available for crops, livestock or irrigation.",
                                  ["water"], [ECWM], ["water scarcity"], ["WATER_USE_EFFICIENCY", "SOIL_MOISTURE", "WATER_USE"]),
}


def seed_challenges(catalogue: list[dict]) -> pd.DataFrame:
    """Challenge rows; ``catalogue_problem_terms`` keeps the terms that occur in the parsed catalogue."""
    observed = {t for e in catalogue for t in e.get("key_problems", [])}
    rows = []
    for cid, (name, desc, groups, fams, terms, outs) in CHALLENGES.items():
        rows.append({
            "challenge_id": cid, "name_en": name, "description_en": desc,
            "objective_groups": ";".join(groups), "practice_families": ";".join(fams),
            "catalogue_problem_terms": ";".join(t for t in terms if t in observed),
            "outcome_ids": ";".join(outs), "status": "seed",
        })
    return pd.DataFrame(rows)


def seed_all(era: pd.DataFrame, csa: pd.DataFrame, hab: pd.DataFrame | None, catalogue: list[dict]) -> Seeded:
    """Run all seeding rules."""
    p, pa, merges, prev, pcov = seed_practices(era, csa, hab, catalogue)
    o, oa, orev, ocov = seed_outcomes(era, csa, hab)
    ch = seed_challenges(catalogue)
    reviews = {**prev, **orev}
    return Seeded(p, pa, o, oa, ch, merges, reviews,
                  coverage={"practices": pcov, "outcomes": ocov})
