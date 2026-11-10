"""Deterministic mapping rules for the practice and outcome taxonomies.

* :func:`normalise_label`: case, punctuation, doses/units, parentheticals,
  plurals and known synonyms.
* :func:`label_components`: canonical components mentioned in a practice
  label, ordered by first mention. It **extends** (never replaces)
  ``rag.graph.component_keywords.COMPONENT_KEYWORDS`` with the extra spellings
  seen in Habtamu's sheet (:data:`EXTRA_COMPONENT_KEYWORDS`).
* :data:`OUTCOME_RULES`: ordered keyword rules label -> outcome id (first
  match wins; specific before general, e.g. weed biomass before biomass).
* :data:`OUTCOME_CANON` and :data:`ERA_OUTCOME_ATTRS`: proposed attributes
  (direction, unit class, objective group) of every outcome the rules can
  produce. Every direction here is a **proposal** until a reviewer sets the
  outcome's status to ``reviewed`` (the 7 legacy indicators excepted, whose
  direction is ``recommend.DIRECTION``).
"""
from __future__ import annotations

import re
import unicodedata
from functools import lru_cache

from rag.graph.component_keywords import COMPONENT_KEYWORDS
from rag.graph.practice_components import CANONICAL_COMPONENTS

# --------------------------------------------------------------- normalising
#: (regex on the normalised text, replacement); applied in order.
SYNONYMS: list[tuple[str, str]] = [
    (r"\b(?:no|zero|minimum) till(?:age)?\b|\bnotill\b", "reduced tillage"),
    (r"(?<!crop )\brotation\b", "crop rotation"),
    (r"\bintercrop\b", "intercropping"),
    (r"fertiliser", "fertilizer"),
    (r"\bagro forestry\b", "agroforestry"),
    (r"\bvetivar\b", "vetiver"),
]
_PAREN = re.compile(r"\([^)]*\)|\[[^\]]*\]|\$[^$]*\$")
_DOSE = re.compile(
    r"\b\d+(?:[.,]\d+)?\s*(?:%|t|mg|kg|g|l|m|cm|mm|yr|years?|months?|days?)\b(?:\s*(?:ha|c|n|p|k)\b)?"
    r"(?:\s*(?:-|⁻|−)?\s*1)?",
    re.I,
)


def normalise_label(text: str | None) -> str:
    """Lower-cased, punctuation-free, dose-free, singular form used for exact matching."""
    if not text:
        return ""
    s = unicodedata.normalize("NFKC", str(text)).lower()
    s = _PAREN.sub(" ", s)
    s = _DOSE.sub(" ", s)
    s = s.replace("&", " and ").replace("+", " and ")
    s = re.sub(r"[^a-z0-9/]+", " ", s)
    words = []
    for w in s.split():
        if len(w) > 3 and w.endswith("s") and not w.endswith(("ss", "us", "is")):
            w = w[:-1]
        words.append(w)
    s = " ".join(words)
    for rx, rep in SYNONYMS:
        s = re.sub(rx, rep, s)
    return " ".join(s.split())


# ---------------------------------------------------------------- practices
#: extra keyword spellings -> canonical component (extends COMPONENT_KEYWORDS).
EXTRA_COMPONENT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "Reduced Tillage": ("no till", "no-till", "notill", "no tillage", "no-tillage", "zero till", "zero-till", "non-inversion",
                        "direct seeding", "direct drilling", "strip till", "reduced till", "minimum till",
                        "mulch tillage", "minimum soil disturbance", "conservation tillage"),
    "Conservation Tillage": ("conservation agriculture",),
    # ("residue retention" stays with Crop Residue Incorporation, as in the base P9 table)
    "Mulch": ("mulch", "straw cover", "straw retention", "residue restitution",
              "groundcover", "ground cover", "stubble retention"),
    "Organic Fertilizer": ("compost", "manure", "vermicompost", "cow dung", "cattle dung", "farmyard", "fym", "biocompost",
                           "green manure", "organic fertili", "slurry", "olive mill waste", "poultry litter"),
    "Inorganic Fertilizer": ("npk", " rdf", "recommended dose", "nitrogen fertili", " n fertili", "mineral fertil",
                             "urea", "recommended np", "chemical fertili", "synthetic fertili", "inorganic fertili"),
    "Inorganic Fertilizer Reduction": ("reduced np", "reduced npk", "reduced fertili", "50% npk", "½ rdf"),
    "ISFM": ("integrated nutrient", "integrated plant nutrient", "ipns", "integrated soil fertility"),
    "Biochar": ("biochar", "bio-char"),
    "Intercropping": ("intercrop", "strip cropping", "relay crop", "push-pull", "push pull", "polyculture",
                      "mixed cropping", "companion crop", "border crop"),
    "Crop Rotation": ("rotation", "crop sequence", "ley"),
    "Improved Fallow": ("improved fallow",),
    "Alleycropping": ("hedgerow", "alley crop", "alleycrop"),
    "Other Agroforestry": ("agroforest", "trees integrated", "farm tree", "shade tree", "scattered tree",
                           "slash-and-mulch"),
    "Parklands": ("parkland",),
    "Multistrata Agroforestry": ("multistrata", "multi-strata", "home garden", "homegarden"),
    "Physical SWC Measures": ("terrace", "bund", "check dam", "check-dam", "trench", "gully", "gabion",
                              "fanya", "stone line", "stone wall"),
    "In-situ Water Harvesting": ("zai", "tied ridg", "tie ridg", "tied-ridg", "basin", "half moon", "half-moon",
                                 "ridge and furrow", "planting pit", "micro-catchment", "microcatchment"),
    "Water Harvesting": ("water harvest", "pond", "cistern", "rainwater harvest"),
    "Biological SWC Practices": ("vetiver", "grass strip", "vegetative strip", "flower strip", "buffer strip",
                                 "desho", "grass barrier"),
    "Exclosure": ("exclosure", "area closure", "enclosure", "passive restoration"),
    "Grazing Management": ("grazing", "rotational graz"),
    "Pasture Management": ("pasture", "grass-clover", "grassland management"),
    "Improved Varieties": ("improved variet", "hybrid", "improved cultivar", "tolerant variet", "resistant variet"),
    "pH Control": ("lime", "liming", "gypsum"),
    "Drip Irrigation": ("drip",),
    "Deficit Irrigation": ("deficit irrigation",),
    "Supplemental Irrigation": ("supplemental irrigation", "supplementary irrigation"),
    "Weeding": ("weeding", "hand weed", "mechanical weed"),
}


@lru_cache(maxsize=1)
def _component_index() -> tuple[tuple[str, str], ...]:
    pairs: list[tuple[str, str]] = []
    for comp, kws in list(COMPONENT_KEYWORDS.items()) + list(EXTRA_COMPONENT_KEYWORDS.items()):
        if comp not in CANONICAL_COMPONENTS:
            raise ValueError(f"unknown component {comp!r} in keyword tables")
        for kw in kws:
            pairs.append((kw.lower(), comp))
    pairs.sort(key=lambda p: -len(p[0]))  # longest keyword first
    return tuple(pairs)


def label_components(text: str | None) -> list[str]:
    """Canonical components mentioned in ``text``, ordered by first mention.

    Longer keywords win over shorter ones on overlapping spans (``alternate
    furrow`` before ``furrow``); a keyword must start a word (``ley`` does not
    match ``barley``); text in brackets counts only when nothing outside the
    brackets matches.
    """
    if not text:
        return []
    full = unicodedata.normalize("NFKC", str(text)).lower()
    outside = _PAREN.sub(" ", full)
    hits = _scan(" " + outside + " ")
    if not hits:  # the brackets often carry the description ("SMAS-1 (slash-and-mulch agroforestry)")
        hits = _scan(" " + full + " ")
    return hits


def _scan(low: str) -> list[str]:
    """Leftmost-longest, non-overlapping keyword matches (base table first on equal spans)."""
    cands: list[tuple[int, int, int, str]] = []  # (start, -length, table order, component)
    for order, (kw, comp) in enumerate(_component_index()):
        start = 0
        while True:
            i = low.find(kw, start)
            if i < 0:
                break
            if not (low[i - 1].isalpha() and kw[0].isalpha()):  # "ley" must not match "barley"
                cands.append((i, -len(kw), order, comp))
            start = i + 1
    cands.sort()
    taken = [False] * len(low)
    hits: list[tuple[int, str]] = []
    for i, neg_len, _, comp in cands:
        j = i - neg_len
        if not any(taken[i:j]):
            for k in range(i, j):
                taken[k] = True
            hits.append((i, comp))
    hits.sort()
    out: list[str] = []
    for _, comp in hits:
        if comp not in out:
            out.append(comp)
    return out


#: A practice label that negates a practice ("without compost", "no soil management")
#: or names the comparator ("conventional", "control", "monoculture") is never
#: rule-mapped; it goes to the review sheet.
NEGATION = re.compile(
    r"\bwithout\b|\bno (?!till)|\bnon[- ](?!inversion)|\bconventional\b|\bcontrol\b|\bmonocrop|\bmonocultur"
    r"|restriction|exclu"
)


def is_negated(label: str | None) -> bool:
    """True when a practice label negates or names a comparator rather than a practice."""
    return bool(label) and bool(NEGATION.search(unicodedata.normalize("NFKC", str(label)).lower()))


#: catalogue category (lower) -> frozen practice family.
CATEGORY_FAMILY = {
    "soil and water conservation": "Erosion control and water management",
    "agroforestry": "Agro-forestry and forest management",
    "forestry": "Agro-forestry and forest management",
    "soil fertility management": "Integrated soil fertility management",
    "integrated soil fertility management": "Integrated soil fertility management",
    "crop production": "Crop production and management",
    "crop management": "Crop production and management",
    "livestock": "Livestock production and management",
    "water management": "Erosion control and water management",
}

# ----------------------------------------------------------------- outcomes
#: id -> (name_en, direction, unit_class, objective_group). Proposed attributes of
#: outcomes the keyword rules target (directions are proposals until reviewed).
OUTCOME_CANON: dict[str, tuple[str, int, str, str]] = {
    # legacy 7 (direction overwritten from recommend.DIRECTION at seeding)
    "YIELD": ("Crop yield", 1, "yield", "productivity"),
    "BIOMASS_YIELD": ("Biomass yield", 1, "yield", "productivity"),
    "INCOME": ("Income (net return)", 1, "money", "economics"),
    "WATER_USE_EFFICIENCY": ("Water use efficiency", 1, "rate", "water"),
    "SOM_CONTENT": ("Soil organic matter content", 1, "fraction", "soil_health"),
    "SOIL_LOSS": ("Soil loss", -1, "mass", "water"),
    "RUNOFF": ("Runoff", -1, "other", "water"),
    # rule targets
    "RUNOFF_COEFFICIENT": ("Runoff coefficient", -1, "fraction", "water"),
    "INFILTRATION_RATE": ("Infiltration rate", 1, "rate", "water"),
    "SOIL_MOISTURE": ("Soil moisture", 1, "fraction", "water"),
    "WATER_HOLDING_CAPACITY": ("Soil water holding capacity", 1, "fraction", "water"),
    "BULK_DENSITY": ("Soil bulk density", -1, "concentration", "soil_health"),
    "SOIL_COMPACTION": ("Soil compaction / penetration resistance", -1, "other", "soil_health"),
    "SOIL_AGGREGATE_STABILITY": ("Soil aggregate stability", 1, "fraction", "soil_health"),
    "SOIL_POROSITY": ("Soil porosity", 1, "fraction", "soil_health"),
    "SOIL_ORGANIC_CARBON": ("Soil organic carbon", 1, "concentration", "soil_health"),
    "SOIL_CARBON_STOCKS": ("Soil carbon stocks", 1, "mass", "soil_health"),
    "ABOVEGROUND_CARBON_BIOMASS": ("Aboveground carbon biomass", 1, "mass", "other"),
    "SOIL_MICROBIAL_BIOMASS": ("Soil microbial biomass", 1, "concentration", "soil_health"),
    "SOIL_FAUNA": ("Soil fauna abundance", 1, "count", "resilience_biodiversity"),
    "SOIL_TOTAL_NITROGEN": ("Soil total nitrogen", 1, "concentration", "soil_health"),
    "SOIL_AVAILABLE_NITROGEN": ("Soil available nitrogen", 1, "concentration", "soil_health"),
    "SOIL_NITROGEN": ("Soil nitrogen", 1, "concentration", "soil_health"),
    "AVAILABLE_PHOSPHORUS": ("Soil available phosphorus", 1, "concentration", "soil_health"),
    "SOIL_POTASSIUM": ("Soil potassium", 1, "concentration", "soil_health"),
    "CATION_EXCHANGE_CAPACITY": ("Cation exchange capacity", 1, "concentration", "soil_health"),
    "SOIL_PH": ("Soil pH (higher is better on acidic soils; context dependent)", 1, "index", "soil_health"),
    "SOIL_ACIDITY": ("Soil exchangeable acidity", -1, "concentration", "soil_health"),
    "NUTRIENT_LEACHING": ("Nutrient leaching / loss", -1, "mass", "water"),
    "NUTRIENT_USE_EFFICIENCY": ("Nutrient use efficiency", 1, "rate", "other"),
    "GHG_EMISSIONS": ("Greenhouse gas emissions", -1, "mass", "other"),
    "LAND_EQUIVALENT_RATIO": ("Land equivalent ratio", 1, "index", "productivity"),
    "NET_PRESENT_VALUE": ("Net present value", 1, "money", "economics"),
    "BENEFIT_COST_RATIO": ("Benefit cost ratio", 1, "index", "economics"),
    "GROSS_MARGIN": ("Gross margin", 1, "money", "economics"),
    "GROSS_RETURN": ("Gross return", 1, "money", "economics"),
    "PRODUCTION_COST": ("Production cost", -1, "money", "economics"),
    "LABOUR_INPUT": ("Labour input", -1, "other", "economics"),
    "RETURN_TO_LABOUR": ("Return to labour", 1, "money", "economics"),
    "BIODIVERSITY": ("Biodiversity (diversity, richness, abundance of non-pest taxa)", 1, "index", "resilience_biodiversity"),
    "WEED_SUPPRESSION": ("Weed suppression", 1, "fraction", "productivity"),
    "WEED_PRESSURE": ("Weed pressure (density, biomass, cover)", -1, "count", "productivity"),
    "PEST_DAMAGE": ("Pest and disease damage", -1, "fraction", "productivity"),
    "NATURAL_PEST_CONTROL": ("Natural pest control (parasitism, predation)", 1, "fraction", "resilience_biodiversity"),
    "POLLINATION": ("Pollination (visitation, seed or fruit set)", 1, "fraction", "resilience_biodiversity"),
    "VEGETATION_COVER": ("Vegetation cover", 1, "fraction", "water"),
    "CROP_RESIDUE_YIELD": ("Crop residue yield", 1, "yield", "productivity"),
    "WEIGHT_GAIN": ("Weight gain", 1, "rate", "livestock"),
    "MILK_YIELD": ("Milk yield", 1, "yield", "livestock"),
    "MEAT_YIELD": ("Meat yield", 1, "yield", "livestock"),
    "FEED_DIGESTIBILITY": ("Feed digestibility / conversion", 1, "fraction", "livestock"),
    "SURVIVAL_RATE": ("Survival rate", 1, "fraction", "resilience_biodiversity"),
}
LEGACY_IDS = {
    "yield": "YIELD", "biomass yield": "BIOMASS_YIELD", "income": "INCOME",
    "water use efficiency": "WATER_USE_EFFICIENCY", "SOM content": "SOM_CONTENT",
    "soil loss": "SOIL_LOSS", "runoff": "RUNOFF",
}

#: ERA outcome name -> (direction, unit_class, objective_group); the 7 legacy names are
#: mapped through ERA_LEGACY instead. Ids are the upper-snake ERA names.
ERA_LEGACY = {
    "Crop Yield": "YIELD", "Biomass Yield": "BIOMASS_YIELD", "Net Return": "INCOME",
    "Water Use Efficiency": "WATER_USE_EFFICIENCY", "Soil Organic Matter": "SOM_CONTENT",
    "Erosion": "SOIL_LOSS", "Runoff": "RUNOFF",
}
ERA_OUTCOME_ATTRS: dict[str, tuple[int, str, str]] = {
    "Aboveground Carbon Biomass": (1, "mass", "other"),
    "Animal Survival": (1, "fraction", "livestock"),
    "Beneficial Organisms": (1, "count", "resilience_biodiversity"),
    "Benefit Cost Ratio (GMVC)": (1, "index", "economics"),
    "Benefit Cost Ratio (GRVC)": (1, "index", "economics"),
    "Benefit Cost Ratio (NRTC)": (1, "index", "economics"),
    "Biodiversity": (1, "index", "resilience_biodiversity"),
    "CO2 Equivalent Emissions": (-1, "mass", "other"),
    "Carbon Dioxide Emissions": (-1, "mass", "other"),
    "Cation Exchange Capacity": (1, "concentration", "soil_health"),
    "Cooking Time": (-1, "other", "other"),
    "Cookstove Emissions": (-1, "mass", "other"),
    "Crop Residue Yield": (1, "yield", "productivity"),
    "Feed Conversion Ratio (In Out)": (-1, "index", "livestock"),
    "Feed Conversion Ratio (Out In)": (1, "index", "livestock"),
    "Fixed Cost": (-1, "money", "economics"),
    "Fuel Savings": (1, "other", "other"),
    "Fuel Use": (-1, "other", "other"),
    "Gross Margin": (1, "money", "economics"),
    "Gross Return": (1, "money", "economics"),
    "Infiltration Rate": (1, "rate", "water"),
    "Labour Cost": (-1, "money", "economics"),
    "Labour Female": (-1, "other", "economics"),
    "Labour Male": (-1, "other", "economics"),
    "Labour Person Hours": (-1, "other", "economics"),
    "Land Equivalent Ratio": (1, "index", "productivity"),
    "Marginal Rate of Return": (1, "index", "economics"),
    "Meat Yield": (1, "yield", "livestock"),
    "Milk Yield": (1, "yield", "livestock"),
    "Nitrogen (Apparent Efficiency Animals Feed)": (1, "rate", "livestock"),
    "Nitrogen Agronomic Efficiency": (1, "rate", "other"),
    "Nitrogen Factor Productivity": (1, "rate", "other"),
    "Nitrogen Use Efficiency (ARE AGB)": (1, "rate", "other"),
    "Nitrogen Use Efficiency (ARE Product)": (1, "rate", "other"),
    "Nitrogen Use Efficiency (ARE Unspecificed)": (1, "rate", "other"),
    "Phosphorus Agronomic Efficiency": (1, "rate", "other"),
    "Phosphorus Use Efficiency (ARE Product)": (1, "rate", "other"),
    "Protein Conversion Ratio (In Out)": (-1, "index", "livestock"),
    "Protein Conversion Ratio (Out In)": (1, "index", "livestock"),
    "Return to Labour": (1, "money", "economics"),
    "Soil Available Nitrogen": (1, "concentration", "soil_health"),
    "Soil Carbon Stocks": (1, "mass", "soil_health"),
    "Soil Moisture": (1, "fraction", "water"),
    "Soil Nitrogen": (1, "concentration", "soil_health"),
    "Soil Organic Carbon": (1, "concentration", "soil_health"),
    "Soil Organic Carbon (Change)": (1, "rate", "soil_health"),
    "Soil Total Nitrogen": (1, "concentration", "soil_health"),
    "Total Cost": (-1, "money", "economics"),
    "Total Factor Productivity": (1, "index", "economics"),
    "Variable Cost": (-1, "money", "economics"),
    "Water Use": (-1, "other", "water"),
    "Weight Gain": (1, "rate", "livestock"),
}
ERA_OUTCOME_NOTES = {
    "Water Use": "ambiguous in ERA (amount of water used); direction -1 proposed, review",
    "Labour Female": "labour input; -1 proposed (less labour better), review",
    "Labour Male": "labour input; -1 proposed (less labour better), review",
}

#: Ordered (regex, outcome_id): first match on the normalised label wins.
OUTCOME_RULES: list[tuple[str, str]] = [
    (r"runoff coefficient", "RUNOFF_COEFFICIENT"),
    (r"divers|richness|shannon|simpson|evenness|margalef|pielou|\bspecies\b|agrobiodiversity|red list", "BIODIVERSITY"),
    (r"weed suppression|weed control", "WEED_SUPPRESSION"),
    (r"\bweed", "WEED_PRESSURE"),
    (r"parasitism|predation|natural enem|predator|biological control|biocontrol", "NATURAL_PEST_CONTROL"),
    (r"injur|damage|infest|grain loss|incidence|severity|disease|\bpest\b|aphid|borer", "PEST_DAMAGE"),
    (r"pollinat|seed set|fruit set|visitation", "POLLINATION"),
    (r"leach|(?:nitrogen|phosphorus|nutrient|\bn|\bp|\bk|\btn) (?:runoff )?(?:loss|load)|runoff associated|total p loss", "NUTRIENT_LEACHING"),
    (r"emission|\bn2o|\bch4|\bghg|carbon footprint|global warming", "GHG_EMISSIONS"),
    (r"water use efficiency|\bwue\b|rwue|water productivity", "WATER_USE_EFFICIENCY"),
    (r"nitrogen use efficiency|nutrient use efficiency|\bnue\b|agronomic efficiency|fertilizer replacement", "NUTRIENT_USE_EFFICIENCY"),
    (r"land equivalent ratio|\bler\b|\blert\b", "LAND_EQUIVALENT_RATIO"),
    (r"soil loss|erosion|sediment|soil erodibility|erodibility", "SOIL_LOSS"),
    (r"runoff|run off", "RUNOFF"),
    (r"infiltration|hydraulic conductivity|hydrulic conductivity", "INFILTRATION_RATE"),
    (r"water holding capacity|plant available water|available water", "WATER_HOLDING_CAPACITY"),
    (r"soil water|soil moisture|moisture content|water content|water storage", "SOIL_MOISTURE"),
    (r"bulk density", "BULK_DENSITY"),
    (r"penetration resistance|compaction", "SOIL_COMPACTION"),
    (r"aggregat|\bwsa\b|\bmwd\b", "SOIL_AGGREGATE_STABILITY"),
    (r"porosity", "SOIL_POROSITY"),
    (r"microbial biomass", "SOIL_MICROBIAL_BIOMASS"),
    (r"earthworm|macrofauna|mesofauna|soil fauna|collembola|centipede|millipede|invertebrate", "SOIL_FAUNA"),
    (r"above ?ground .*carbon|biomass carbon|tree carbon|carbon .*biomass", "ABOVEGROUND_CARBON_BIOMASS"),
    (r"carbon stock|soc stock|soc storage|carbon storage|carbon sequestration|\bc stock|co2 equivalent uptake", "SOIL_CARBON_STOCKS"),
    (r"soil organic matter|\bsom\b|organic matter", "SOM_CONTENT"),
    (r"organic carbon|ogranic carbon|\bsoc\b|soil carbon|carbon content|whole soil carbon|\bmaoc\b|\bpoc\b|labile carbon|extractable carbon", "SOIL_ORGANIC_CARBON"),
    (r"available nitrogen|mineral nitrogen|mineral n\b|available n\b|nitrate|ammonium", "SOIL_AVAILABLE_NITROGEN"),
    (r"total nitrogen|total soil nitrogen|\btn\b", "SOIL_TOTAL_NITROGEN"),
    (r"available p\b|available phosphorus|olsen", "AVAILABLE_PHOSPHORUS"),
    (r"potassium|exch ?k\b|\bav ?k\b", "SOIL_POTASSIUM"),
    (r"cation exchange|\bcec\b", "CATION_EXCHANGE_CAPACITY"),
    (r"exchangeable acidity|soil acidity", "SOIL_ACIDITY"),
    (r"\bph\b", "SOIL_PH"),
    (r"net present value|\bnpv\b", "NET_PRESENT_VALUE"),
    (r"benefit ?cost|cost ?benefit|\bbcr\b", "BENEFIT_COST_RATIO"),
    (r"gross margin", "GROSS_MARGIN"),
    (r"return to labou?r", "RETURN_TO_LABOUR"),
    (r"net (?:income|return|revenue|profit|benefit)|\bprofit|\bincome\b", "INCOME"),
    (r"gross (?:return|revenue|income)|\brevenue", "GROSS_RETURN"),
    (r"\bcost", "PRODUCTION_COST"),
    (r"labou?r", "LABOUR_INPUT"),
    (r"weight gain|live ?weight|body weight|daily gain|average gain|total gain|growth rate", "WEIGHT_GAIN"),
    (r"\bmilk", "MILK_YIELD"),
    (r"\bmeat|carcass", "MEAT_YIELD"),
    (r"digestib|digestab|digesion|feed conversion|feed efficiency|diet conversion", "FEED_DIGESTIBILITY"),
    (r"surviv", "SURVIVAL_RATE"),
    (r"residue yield|straw yield|stover yield", "CROP_RESIDUE_YIELD"),
    (r"biomass|dry matter|\bforage|fodder|herbage", "BIOMASS_YIELD"),
    (r"vegetation cover|ground cover|canopy cover|basal cover", "VEGETATION_COVER"),
    (r"\byield|grain production|crop production|cereal production|\bproductivity|harvest", "YIELD"),
]
_COMPILED = [(re.compile(rx), oid) for rx, oid in OUTCOME_RULES]
for _rx, _oid in OUTCOME_RULES:
    if _oid not in OUTCOME_CANON:
        raise ValueError(f"OUTCOME_RULES target {_oid} missing from OUTCOME_CANON")

#: Outcome_type(domain) values (lower) that allow the domain fallback to BIODIVERSITY.
BIODIVERSITY_DOMAINS = re.compile(r"biodiversit")
BIODIVERSITY_LABEL_HINT = re.compile(r"abundance|density|number of|richness|species|population|taxa|order")


def outcome_text(label: str | None) -> str:
    """Light normalisation for outcome rules: lower case, punctuation to spaces.

    Unlike :func:`normalise_label` it keeps parenthetical abbreviations
    (``Yield advantage (LER)`` must reach the LER rule, not the yield rule).
    """
    if not label:
        return ""
    s = unicodedata.normalize("NFKC", str(label)).lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " " + " ".join(s.split()) + " "


def outcome_rule(label: str | None) -> tuple[str | None, str | None]:
    """``(outcome_id, rule_regex)`` of the first keyword rule matching ``label``."""
    norm = outcome_text(label)
    for rx, oid in _COMPILED:
        if rx.search(norm):
            return oid, rx.pattern
    return None, None


def propose_attrs(name: str) -> tuple[int, str, str]:
    """Heuristic proposal ``(direction, unit_class, objective_group)`` for a new outcome name."""
    oid, _ = outcome_rule(name)
    if oid:
        _, d, u, g = OUTCOME_CANON[oid]
        return d, u, g
    low = name.lower()
    d = -1 if re.search(r"cost|loss|emission|time|leach|density|disease|incidence|labou?r", low) else 1
    return d, "other", "other"
