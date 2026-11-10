"""Rule tests for the taxonomy mappings (brief C4) and the review-preserving merge."""
from __future__ import annotations

import json

import pandas as pd
import pytest

from pipelines.taxonomy import propose_mappings as pm
from pipelines.taxonomy import rules, seed
from pipelines.taxonomy import taxonomy_io as tio


@pytest.mark.parametrize("label, norm", [
    ("No tillage (NT)", "reduced tillage"),
    ("Biochar (100 Mg ha⁻¹)", "biochar"),
    ("Stone terraces", "stone terrace"),
    ("rotation", "crop rotation"),
    ("Crop rotation", "crop rotation"),
    ("Vermicompost 5 t ha⁻¹", "vermicompost"),
])
def test_normalise_label(label, norm):
    assert rules.normalise_label(label) == norm


@pytest.mark.parametrize("label, comps", [
    ("No-tillage + residue retention", ["Reduced Tillage", "Crop Residue Incorporation"]),  # base P9 table wins
    ("Chickpea + Barley (100:100)", []),                      # "ley" must not match "barley"
    ("SMAS-1 (slash-and-mulch agroforestry)", ["Other Agroforestry"]),  # brackets used only as fallback
    ("Zai pit + manure", ["In-situ Water Harvesting", "Organic Fertilizer"]),
    ("Alternate furrow irrigation", ["Alternate Furrow Irrigation"]),
])
def test_label_components(label, comps):
    assert rules.label_components(label) == comps


def test_negated_labels_are_not_rule_mapped():
    assert rules.is_negated("SRI without compost")
    assert rules.is_negated("Conventional tillage (CT)")
    assert not rules.is_negated("No-tillage (NT)")
    assert not rules.is_negated("Non-inversion tillage")


@pytest.mark.parametrize("label, oid", [
    ("Maize grain yield", "YIELD"),
    ("Weed biomass", "WEED_PRESSURE"),
    ("Aboveground biomass", "BIOMASS_YIELD"),
    ("Yield advantage (LER)", "LAND_EQUIVALENT_RATIO"),
    ("Soil organic carbon (SOC)", "SOIL_ORGANIC_CARBON"),
    ("SOC stock (0–100 cm)", "SOIL_CARBON_STOCKS"),
    ("Sediment yield", "SOIL_LOSS"),
    ("Runoff-associated N loss", "NUTRIENT_LEACHING"),
    ("Runoff coefficient", "RUNOFF_COEFFICIENT"),
    ("Net Present Value (NPV)", "NET_PRESENT_VALUE"),
    ("Total energy output", None),
])
def test_outcome_rules(label, oid):
    assert rules.outcome_rule(label)[0] == oid


def test_every_rule_target_has_attributes():
    for _, oid in rules.OUTCOME_RULES:
        d, unit, group = rules.OUTCOME_CANON[oid][1:]
        assert d in (1, -1) and unit in tio.UNIT_CLASSES and group in tio.OBJECTIVE_GROUPS
    for d, unit, group in rules.ERA_OUTCOME_ATTRS.values():
        assert d in (1, -1) and unit in tio.UNIT_CLASSES and group in tio.OBJECTIVE_GROUPS


def _frames():
    era = pd.DataFrame({
        "practice_raw": ["Inorganic Fertilizer", "Mulch", "Cookstove"],
        "_outcome_key": ["Crop Yield", "Soil Moisture", "Cooking Time"],
        "extra": [json.dumps({"T_codes": ["b17"], "Outcode": "101"}), json.dumps({"Outcode": "231"}),
                  json.dumps({"Outcode": "300"})],
    })
    csa = pd.DataFrame({"practice_raw": ["Physical SWC measures", "rotation"],
                        "_outcome_key": ["soil loss", "bulk density"], "extra": [None, None]})
    hab = pd.DataFrame({
        "practice_raw": ["Stone bunds", "No-tillage (NT)", "Organic farming", "SRI without compost"],
        "_outcome_key": ["Maize grain yield", "Soil bulk density", "Total energy output", "Weed biomass"],
        "extra": [json.dumps({"Outcome_type(domain)": "Yield"})] * 4,
    })
    cat = [{"catalogue_id": "CAT_01", "name": "Bench Terrace", "category": "Soil and water conservation",
            "description": "", "key_problems": ["soil erosion"]}]
    return era, csa, hab, cat


def test_seed_and_review_sheet():
    era, csa, hab, cat = _frames()
    s = seed.seed_all(era, csa, hab, cat)
    pa = s.practice_aliases
    assert (pa["accepted"] == "").all() and (pa["reviewer"] == "").all()   # nothing accepted automatically
    look = {(r.source, r.alias): r.practice_id for r in pa.itertuples()}
    assert look[("ERA", "Inorganic Fertilizer")] == "INORGANIC_FERTILIZER"
    assert look[("CSA", "rotation")] == "CROP_ROTATION"                   # normalised synonym
    assert look[("ERA", "Cookstove")] == "COOKSTOVE"                       # ERA label outside the frozen set
    assert look[("CAT", "Bench Terrace")] == "BENCH_TERRACE"
    assert look[("HAB", "Stone bunds")] == "PHYSICAL_SWC_MEASURES"
    assert look[("HAB", "No-tillage (NT)")] == "REDUCED_TILLAGE"
    assert ("HAB", "SRI without compost") not in look
    review = s.reviews["HAB_practices"]
    assert set(review["raw_label"]) == {"Organic farming", "SRI without compost"}
    assert {"candidate_1", "score_1", "candidate_3", "llm_suggestion", "accepted", "practice_id", "reviewer"} <= set(review.columns)
    oa = {(r.source, r.alias): r.outcome_id for r in s.outcome_aliases.itertuples()}
    assert oa[("ERA", "Crop Yield")] == "YIELD" and oa[("CSA", "soil loss")] == "SOIL_LOSS"
    assert oa[("HAB", "Soil bulk density")] == "BULK_DENSITY" and ("HAB", "Total energy output") not in oa
    out = s.outcomes.set_index("outcome_id")
    assert out.loc["YIELD", "status"] == "frozen" and out.loc["SOIL_LOSS", "direction"] == "-1"
    assert out.loc["SOIL_MOISTURE", "status"] == "seed"                    # proposed direction only
    assert s.coverage["practices"]["HAB"] == 0.5 and s.coverage["practices"]["ERA"] == 1.0
    merges = s.merges
    assert ((merges["practice_id_a"] == "BENCH_TERRACE") & (merges["practice_id_b"] == "PHYSICAL_SWC_MEASURES")).any()
    assert ((merges["relation"] == "same_practice")).any()                # Deficit Irrigation ERA/CSA


def test_merge_keeps_human_decisions(tmp_path):
    era, csa, hab, cat = _frames()
    s = seed.seed_all(era, csa, hab, cat)
    pm.write_merged(pm.merge_seeded(s, tmp_path), tmp_path)
    # a reviewer rejects one alias, reviews one outcome and fills the review sheet
    pa = tio.read_csv(tmp_path / "practice_aliases.csv", tio.alias_columns("practice_id"))
    pa.loc[pa["alias"] == "Stone bunds", ["accepted", "reviewer"]] = ["no", "MT"]
    tio.write_csv(pa, tmp_path / "practice_aliases.csv", tio.alias_columns("practice_id"))
    oc = tio.read_csv(tmp_path / "outcomes.csv", tio.OUTCOME_COLUMNS)
    oc.loc[oc["outcome_id"] == "SOIL_MOISTURE", ["status", "notes"]] = ["reviewed", "checked by MT"]
    tio.write_csv(oc, tmp_path / "outcomes.csv", tio.OUTCOME_COLUMNS)
    rv = tio.read_csv(tmp_path / "review" / "HAB_practices_review.csv", tio.review_columns("practice_id"))
    rv.loc[rv["raw_label"] == "Organic farming", ["accepted", "practice_id", "reviewer", "date"]] = \
        ["yes", "INORGANIC_FERTILIZER", "MT", "2026-11-10"]
    tio.write_csv(rv, tmp_path / "review" / "HAB_practices_review.csv", list(rv.columns))
    # re-seeding must not overwrite any of it
    pm.write_merged(pm.merge_seeded(seed.seed_all(era, csa, hab, cat), tmp_path), tmp_path)
    tax = tio.Taxonomy.load(tmp_path)
    assert ("HAB", "Stone bunds") not in tax.practice_lookup()            # rejected alias stays rejected
    assert tax.outcome_directions()["SOIL_MOISTURE"] == 1                  # reviewed direction now usable
    assert tax.outcome_directions()["INFILTRATION_RATE"] is None           # still a proposal
    rv2 = tio.read_csv(tmp_path / "review" / "HAB_practices_review.csv", tio.review_columns("practice_id"))
    assert rv2.set_index("raw_label").loc["Organic farming", "reviewer"] == "MT"
    # --apply-review ingests the ticked row
    assert pm.apply_review(tmp_path) == 1
    tax = tio.Taxonomy.load(tmp_path)
    assert tax.practice_lookup()[("HAB", "Organic farming")] == "INORGANIC_FERTILIZER"
    row = tax.practice_aliases.set_index("alias").loc["Organic farming"]
    assert (row["accepted"], row["method"], row["reviewer"]) == ("yes", "manual", "MT")


def test_llm_answer_is_constrained():
    allowed = {"MULCH", "BIOCHAR"}
    assert pm.parse_llm_answer('{"id": "MULCH", "confidence": 0.9, "reason": "x"}', allowed)["id"] == "MULCH"
    assert pm.parse_llm_answer('{"id": "NEW"}', allowed)["id"] == "NEW"
    assert pm.parse_llm_answer('{"id": "INVENTED"}', allowed) is None
    assert pm.parse_llm_answer("not json", allowed) is None
    msgs = pm.build_llm_messages("Stone bunds", "practice", [("MULCH", "Mulch")])
    assert "NEW" in msgs[1]["content"] and "JSON" in msgs[0]["content"]
