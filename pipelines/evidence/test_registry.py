"""Registry thresholds (brief D1) on a synthetic store and taxonomy."""
from __future__ import annotations

import json

import pandas as pd

from pipelines.common.country_config import parse_country
from pipelines.evidence import build_registry as br
from pipelines.taxonomy import taxonomy_io as tio

FAM = "Erosion control and water management"


def cfg(min_rows=4, min_studies=2, min_docs=2):
    return parse_country({"code": "TT", "name": "Test", "status": "draft",
                          "bbox": {"lon_min": 0, "lon_max": 1, "lat_min": 0, "lat_max": 1},
                          "knowledge_sources": ["catalogue"],
                          "exposure": {"min_rows": min_rows, "min_studies": min_studies, "min_docs": min_docs}})


def store():
    rows = []
    def add(study, oid, reviewed=True, country="TT", lrr=0.1, dup=None, pid="BUND", fam=FAM):
        rows.append({"study_id": study, "outcome_id": oid, "direction_reviewed": reviewed, "country": country,
                     "lrr": lrr, "practice_id": pid, "practice_family": fam,
                     "extra": json.dumps({"dup_of": dup}) if dup else None})
    for i in range(4):
        add(f"S{i % 2}", "SOIL_LOSS")                         # 4 rows, 2 studies -> exposed
    add("S9", "SOIL_LOSS", dup="TT:S0:1")                     # duplicate: never counted
    add("S8", "SOIL_LOSS", country="XX")                      # other country
    add("S7", "SOIL_LOSS", lrr=None)                          # no effect size
    add("S6", "SOIL_LOSS", pid="VARIETY", fam="Crop production and management")  # family not in challenge
    add("S5", "SOIL_MOISTURE", reviewed=False)                # pending direction review
    add("S4", "YIELD")                                        # 1 row only -> below threshold
    return pd.DataFrame(rows)


def taxonomy():
    outcomes = pd.DataFrame([
        {"outcome_id": "SOIL_LOSS", "name_en": "Soil loss", "direction": "-1", "unit_class": "mass",
         "objective_group": "water", "legacy_indicator": "soil loss", "status": "frozen", "notes": ""},
        {"outcome_id": "SOIL_MOISTURE", "name_en": "Soil moisture", "direction": "1", "unit_class": "fraction",
         "objective_group": "water", "legacy_indicator": "", "status": "seed", "notes": ""},
        {"outcome_id": "YIELD", "name_en": "Crop yield", "direction": "1", "unit_class": "yield",
         "objective_group": "productivity", "legacy_indicator": "yield", "status": "frozen", "notes": ""},
    ])
    challenges = pd.DataFrame([
        {"challenge_id": "SOIL_EROSION", "name_en": "Soil erosion", "description_en": "", "objective_groups": "water",
         "practice_families": FAM, "catalogue_problem_terms": "soil erosion", "outcome_ids": "SOIL_LOSS;SOIL_MOISTURE",
         "status": "seed"},
        {"challenge_id": "GULLY_EROSION", "name_en": "Gully erosion", "description_en": "", "objective_groups": "productivity",
         "practice_families": FAM, "catalogue_problem_terms": "gully erosion", "outcome_ids": "YIELD", "status": "seed"},
        {"challenge_id": "FEED_SHORTAGE", "name_en": "Feed", "description_en": "", "objective_groups": "livestock",
         "practice_families": "", "catalogue_problem_terms": "feed shortage", "outcome_ids": "", "status": "seed"},
    ])
    practices = pd.DataFrame([
        {"practice_id": "BUND", "name_en": "Bund", "practice_family": FAM, "components": "", "era_codes": "",
         "catalogue_ids": "", "wocat_group": "", "wocat_measure": "", "status": "seed", "notes": ""},
        {"practice_id": "CHECK_DAM", "name_en": "Check dam", "practice_family": FAM, "components": "", "era_codes": "",
         "catalogue_ids": "CAT_02", "wocat_group": "", "wocat_measure": "", "status": "seed", "notes": ""},
    ])
    empty = pd.DataFrame(columns=tio.alias_columns("practice_id"))
    return tio.Taxonomy(practices, empty, outcomes, empty, challenges)


CATALOGUE = [{"catalogue_id": "CAT_01", "key_problems": ["soil erosion"]},
             {"catalogue_id": "CAT_02", "key_problems": ["gully erosion"]},
             {"catalogue_id": "CAT_03", "key_problems": ["gully erosion", "feed shortage"]}]


def test_thresholds_and_counting_rule():
    reg = br.build_registry(store(), taxonomy(), CATALOGUE, cfg())
    ch = {c["id"]: c for c in reg["challenges"]}
    ero = ch["SOIL_EROSION"]
    assert (ero["n_rows"], ero["n_studies"], ero["exposed"]) == (4, 2, True)
    assert ero["exposure_reason"] == "rows>=4 and studies>=2"
    obj = {o["id"]: o for o in ero["objectives"]}
    assert obj["SOIL_LOSS"]["direction"] == -1 and obj["SOIL_LOSS"]["exposed"] is True
    assert obj["SOIL_MOISTURE"]["n_rows"] == 0 and obj["SOIL_MOISTURE"]["direction"] is None
    assert obj["SOIL_MOISTURE"]["n_rows_pending_review"] == 1
    gully = ch["GULLY_EROSION"]                               # 1 row < 4 but 2 documented practices >= 2
    assert (gully["n_rows"], gully["exposed"], gully["documented_only"]) == (1, False, True)
    assert gully["documented_catalogue_ids"] == ["CAT_02", "CAT_03"]
    feed = ch["FEED_SHORTAGE"]                                # 0 rows, 1 document < 2
    assert (feed["exposed"], feed["documented_only"]) == (False, False)
    assert reg["thresholds"] == {"min_rows": 4, "min_studies": 2, "min_docs": 2}
    assert reg["n_counted_rows"] == 6                         # 4 + VARIETY row + YIELD row
    prac = {p["id"]: p for p in reg["practices"]}
    assert prac["BUND"]["challenges"] == ["GULLY_EROSION", "SOIL_EROSION"]
    assert prac["CHECK_DAM"]["challenges"] == ["GULLY_EROSION"] and prac["CHECK_DAM"]["n_rows"] == 0


def test_higher_thresholds_hide_items():
    reg = br.build_registry(store(), taxonomy(), CATALOGUE, cfg(min_rows=30, min_studies=5, min_docs=3))
    assert not any(c["exposed"] for c in reg["challenges"])
    assert not any(c["documented_only"] for c in reg["challenges"])
    assert "| SOIL_EROSION | 4 |" in br.exposure_table(reg)
