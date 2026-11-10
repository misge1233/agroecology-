"""Loader tests on small synthetic fixtures (5 to 10 rows each; no raw data needed)."""
from __future__ import annotations

import json
import math

import pandas as pd
import pytest

from pipelines.evidence import crop_lookup, load_csa, load_era, load_habtamu, schema

CROPS = crop_lookup.CropLookup({
    ("ERA", "Maize"): ("Maize", "Cereal"), ("ERA", "Fava Bean"): ("Faba bean", "Pulse"),
    ("CSA", "maize"): ("Maize", "Cereal"), ("CSA", "Tef"): ("Teff", "Cereal"),
})


# ------------------------------------------------------------------- ERA
def era_fixture(path):
    base = {
        "Unnamed: 0": 0, "Index": 0, "Code": "NJ0001", "Author": "Doe J", "Date": 2015, "Journal": "FIELD CROPS RES",
        "DOI": "10.1016/J.FCR.2015.1", "ISO.3166.1.alpha.3": "ETH", "Latitude": 9.0, "Longitude": 38.5,
        "Site.ID": "Holetta", "PrName": "Inorganic Fertilizer", "C.Descrip": "no fertilizer",
        "Out.SubInd": "Crop Yield", "Partial.Outcome.Name": "Not assessed", "Units": "kg/ha",
        "MeanT": 3000.0, "MeanC": 2000.0, "Rep": 4, "Mean.Error.Type": "SE (Standard Error)",
        "MeanT.Error": 100.0, "MeanC.Error": 80.0, "Product.Simple": "Maize", "Duration": 1.0, "MAP": 1100.0,
        "Elevation": "2400", "Soil.Texture": "Clay", "Soil.pH": 5.5, "AEZ16simple": "cool / subhumid",
        "DataLoc": "Tab 2", "yi": "0.405465108", "MeanFlip": None, "Outcode": 101.0, "Out.Ind": "Product Yield",
        "Out.Pillar": "Productivity", "SubPrName": "Inorg Fert", "Theme": "Soil", "Tree": None,
        "T.Descrip": "NP", "Product": "Maize", "Upper": None, "Lower": None, "Mean.Annual.Precip": "1050",
        "MAT": "16", "AEZ16": "Tropic - cool / subhumid", "Site.Type": "Station",
        **{f"T{i}": None for i in range(1, 15)}, **{f"C{i}": None for i in range(1, 15)},
    }
    rows = [dict(base, Index=i) for i in range(6)]
    rows[0]["T1"] = "b17"
    rows[1].update({"Out.SubInd": "Erosion", "Outcode": 222.0, "MeanT": 5.0, "MeanC": 20.0, "MeanFlip": "N",
                    "Mean.Error.Type": "SD (Standard Deviation)", "MeanT.Error": 1.0, "MeanC.Error": 2.0})
    rows[2].update({"MeanC": 0.0})                                       # lrr null, row kept
    rows[3].update({"Product.Simple": "Sheep", "Duration": 270.0})       # not in lookup; days, not years
    rows[4].update({"Code": "NJ0002", "Partial.Outcome.Name": "Maize Cob", "Mean.Error.Type": None})
    rows[5].update({"Mean.Error.Type": "CV (Co-efficient of Variation)", "MeanT.Error": 9.0})
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


def test_load_era(tmp_path):
    df, log, raw = load_era.load(era_fixture(tmp_path / "era.csv"), crops=CROPS)
    df = schema.coerce(df)  # what reaches the store
    assert len(df) == len(raw) == 6                        # nothing dropped
    assert df["study_id"].tolist()[:2] == ["ERA_NJ0001", "ERA_NJ0001"]
    assert df["row_id"].tolist()[:5] == ["ERA:ERA_NJ0001:1", "ERA:ERA_NJ0001:2", "ERA:ERA_NJ0001:3",
                                         "ERA:ERA_NJ0001:4", "ERA:ERA_NJ0002:1"]
    r0 = df.iloc[0]
    assert r0["doi"] == "10.1016/j.fcr.2015.1" and r0["country"] == "ET" and r0["loc_precision"] == "site"
    assert r0["lrr"] == pytest.approx(math.log(1.5))
    assert r0["sd_with"] == pytest.approx(100.0 * 2) and r0["se_with"] == 100.0   # SE -> SD with sqrt(Rep)
    assert r0["var_lrr"] == pytest.approx((200 ** 2) / (4 * 3000 ** 2) + (160 ** 2) / (4 * 2000 ** 2))
    assert (r0["crop"], r0["crop_group"]) == ("Maize", "Cereal")
    assert json.loads(r0["extra"])["T_codes"] == ["b17"]
    assert df.iloc[1]["lrr"] == pytest.approx(math.log(5 / 20))           # never flipped
    assert json.loads(df.iloc[1]["extra"])["MeanFlip"] == "N"
    assert pd.isna(df.iloc[2]["lrr"])
    assert df.iloc[3]["crop"] == "Sheep" and df.iloc[3]["crop_group"] is None and pd.isna(df.iloc[3]["duration_years"])
    assert df.iloc[4]["outcome_raw"] == "Maize Cob" and df.iloc[4]["_outcome_key"] == "Crop Yield"
    assert pd.isna(df.iloc[5]["sd_with"]) and json.loads(df.iloc[5]["extra"])["MeanT.Error"] == 9.0
    assert log.parsing["meanflip_flag_kept_in_extra_not_applied"] == 1
    assert sum(log.dropped.values()) == 0


# ------------------------------------------------------------------- CSA
def csa_fixture(path):
    base = {"Study_No_": 6, "Reference": "Temesgen, M. (2009) ...", "CSA_practi": "Minimum Tillage",
            "CSA_catago": "Conservation tillage", "duration_o": 1, "Scale": "field experiment", "study_site": "Melkawuha",
            "Latitude": 8.38, "Longitude": 39.37, "Region": "oromia", "Rainfall": 600, "Altitude_r": 1450,
            "Slope____": 12, "Soil_type": "sandy loam", "Crop_type": "maize", "CSA_Pilar": "P", "Indicator": "Yield",
            "With": 1070, "without": 960, "unit": "kg/ha", "Agro_zone": "Dry Kolla"}
    rows = [dict(base) for _ in range(6)]
    rows[1].update({"Crop_type": "Tef", "Indicator": " net income ", "With": 500, "without": 0})
    rows[2] = dict(rows[0])                                               # exact duplicate of row 0
    rows[3].update({"Latitude": 0.0, "Longitude": 0.0, "Rainfall": 0})
    rows[4].update({"Study_No_": 99, "Crop_type": " ", "Indicator": "bulk density"})
    rows[5].update({"Study_No_": 7, "CSA_catago": "rotation"})
    pd.DataFrame(rows).to_excel(path, index=False, sheet_name="Sheet1")
    return path


def test_load_csa(tmp_path):
    refs = {"_compilation": {"citation": "Adimassu et al. 2024."},
            "CSA_6": {"citation": "Temesgen et al. (2009).", "doi": "10.1234/ABC", "year": 2009}}
    df, log, raw = load_csa.load(csa_fixture(tmp_path / "csa.xlsx"), crops=CROPS, refs=refs)
    df = schema.coerce(df)
    assert len(df) == 6
    r0 = df.iloc[0]
    assert r0["study_id"] == "CSA_6" and r0["practice_raw"] == "Conservation tillage"
    assert json.loads(r0["extra"])["CSA_practi"] == "Minimum Tillage"
    assert r0["citation"] == "Temesgen et al. (2009)." and r0["doi"] == "10.1234/abc" and r0["year"] == 2009
    assert (r0["crop"], r0["crop_group"]) == ("Maize", "Cereal")
    assert r0["lrr"] == pytest.approx(math.log(1070 / 960)) and pd.isna(r0["var_lrr"])
    assert df.iloc[1]["_outcome_key"] == "net income" and pd.isna(df.iloc[1]["lrr"])
    assert json.loads(df.iloc[2]["extra"])["dup_of"] == df.iloc[0]["row_id"]
    assert pd.isna(df.iloc[3]["lat"]) and df.iloc[3]["loc_precision"] == "country"
    assert pd.isna(df.iloc[3]["ctx_reported_rain_mm"])
    assert df.iloc[4]["crop"] is None and df.iloc[4]["citation"] == "Adimassu et al. 2024."
    assert df.iloc[0]["ctx_reported_slope_pct"] == 12


# ------------------------------------------------------------------- HAB
HAB_COLUMNS = [
    "Study_ID", "DOI", "Study_design", "Replication_level", "Scale_study", "Quality_score", "Study_period",
    "Country", "Continent", "Precipitation", "Soil", "Slope_topography", "Altitude", "Agroecological_Zone",
    "Climate_Koppen_Class", "Cropping_system", "HLPE_principle", "Intervention_type", "Comparator_description",
    "Intervention_duration", "Outcome_name", "Outcome_type(domain)", "MFL_domain", "Measurement_method", "Unit",
    "Mean_with", "Mean_without", "SD_with", "SD_without", "N_with", "N_without", "SE_with", "SE_without",
    "CI_lower_with", "CI_upper_with", "CI_lower_without", "CI_upper_without", "CV_with", "CV_without",
    "t-value", "F-value", "x2-value", "p-value", "correlation-r", "R²",
    "Extraction Source (Location in PDF)", "Supporting Evidence",
]


def hab_fixture(path):
    base = {c: "NR" for c in HAB_COLUMNS}
    base.update({"Study_ID": "Abebe_2019", "DOI": "https://doi.org/10.1016/J.X.2019.1", "Quality_score": "High",
                 "Study_period": "2015–2017", "Country": "Ethiopia", "Precipitation": "700–900 mm yr⁻¹",
                 "Altitude": "1650 m ASL", "Agroecological_Zone": "Sub-humid Oromia", "Cropping_system": "Rainfed maize",
                 "HLPE_principle": "Recycling; Soil Health", "Intervention_type": "Stone bunds",
                 "Comparator_description": "No bunds", "Intervention_duration": "3 seasons",
                 "Outcome_name": "Maize grain yield", "Outcome_type(domain)": "Yield", "Unit": "t ha⁻¹",
                 "Mean_with": "3.0", "Mean_without": "2.0", "SD_with": "0.3", "SD_without": "0.2",
                 "N_with": "4", "N_without": "4", "Supporting Evidence": "Table 3",
                 "Extraction Source (Location in PDF)": "Page 4"})
    rows = [dict(base) for _ in range(7)]
    rows[1].update({"Study_ID": "Rossi_2005_001", "DOI": "IJPSS.2014.8.004", "Country": "Italy, France",
                    "Quality_score": "Moderate–High", "Precipitation": "~800", "Mean_with": "NR",
                    "Intervention_duration": "One season", "Agroecological_Zone": "Mediterranean"})
    rows[2].update({"Quality_score": "2021", "Mean_with": "1,204", "Mean_without": "1000", "SD_with": "NA",
                    "Intervention_duration": "2–4 years", "Country": "China (Shaanxi, Loess Plateau)"})
    rows[3].update({"Mean_with": "12 ± 3", "Mean_without": "10", "Country": "7 European countries"})
    rows[4].update({"SD_with": "0", "SD_without": "0"})                      # zero variance -> var null
    rows[5].update({"Mean_without": "0"})                                    # lrr null
    rows[6].update({"Study_ID": "Rossi_2005_001", "Intervention_duration": ">15 years"})
    pd.DataFrame(rows, columns=HAB_COLUMNS).to_csv(path, index=False, encoding="utf-8")
    return path


def test_load_habtamu(tmp_path):
    df, log, raw = load_habtamu.load(hab_fixture(tmp_path / "hab.csv"), crops=CROPS)
    df = schema.coerce(df)
    assert len(df) == 7
    r0 = df.iloc[0]
    assert r0["study_id"] == "HAB_Abebe_2019" and r0["year"] == 2019 and r0["doi"] == "10.1016/j.x.2019.1"
    assert r0["country"] == "ET" and pd.isna(r0["lat"]) and r0["loc_method"] == "none"
    assert r0["loc_precision"] == "site"                                     # zone names a place (Oromia)
    assert r0["ctx_reported_rain_mm"] == 800.0                               # range midpoint for context
    assert json.loads(r0["extra"])["Precipitation_range"] == "700-900"
    assert r0["ctx_reported_altitude_m"] == 1650.0
    assert r0["hlpe_principle"] == "Recycling; Soil health"
    assert r0["duration_years"] == pytest.approx(1.5)                        # 3 seasons at 0.5 year
    assert r0["quality_flag"] == "High" and r0["crop"] == "Maize"
    assert r0["lrr"] == pytest.approx(math.log(1.5))
    assert r0["var_lrr"] == pytest.approx(0.09 / (4 * 9) + 0.04 / (4 * 4))
    r1 = df.iloc[1]
    assert r1["doi"] is None and json.loads(r1["extra"])["doi_raw"] == "IJPSS.2014.8.004"
    assert r1["country"] == "IT" and r1["quality_flag"] == "Medium" and r1["loc_precision"] == "country"
    assert pd.isna(r1["mean_with"]) and r1["duration_years"] == 0.5 and r1["year"] == 2005
    r2 = df.iloc[2]
    assert r2["quality_flag"] == "NR" and json.loads(r2["extra"])["Quality_score_raw"] == "2021"
    assert r2["mean_with"] == 1204.0 and r2["duration_years"] == 3.0 and r2["country"] == "CN"
    assert df.iloc[3]["mean_with"] == 12.0 and df.iloc[3]["country"] is None
    assert pd.isna(df.iloc[4]["var_lrr"]) and pd.isna(df.iloc[5]["lrr"])
    assert pd.isna(df.iloc[6]["duration_years"])
    assert log.parsing["var_lrr_null_sd_zero"] == 1
    assert log.parsing["Mean_with:missing"] == 1


def test_habtamu_helpers():
    assert load_habtamu.parse_duration("10 months") == (pytest.approx(10 / 12), "duration_parsed")
    assert load_habtamu.parse_duration("Long-term")[0] is None
    assert load_habtamu.map_country("Ethiopia, Kenya, Uganda") == ("ET", "multi_country_first_kept")
    assert load_habtamu.normalise_principles("Diversity, synergy and efficiency") == "Diversity; Synergy; Efficiency"
    assert load_habtamu.year_from("He_2019", None) == (2019, "year_from_study_id_suffix")
    assert load_habtamu.year_from("Smith", "2013–2016") == (2016, "year_from_study_period_last_year")
