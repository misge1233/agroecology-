"""Fill the E1/E2 review sheets with the reviewer's decisions (run from the repo root)."""
from __future__ import annotations
import csv, re, sys
from pathlib import Path
import pandas as pd

ROOT = Path(".")
TAX = ROOT / "data/taxonomy"
REV = TAX / "review"
EVREV = ROOT / "data/evidence/review"
REVIEWER, DATE = "Misganu T.", "2026-11-10"

def rd(p):  # keep everything as text
    return pd.read_csv(p, dtype=str, keep_default_na=False)

def wr(df, p):
    df.to_csv(p, index=False, lineterminator="\n", quoting=csv.QUOTE_MINIMAL)

# ---------------------------------------------------------------- practices
P = {}  # index -> (practice_id, note)
def m(idx, pid, note=""):
    for i in (idx if isinstance(idx, (list, tuple, range)) else [idx]):
        P[i] = (pid, note)

m([0, 43, 54, 129, 85, 135], "NEW:ORGANIC_FARMING", "organic system (certified or by restriction)")
m([2, 5, 40, 44], "NEW:AGROECOLOGICAL_FARMING_SYSTEM")
m([4, 17, 62, 79, 6] + list(range(185, 192)), "NEW:REGENERATIVE_AGRICULTURE")
m([1, 37, 70, 65], "NEW:BIODIVERSITY_BASED_PEST_CONTROL", "conservation biological control")
m([11, 18, 34, 36, 64, 82, 84, 166, 167, 169, 201], "NEW:SEMI_NATURAL_HABITAT_CONSERVATION")
m([101, 168, 157, 66, 67], "NEW:LANDSCAPE_DIVERSIFICATION")
m([10, 153, 151, 195], "NEW:FOREST_CONSERVATION")
m(196, "NEW:INVASIVE_SPECIES_CONTROL")
m([8, 27, 149], "NEW:INSECT_POLLINATION_SERVICE", "open pollination versus exclusion")
m(25, "NEW:FARMING_WITH_ALTERNATIVE_POLLINATORS")
m([9, 148], "PHYSICAL_PLUS_BIOLOGICAL_SWC_PRACTICES", "wooden runoff barriers plus vegetation restoration")
m([12, 47], "REDUCED_TILLAGE")
m([120, 130], "NEW:RIDGE_TILLAGE")
m(197, "NEW:SUBSOILING")
m([22, 31, 35, 41, 50, 52, 59, 60, 61, 63, 68, 69, 78, 87, 88, 89, 102, 103, 104, 105, 106, 136, 138, 139,
   158, 159, 160, 161, 162, 164, 165, 170, 171, 172, 173, 174, 175, 176, 177, 178, 179, 209, 210, 211, 212, 23],
  "NEW:COVER_CROPS")
m(33, "NEW:PERMANENT_GROUND_COVER")
m(133, "IMPROVED_FALLOW")
m([13, 121, 122, 123, 124, 125, 192, 193, 116], "INTERCROPPING")
m(15, "CROP_ROTATION", "sunflower and durum wheat sequence")
m(194, "NEW:TRAP_CROPPING")
m([16, 141, 142, 143, 145, 146, 90, 91], "MULTISTRATA_AGROFORESTRY", "shade or homegarden systems")
m(38, "PARKLANDS", "scattered trees on cropland")
m(76, "NEW:LIVE_FENCE")
m([39, 77], "OTHER_AGROFORESTRY", "vegetative corridors")
m(92, "OTHER_AGROFORESTRY", "orchard land use")
m(75, "NEW:PERENNIAL_CROPS")
m(117, "NEW:NATURAL_REGENERATION")
m([21, 42, 45, 93, 94, 206, 207, 208, 26], "NEW:BIOFERTILIZER_INOCULATION")
m([20, 51, 107], "NEW:DUNG_BEETLE_INTRODUCTION")
m([14, 24, 180, 181, 182], "NEW:INTEGRATED_RICE_SYSTEM", "rice with azolla, fish, ducks")
m(19, "NEW:INTEGRATED_CROP_LIVESTOCK_SYSTEM")
m(29, "NEW:AGRI_ENVIRONMENT_SCHEME")
m(28, "NEW:CONSTRUCTED_WETLAND")
m([48, 81, 95, 147], "NEW:SYSTEM_OF_RICE_INTENSIFICATION")
m(112, "PASTURE_MANAGEMENT")
m([113, 114, 115, 86], "NEW:FIELD_MARGINS_AND_HABITAT_STRIPS")
m([118, 119, 183, 184], "ORGANIC_FERTILIZER", "bokashi compost with preparations")
m(126, "BIOCHAR")
m([131, 132, 203, 155, 71], "NEW:CROP_DIVERSIFICATION")
m(134, "IN_SITU_WATER_HARVESTING")
m(137, "NEW:PLANT_SPACING")

NOT = {
    3: "ambiguous: 'no soil management' is the comparator in vineyard trials",
    7: "cooperative governance arrangement, not a land practice",
    30: "landscape descriptor (arable cover share)",
    32: "reversal of no-till, not a practice",
    46: "unexplained code (RTG)",
    49: "unexplained code (AD GM+)",
    53: "experimental factor, not a practice",
    55: "unexplained code (PEL)",
    56: "unexplained code (SMC)",
    57: "HLPE principle names, not a practice",
    58: "intensity level, not a practice",
    72: "paired outcome label, not a practice",
    73: "paired outcome label, not a practice",
    74: "conventional comparator",
    80: "pest community descriptor",
    83: "vineyard age, not a practice",
    96: "blank label",
    97: "richness level used as a treatment", 98: "richness level used as a treatment", 99: "richness level used as a treatment",
    100: "HLPE principle names, not a practice",
    108: "unexplained code (PAS age classes)", 109: "unexplained code (PAS age classes)",
    110: "unexplained code (PAS age classes)", 111: "unexplained code (PAS age classes)",
    127: "outcome used as a treatment", 128: "outcome used as a treatment",
    140: "outcome used as a treatment",
    144: "full-sun conventional comparator",
    150: "richness level used as a treatment", 152: "richness level used as a treatment",
    154: "unexplained code (OWC GM+)",
    156: "service level, not a practice",
    163: "bare soil comparator",
    198: "HLPE principle name", 199: "conventional comparator", 200: "HLPE principle name",
    202: "HLPE principle name", 204: "conventional comparator", 205: "HLPE principle name", 213: "HLPE principle name",
}
# preferred label per NEW id (goes first so it names the practice)
PREF = {"NEW:REGENERATIVE_AGRICULTURE": 185, "NEW:COVER_CROPS": 31, "NEW:ORGANIC_FARMING": 0,
        "NEW:BIODIVERSITY_BASED_PEST_CONTROL": 1, "NEW:INSECT_POLLINATION_SERVICE": 27,
        "NEW:INTEGRATED_RICE_SYSTEM": 24, "NEW:BIOFERTILIZER_INOCULATION": 45, "NEW:SEMI_NATURAL_HABITAT_CONSERVATION": 11,
        "NEW:FIELD_MARGINS_AND_HABITAT_STRIPS": 113, "NEW:CROP_DIVERSIFICATION": 131,
        "NEW:SYSTEM_OF_RICE_INTENSIFICATION": 48, "NEW:RIDGE_TILLAGE": 120, "NEW:DUNG_BEETLE_INTRODUCTION": 20}

pr = rd(REV / "HAB_practices_review.csv")
assert len(pr) == 214, len(pr)
if "reviewer_note" not in pr.columns:
    pr["reviewer_note"] = ""
mapped = 0
for i in range(len(pr)):
    if i in P:
        pid, note = P[i]
        pr.loc[i, "practice_id"] = pid; pr.loc[i, "accepted"] = "yes"
        pr.loc[i, "reviewer"] = REVIEWER; pr.loc[i, "date"] = DATE; pr.loc[i, "reviewer_note"] = note
        mapped += 1
    elif i in NOT:
        pr.loc[i, "accepted"] = "no"; pr.loc[i, "reviewer"] = REVIEWER; pr.loc[i, "date"] = DATE
        pr.loc[i, "reviewer_note"] = NOT[i]
    else:
        raise SystemExit(f"practice row {i} ({pr.loc[i,'raw_label']}) has no decision")
# order: preferred label first within each NEW id, otherwise keep the sheet order
pr["_k"] = [0 if (i in P and PREF.get(P[i][0]) == i) else 1 for i in range(len(pr))]
pr["_i"] = range(len(pr))
pr = pr.sort_values(["_k", "_i"]).drop(columns=["_k", "_i"]).reset_index(drop=True)
wr(pr, REV / "HAB_practices_review.csv")
print("practices: mapped", mapped, "not a practice", len(NOT), "rows covered", pr[pr.accepted=='yes'].n_rows.astype(int).sum(), "of", pr.n_rows.astype(int).sum())

# ---------------------------------------------------------------- outcomes
O = {}
def o(idx, oid, note=""):
    for i in (idx if isinstance(idx, (list, tuple, range)) else [idx]):
        O[i] = (oid, note)
o([0, 72, 133], "NEW:ENERGY_BALANCE")
o(1, "CRUDE_PROTEIN"); o([3, 4, 5, 6, 25, 34, 65, 66, 77, 122, 67], "NEW:PRODUCE_QUALITY")
o(2, "NEW:FINANCIAL_RESILIENCE")
o([7, 163, 164, 165], "YIELD")
o([18, 86, 87, 88, 89, 106, 107, 112, 113, 114, 127, 186, 194, 195, 196, 197], "NEW:YIELD_COMPONENTS")
o([8, 26, 135, 137, 180, 128, 169], "NEW:PLANT_GROWTH")
o(58, "TREE_HEIGHT", "tree growth increment")
o(166, "LAI")
o(9, "N_CONTENT_SHOOT"); o([62, 64], "NEW:NUTRIENT_UPTAKE"); o(63, "P_UPTAKE")
o([16, 21, 33, 118], "SOIL_AVAILABLE_NITROGEN")
o([54, 101, 102, 103, 145, 191, 193, 38, 39, 55], "SOIL_TOTAL_NITROGEN")
o(22, "SOIL_POTASSIUM"); o([199, 210], "AVAILABLE_PHOSPHORUS"); o(97, "NEW:SOIL_TOTAL_PHOSPHORUS")
o([119, 183, 189], "SOIL_FERTILITY_INDICATOR_CA"); o(190, "SOIL_FERTILITY_INDICATOR_MG")
o(120, "NEW:SOIL_SULFUR"); o(74, "NEW:SOIL_AVAILABLE_NUTRIENTS"); o(136, "NEW:SOIL_SALINITY")
o([23, 40, 41, 144], "NEW:BIOLOGICAL_NITROGEN_FIXATION")
o([29, 35, 100, 105, 138, 198], "NEW:SOIL_ENZYME_ACTIVITY")
o([27, 56, 73], "NEW:SOIL_RESPIRATION", "direction needs review: respiration is a carbon loss")
o([36, 206], "SOIL_MICROBIAL_BIOMASS")
o([173, 174, 175, 176, 177, 178, 209], "NEW:MYCORRHIZAL_COLONIZATION")
o([121, 98], "NEW:SOIL_HEALTH_INDEX")
o([96, 125, 126, 157, 158, 160, 161, 162], "SOIL_ORGANIC_CARBON", "carbon fractions and indices")
o([172, 192], "SOIL_CARBON_STOCKS")
o([115, 134], "NEW:CARBON_BALANCE"); o(116, "CARBON_DIOXIDE_EMISSIONS"); o([170, 171], "ABOVEGROUND_CARBON_BIOMASS")
o([17, 20, 84, 141], "GROSS_MARGIN"); o([57, 90], "GROSS_RETURN"); o(37, "TOTAL_FACTOR_PRODUCTIVITY"); o(132, "NEW:EMPLOYMENT")
o([32, 78, 79, 80, 81, 82, 83, 203], "NEW:NATURAL_ENEMY_ABUNDANCE")
o([109, 110], "NEW:POLLINATOR_ABUNDANCE"); o(111, "POLLINATION")
o([31, 49, 50, 99, 139, 140, 142, 143, 152, 153, 154, 179, 204, 167], "NEW:PEST_ABUNDANCE")
o([71, 75], "INFILTRATION_RATE"); o(14, "DISCHARGE"); o(131, "SOIL_LOSS"); o([200, 201], "SOIL_AGGREGATE_STABILITY")
o([30, 146, 182], "VEGETATION_COVER"); o(117, "NEW:TREE_REGENERATION"); o([184, 185], "NEW:TREE_DENSITY")
o([59, 202], "NEW:LITTER_DECOMPOSITION"); o(168, "NEW:LODGING"); o(155, "NEW:AMMONIA_EMISSIONS"); o(156, "NUTRIENT_LEACHING")
o(76, "FEED_DIGESTIBILITY", "net energy feed value")

ONOT = {10: "threshold parameter", 11: "statistical association", 12: "co-occurrence pattern", 13: "co-occurrence pattern",
        15: "composite index without direction", 19: "biomarker fraction", 24: "mechanical trait", 28: "percolation: direction context-dependent",
        42: "pest life-history trait", 43: "pest life-history trait", 44: "pest life-history trait", 45: "pest life-history trait",
        46: "composite growth indicator", 47: "composite growth indicator", 48: "vague cycling index", 51: "nitrogen balance: direction context-dependent",
        52: "nitrogen balance: direction context-dependent", 53: "nitrogen balance: direction context-dependent", 60: "correlation", 61: "correlation",
        68: "landscape index", 69: "composite index", 70: "composite index", 85: "composite index", 91: "behavioural model path", 92: "behavioural model path",
        93: "behavioural model path", 94: "behavioural model path", 95: "behavioural model path", 104: "isotope ratio", 108: "composition difference",
        123: "residue input, not an outcome", 124: "residue input, not an outcome", 129: "model parameter", 130: "plot descriptor",
        147: "percolation: direction context-dependent", 148: "tracer activity", 149: "descriptor", 150: "descriptor", 151: "deposition: context-dependent",
        159: "incubation parameter", 181: "national aggregate", 187: "not an outcome", 188: "ratio with no direction", 205: "vague", 207: "vague", 208: "vague"}
OPREF = {"NEW:YIELD_COMPONENTS": 18, "NEW:PRODUCE_QUALITY": 3, "NEW:PLANT_GROWTH": 8, "NEW:PEST_ABUNDANCE": 49,
         "NEW:NATURAL_ENEMY_ABUNDANCE": 83, "NEW:SOIL_ENZYME_ACTIVITY": 100, "NEW:MYCORRHIZAL_COLONIZATION": 209,
         "NEW:BIOLOGICAL_NITROGEN_FIXATION": 23, "NEW:SOIL_HEALTH_INDEX": 98, "NEW:ENERGY_BALANCE": 72, "NEW:CARBON_BALANCE": 115,
         "NEW:TREE_DENSITY": 185, "NEW:LITTER_DECOMPOSITION": 202, "NEW:NUTRIENT_UPTAKE": 62}
ou = rd(REV / "HAB_outcomes_review.csv")
assert len(ou) == 211, len(ou)
if "reviewer_note" not in ou.columns:
    ou["reviewer_note"] = ""
omapped = 0
for i in range(len(ou)):
    if i in O:
        oid, note = O[i]
        ou.loc[i, "outcome_id"] = oid; ou.loc[i, "accepted"] = "yes"; ou.loc[i, "reviewer"] = REVIEWER
        ou.loc[i, "date"] = DATE; ou.loc[i, "reviewer_note"] = note; omapped += 1
    elif i in ONOT:
        ou.loc[i, "accepted"] = "no"; ou.loc[i, "reviewer"] = REVIEWER; ou.loc[i, "date"] = DATE; ou.loc[i, "reviewer_note"] = ONOT[i]
    else:
        raise SystemExit(f"outcome row {i} ({ou.loc[i,'raw_label']}) has no decision")
ou["_k"] = [0 if (i in O and OPREF.get(O[i][0]) == i) else 1 for i in range(len(ou))]
ou["_i"] = range(len(ou))
ou = ou.sort_values(["_k", "_i"]).drop(columns=["_k", "_i"]).reset_index(drop=True)
wr(ou, REV / "HAB_outcomes_review.csv")
print("outcomes: mapped", omapped, "not an outcome", len(ONOT), "rows covered", ou[ou.accepted=='yes'].n_rows.astype(int).sum(), "of", ou.n_rows.astype(int).sum())

# ---------------------------------------------------------------- direction review
d = rd(REV / "outcomes_direction_review.csv")
d["accepted"] = "yes"; d["reviewer"] = REVIEWER; d["date"] = DATE
d["proposed_by"] = d["proposed_by"].str.replace(r" \(.*\)$", "", regex=True)
wr(d, REV / "outcomes_direction_review.csv"); print("direction review accepted", len(d))

# ---------------------------------------------------------------- merges
mg = rd(REV / "practice_merges.csv")
better = {"SOIL_BUND_VEGETATED_WITH_FORAGE_GRASS", "STONE_FACED_SOIL_BUND_WITH_FORAGE_TREES", "FANYA_JUU_VEGETATED_WITH_FORAGE_GRASS_TREES",
          "FANYA_JUU_WITH_VETIVAR_GRASS", "DENSHO_GRASS_BUND", "GRADED_LEVEL_STONE_FACED_SOIL_BUND_STABILIZED_WITH_GRASSES",
          "GRADED_LEVEL_STONE_FACED_SOIL_BUND_STABILIZED_WITH_TREES", "LIVE_CHECK_DAM", "GULLY_WALL_RE_SHAPING_AND_REVEGETATION"}
for i, r in mg.iterrows():
    if r.practice_id_a in better and r.relation == "narrower_than":
        mg.loc[i, "practice_id_b"] = "PHYSICAL_PLUS_BIOLOGICAL_SWC_PRACTICES"
        mg.loc[i, "reason"] = r.reason + " | reviewer: vegetated or live structure, parent corrected to PHYSICAL_PLUS_BIOLOGICAL_SWC_PRACTICES"
    if r.practice_id_a == "BIOLOGICAL_GULLY_REHABILITATION":
        mg.loc[i, "practice_id_b"] = "BIOLOGICAL_SWC_PRACTICES"
        mg.loc[i, "reason"] = r.reason + " | reviewer: biological measure, parent corrected to BIOLOGICAL_SWC_PRACTICES"
mg["accepted"] = "yes"; mg["reviewer"] = REVIEWER; mg["date"] = DATE
wr(mg, REV / "practice_merges.csv"); print("merges accepted", len(mg))

# ---------------------------------------------------------------- geocoding
g = rd(EVREV / "geocoding_review.csv")
conf = {
 "10.1016/j.ijagro.2024.100012": ("Gozamin", "10.5", "37.5", "district"),
 "10.1155/aess/9969088": ("Kenna district, Konso", "5.25", "37.483", "district"),
 "10.1002/ldr.2182": ("Galessa watershed, Dendi", "9.07", "38.1", "district"),
 "10.1016/j.agwat.2010.01.012": ("Mekelle", "13.48", "39.48", "site"),
 "10.1079/sum2005321": ("Dogu'a Tembien (Hagere Selam)", "13.65", "39.17", "district"),
 "10.1016/j.still.2007.08.002": ("Lenche Dima watershed, Gubalafto", "11.72", "39.63", "site"),
 "10.1007/s10457-025-01343-0": ("Tullo district, West Hararghe", "8.67", "40.85", "district"),
 "10.9734/ijpss/2014/8797": ("Bako Tibe", "9.0", "37.167", "site"),
}
n = 0
for i, r in g.iterrows():
    key = r.doi.strip().lower()
    if key in conf:
        site, lat, lon, prec = conf[key]
        g.loc[i, ["site_name", "lat", "lon", "loc_precision"]] = [site, lat, lon, prec]
        g.loc[i, "method"] = "reviewer_confirmed" if r.method.startswith("geonames") else "reviewer_knowledge"
        g.loc[i, "accepted"] = "yes"; g.loc[i, "reviewer"] = REVIEWER; g.loc[i, "date"] = DATE; n += 1
wr(g, EVREV / "geocoding_review.csv"); print("geocoding rows accepted", n)
gp = rd(EVREV / "geocoding_ET_reviewer_proposals.csv")
gp["proposed_by"] = gp["proposed_by"].str.replace(r" \(.*\)$", "", regex=True)
gp.loc[gp.action.str.startswith("confirm"), ["accepted", "reviewer", "date"]] = ["yes", REVIEWER, DATE]
gp.loc[gp.action == "keep country precision", ["accepted", "reviewer", "date"]] = ["yes", REVIEWER, DATE]
wr(gp, EVREV / "geocoding_ET_reviewer_proposals.csv"); print("proposals sheet updated")
