"""WOCAT controlled vocabularies, transcribed from the official questionnaire.

Source (verified 23 Oct 2026 against the file itself, not a secondary read):

    WOCAT (2019). *Questionnaire on Sustainable Land Management (SLM)
    Technologies* (QT), English version. Eds. Liniger, H., Schwilch, G.,
    Gurtner, M., Mekdaschi Studer, R., Hauert, C., van Lynden, G.,
    Critchley, W., Fleiner, R., Harari, N., Gavilano, A., Lauterburg, R.
    Centre for Development and Environment (CDE), University of Bern.
    DOCX: https://wocat.net/documents/447/QT_English_2019_CClicence.docx

Licence of the questionnaire and of data documented through WOCAT, as stated
in QT §1.3: **Creative Commons Attribution-NonCommercial-ShareAlike 4.0
International** (https://creativecommons.org/licenses/by-nc-sa/4.0/) —
attribution to WOCAT and the compilers, link to the licence, indicate
changes, non-commercial use, share-alike for derived data. Any derived
WOCAT data released with the manuscript carries the same licence.

Verification notes (differences found against
``docs/decisions/wocat_taxonomy_draft.md``, which was a partial read):

* §1.3 states CC BY-NC-SA **4.0 International**, not 3.0 Unported as the
  draft recorded. The database site states 4.0 as well, so both agree.
* §6.1 "Climate and disaster risk reduction" has one more variable than the
  draft captured: ``micro-climate`` (worsened / improved).
* §6.5 adoption bands in the questionnaire are
  ``single cases/experimental``, ``1-10%``, ``10-50%``, ``more than 50%``.
  The live database renders its own band labels (e.g. "11 – 50 %"), so
  :func:`normalize_adoption_band` maps both spellings onto the QT classes.
* §6.1 ``pests/ diseases`` is printed with its poles as
  ``decreased`` (negative end) / ``increased`` (positive end) — inverted
  relative to every other harmful-outcome row in the same table (e.g.
  ``harmful species``: ``increased`` / ``decreased``). The poles are
  transcribed verbatim; ``good_direction`` follows the substantive meaning
  and the discrepancy is recorded in ``source_note``.

The PDF URL given in the phase brief
(``wocat.net/documents/448/Questionnaire_on_SLM_Technologies_-_English_FINAL.pdf``)
returned HTTP 404 on 23 Oct 2026; the DOCX above is the copy used here.

Nothing in this module is generated: every label is a literal transcription.
"""
from __future__ import annotations

from dataclasses import dataclass, field

QUESTIONNAIRE_CITATION = (
    "WOCAT (2019). Questionnaire on Sustainable Land Management (SLM) "
    "Technologies (QT), English version. CDE, University of Bern."
)
QUESTIONNAIRE_URL = "https://wocat.net/documents/447/QT_English_2019_CClicence.docx"
LICENCE = "CC BY-NC-SA 4.0 International"
LICENCE_URL = "https://creativecommons.org/licenses/by-nc-sa/4.0/"


# --------------------------------------------------------------- §3.5 groups
#: QT §3.5 — a Technology is assigned to one, or at most three, of these.
#: Transcribed verbatim, in questionnaire order.
SLM_GROUPS: tuple[str, ...] = (
    "natural and semi-natural forest management",
    "forest plantation management",
    "agroforestry",
    "windbreak/ shelterbelt",
    "area closure (stop use, support restoration)",
    "rotational system (crop rotation, fallows, shifting cultivation)",
    "pastoralism and grazing land management",
    "integrated crop-livestock management",
    "improved ground/ vegetation cover",
    "minimal soil disturbance",
    "integrated soil fertility management",
    "cross-slope measure",
    "integrated pest and disease management (incl. organic agriculture)",
    "improved plant varieties/ animal breeds",
    "water harvesting",
    "irrigation management (incl. water supply, drainage)",
    "water diversion and drainage",
    "surface water management",
    "groundwater management",
    "wetland protection/ management",
    "waste management/ waste water management",
    "energy efficiency",
    "beekeeping, aquaculture, poultry, rabbit farming, silkworm farming, etc.",
    "home gardens",
    "ecosystem-based disaster risk reduction",
    "post-harvest measures",
    "other",
)


# ------------------------------------------------------------- §3.6 measures
@dataclass(frozen=True)
class SLMMeasure:
    """One QT §3.6 SLM measure code."""

    code: str
    label: str
    category: str
    examples: str = ""
    sub_options: tuple[str, ...] = ()


#: QT §3.6 — the five measure categories.
SLM_MEASURE_CATEGORIES: tuple[str, ...] = (
    "agronomic",
    "vegetative",
    "structural",
    "management",
    "other",
)

#: QT §3.6 A3 and A6 carry sub-options that must be specified when selected.
A3_TILLAGE_SYSTEMS: tuple[str, ...] = (
    "no tillage",
    "reduced tillage (> 30% soil cover)",
    "full tillage (< 30% soil cover)",
)
A6_RESIDUE_MANAGEMENT: tuple[str, ...] = ("burned", "grazed", "collected", "retained")

SLM_MEASURES: tuple[SLMMeasure, ...] = (
    SLMMeasure("A1", "Vegetation/ soil cover", "agronomic",
               "Mixed cropping, intercropping, relay cropping, cover cropping"),
    SLMMeasure("A2", "Organic matter/ soil fertility", "agronomic",
               "Conservation agriculture, production and application of compost/ "
               "manure, mulching, trash lines, green manure, crop rotation"),
    SLMMeasure("A3", "Soil surface treatment", "agronomic",
               "Zero tillage (no-till), minimum tillage, contour tillage",
               A3_TILLAGE_SYSTEMS),
    SLMMeasure("A4", "Subsurface treatment", "agronomic",
               "Breaking compacted subsoil (hard pans), deep ripping, double digging"),
    SLMMeasure("A5", "Seed management, improved varieties", "agronomic",
               "Production of seeds and seedlings, seed selection, seed banks, "
               "development/ production of improved varieties"),
    SLMMeasure("A6", "Residue management", "agronomic", "", A6_RESIDUE_MANAGEMENT),
    SLMMeasure("A7", "Others", "agronomic"),
    SLMMeasure("V1", "Tree and shrub cover", "vegetative",
               "Agroforestry, windbreaks, afforestation, hedges, live fences"),
    SLMMeasure("V2", "Grasses and perennial herbaceous plants", "vegetative",
               "Grass strips along the contour, vegetation strips along riverbanks"),
    SLMMeasure("V3", "Clearing of vegetation", "vegetative",
               "Fire breaks, reduced fuel for forest fires"),
    SLMMeasure("V4", "Replacement or removal of alien/ invasive species", "vegetative",
               "Cutting of undesired trees and bushes"),
    SLMMeasure("V5", "Others", "vegetative", "Tree nurseries"),
    SLMMeasure("S1", "Terraces", "structural",
               "Bench terraces (slope of terrace bed <6%); forward-sloping terraces "
               "(slope of terrace bed >6%)"),
    SLMMeasure("S2", "Bunds, banks", "structural",
               "Earth bunds, stone bunds (along the contour or graded), "
               "semi-circular bunds (demi-lunes)"),
    SLMMeasure("S3", "Graded ditches, channels, waterways", "structural",
               "Diversion/ drainage ditch, waterways to drain and convey water"),
    SLMMeasure("S4", "Level ditches, pits", "structural",
               "Retention/ infiltration ditches, planting holes, micro-catchments"),
    SLMMeasure("S5", "Dams, pans, ponds", "structural",
               "Dams for flood control, dams for irrigation, sand dams"),
    SLMMeasure("S6", "Walls, barriers, palisades, fences", "structural",
               "Sand dune stabilization, rotational grazing (using fences), "
               "area closure, gully plugs (check dams)"),
    SLMMeasure("S7", "Water harvesting/ supply/ irrigation equipment", "structural",
               "Rooftop water harvesting, water intakes, pipes, tanks, etc."),
    SLMMeasure("S8", "Sanitation/ waste water structures", "structural",
               "Compost toilet, septic tanks, constructed treatment wetlands"),
    SLMMeasure("S9", "Shelters for plants and animals", "structural",
               "Greenhouses, stables, shelters for plant nurseries"),
    SLMMeasure("S10", "Energy saving measures", "structural",
               "Wood-saving stoves, insulation of buildings, renewable energy "
               "sources (solar, biogas, wind, hydropower)"),
    SLMMeasure("S11", "Others", "structural",
               "Compost production pits; reshaping of surface (slope reduction)"),
    SLMMeasure("M1", "Change in land use type", "management",
               "Area closure/ resting, protection, change from cropland to grazing "
               "land, from forest to agroforestry, afforestation"),
    SLMMeasure("M2", "Change in management/ intensity level", "management",
               "Change from grazing to cutting (stall feeding), from monocropping to "
               "rotational cropping, from continuous cropping to managed fallow, "
               "adjusting stocking rates, rotational grazing"),
    SLMMeasure("M3", "Layout according to natural and human environment", "management",
               "Exclusion of natural waterways and hazardous areas, separation of "
               "grazing types, distribution of water points, increase in landscape "
               "diversity"),
    SLMMeasure("M4", "Major change in timing of activities", "management",
               "Land preparation, planting, cutting of vegetation"),
    SLMMeasure("M5", "Control/ change in species composition", "management",
               "Reduction of invasive species, selective clearing, introduction of "
               "new species, controlled burning"),
    SLMMeasure("M6", "Waste management (recycling, re-use or reduce)", "management",
               "Both artificial and natural methods for waste management"),
    SLMMeasure("M7", "Others", "management"),
)


# ---------------------------------------------------------- §3.7 degradation
@dataclass(frozen=True)
class DegradationType:
    """One QT §3.7 land-degradation subcategory."""

    code: str
    label: str
    category: str
    category_label: str


#: QT §3.7 — six main types, keyed by their code letter.
DEGRADATION_CATEGORIES: dict[str, str] = {
    "W": "soil erosion by water",
    "E": "soil erosion by wind",
    "C": "chemical soil deterioration",
    "P": "physical soil deterioration",
    "B": "biological degradation",
    "H": "water degradation",
}

DEGRADATION_TYPES: tuple[DegradationType, ...] = tuple(
    DegradationType(code, label, code[0], DEGRADATION_CATEGORIES[code[0]])
    for code, label in (
        ("Wt", "Loss of topsoil/ surface erosion"),
        ("Wg", "Gully erosion/ gullying"),
        ("Wm", "Mass movements/ landslides"),
        ("Wr", "Riverbank erosion"),
        ("Wc", "Coastal erosion"),
        ("Wo", "Offsite degradation effects"),
        ("Et", "Loss of topsoil"),
        ("Ed", "Deflation and deposition"),
        ("Eo", "Offsite degradation effects"),
        ("Cn", "Fertility decline and reduced soil organic matter content "
               "(not caused by erosion)"),
        ("Ca", "Acidification"),
        ("Cp", "Soil pollution"),
        ("Cs", "Salinization/ alkalinization"),
        ("Pc", "Compaction"),
        ("Pk", "Slaking and crusting"),
        ("Pi", "Soil sealing"),
        ("Pw", "Waterlogging"),
        ("Ps", "Subsidence of organic soils, settling of soil"),
        ("Pu", "Loss of bio-productive function due to other activities"),
        ("Bc", "Reduction of vegetation cover"),
        ("Bh", "Loss of habitats"),
        ("Bq", "Quantity/ biomass decline"),
        ("Bf", "Detrimental effects of fires"),
        ("Bs", "Quality and species composition/ diversity decline"),
        ("Bl", "Loss of soil life"),
        ("Bp", "Increase in pests/ diseases, loss of predators"),
        ("Ha", "Aridification"),
        ("Hs", "Change in quantity of surface water"),
        ("Hg", "Change in groundwater/ aquifer level"),
        ("Hp", "Decline in surface water quality"),
        ("Hq", "Decline in groundwater quality"),
        ("Hw", "Reduction in the buffering capacity of wetland areas"),
    )
)


# ------------------------------------------------------- §5.1-5.3 context
#: QT §5.1-§5.3 context classes. The ``kind`` keys are the ``ContextClass``
#: node kinds used by the graph schema.
CONTEXT_CLASSES: dict[str, tuple[str, ...]] = {
    "rainfall_band": (
        "< 250 mm", "251-500 mm", "501-750 mm", "751-1,000 mm", "1,001-1,500 mm",
        "1,501-2,000 mm", "2,001-3,000 mm", "3,001-4,000 mm", "> 4,000 mm",
    ),
    "agroclimatic_zone": ("humid", "sub-humid", "semi-arid", "arid"),
    "slope_class": (
        "flat (0-2%)", "gentle (3-5%)", "moderate (6-10%)", "rolling (11-15%)",
        "hilly (16-30%)", "steep (31-60%)", "very steep (> 60%)",
    ),
    "landform": (
        "plateau/ plains", "ridges", "mountain slopes", "hill slopes",
        "footslopes", "valley floors",
    ),
    "altitude_zone": (
        "< 100 m a.s.l.", "101-500 m a.s.l.", "501-1,000 m a.s.l.",
        "1,001-1,500 m a.s.l.", "1,501-2,000 m a.s.l.", "2,001-2,500 m a.s.l.",
        "2,501-3,000 m a.s.l.", "3,001-4,000 m a.s.l.", "> 4,000 m a.s.l.",
    ),
    "soil_depth": (
        "very shallow (0-20 cm)", "shallow (21-50 cm)", "moderately deep (51-80 cm)",
        "deep (81-120 cm)", "very deep (> 120 cm)",
    ),
    "soil_texture": (
        "coarse/ light (sandy)", "medium (loamy, silty)", "fine/ heavy (clay)",
    ),
    "topsoil_om": ("high (> 3%)", "medium (1-3%)", "low (< 1%)"),
}

#: QT §5.1 agro-climatic zone definitions (length of growing period, days).
AGROCLIMATIC_ZONE_LGP: dict[str, str] = {
    "humid": "LGP > 270 days",
    "sub-humid": "LGP 180-269 days",
    "semi-arid": "LGP 75-179 days",
    "arid": "LGP < 74 days",
}

#: QT §3.4 water supply options.
WATER_SUPPLY: tuple[str, ...] = (
    "rainfed", "mixed rainfed-irrigated", "full irrigation", "post-flooding", "other",
)

#: QT §3.2 land use types: code -> label (main category in parentheses).
LAND_USE_TYPES: dict[str, str] = {
    "Ca": "Cropland: annual cropping",
    "Cp": "Cropland: perennial (non-woody) cropping",
    "Ct": "Cropland: tree and shrub cropping",
    "Co": "Cropland: other",
    "Ge": "Grazing land: extensive grazing",
    "Gi": "Grazing land: intensive grazing/ fodder production",
    "Go": "Grazing land: other",
    "Fn": "Forests/ woodlands: natural or semi-natural",
    "Fp": "Forests/ woodlands: plantations, afforestations",
    "Fo": "Forests/ woodlands: other",
    "Ss": "Settlements, buildings",
    "St": "Traffic lines: roads, railways",
    "Se": "Energy lines: pipelines, power lines",
    "So": "Other infrastructure",
    "Wd": "Drainage lines, waterways",
    "Wp": "Ponds, dams",
    "Ws": "Swamps, wetlands",
    "Wr": "Rivers and riparian zone",
    "Wl": "Lakes and lakeshore",
    "Wc": "Sea and seashores",
    "Wo": "Other waterways",
    "I": "Mines, extractive industries",
    "Io": "Mines, extractive industries: other",
    "U": "Unproductive land: wastelands, deserts, glaciers, etc.",
    "Uo": "Unproductive land: other",
}


# ----------------------------------------------------- §6.1 impact variables
@dataclass(frozen=True)
class ImpactVariable:
    """One QT §6.1 on-site impact variable.

    ``negative_pole`` / ``positive_pole`` are the row's printed end labels;
    the 7-point rating in :data:`IMPACT_RATING_SCALE` runs from the negative
    to the positive pole, so a "positive" rating always means movement
    towards ``positive_pole``.

    ``good_direction`` is ``"increase"`` or ``"decrease"`` and says which way
    the underlying quantity must move for the outcome to be beneficial. It is
    what :mod:`rag.graph.indicator_map` compares against the ML model's
    predicted effect direction.
    """

    name: str
    category: str
    subcategory: str
    negative_pole: str
    positive_pole: str
    good_direction: str
    source_note: str = ""


#: QT §6.1 rating scale, negative pole -> positive pole.
IMPACT_RATING_SCALE: tuple[str, ...] = (
    "very negative (-50-100%)",
    "negative (-20-50%)",
    "slightly negative (-5-20%)",
    "negligible impact",
    "slightly positive (+5-20%)",
    "positive (+20-50%)",
    "very positive (+50-100%)",
)

#: Short rating keys as the live database renders them, in the same order.
IMPACT_RATING_KEYS: tuple[str, ...] = (
    "very negative", "negative", "slightly negative", "negligible",
    "slightly positive", "positive", "very positive",
)

_INC, _DEC = "increase", "decrease"

ON_SITE_IMPACT_VARIABLES: tuple[ImpactVariable, ...] = (
    # --- socio-economic: production ---------------------------------------
    ImpactVariable("crop production", "socio-economic", "production",
                   "decreased", "increased", _INC),
    ImpactVariable("crop quality", "socio-economic", "production",
                   "decreased", "increased", _INC),
    ImpactVariable("fodder production", "socio-economic", "production",
                   "decreased", "increased", _INC),
    ImpactVariable("fodder quality", "socio-economic", "production",
                   "decreased", "increased", _INC),
    ImpactVariable("animal production", "socio-economic", "production",
                   "decreased", "increased", _INC),
    ImpactVariable("wood production", "socio-economic", "production",
                   "decreased", "increased", _INC),
    ImpactVariable("forest/ woodland quality", "socio-economic", "production",
                   "decreased", "increased", _INC),
    ImpactVariable("non-wood forest production", "socio-economic", "production",
                   "decreased", "increased", _INC),
    ImpactVariable("risk of production failure", "socio-economic", "production",
                   "increased", "decreased", _DEC),
    ImpactVariable("product diversity", "socio-economic", "production",
                   "decreased", "increased", _INC),
    ImpactVariable("production area", "socio-economic", "production",
                   "decreased", "increased", _INC),
    ImpactVariable("land management", "socio-economic", "production",
                   "hindered", "simplified", _INC),
    ImpactVariable("energy generation", "socio-economic", "production",
                   "decreased", "increased", _INC),
    # --- socio-economic: water availability and quality -------------------
    ImpactVariable("drinking water availability", "socio-economic",
                   "water availability and quality", "decreased", "increased", _INC),
    ImpactVariable("drinking water quality", "socio-economic",
                   "water availability and quality", "decreased", "increased", _INC),
    ImpactVariable("water availability for livestock", "socio-economic",
                   "water availability and quality", "decreased", "increased", _INC),
    ImpactVariable("water quality for livestock", "socio-economic",
                   "water availability and quality", "decreased", "increased", _INC),
    ImpactVariable("irrigation water availability", "socio-economic",
                   "water availability and quality", "decreased", "increased", _INC),
    ImpactVariable("irrigation water quality", "socio-economic",
                   "water availability and quality", "decreased", "increased", _INC),
    ImpactVariable("demand for irrigation water", "socio-economic",
                   "water availability and quality", "increased", "decreased", _DEC),
    # --- socio-economic: income and costs ---------------------------------
    ImpactVariable("expenses on agricultural inputs", "socio-economic",
                   "income and costs", "increased", "reduced", _DEC),
    ImpactVariable("farm income", "socio-economic", "income and costs",
                   "decreased", "increased", _INC),
    ImpactVariable("diversity of income sources", "socio-economic",
                   "income and costs", "decreased", "increased", _INC),
    ImpactVariable("economic disparities", "socio-economic", "income and costs",
                   "increased", "decreased", _DEC),
    ImpactVariable("workload", "socio-economic", "income and costs",
                   "increased", "decreased", _DEC),
    # --- socio-cultural ---------------------------------------------------
    ImpactVariable("food security/ self-sufficiency", "socio-cultural",
                   "socio-cultural", "reduced", "improved", _INC),
    ImpactVariable("health situation", "socio-cultural", "socio-cultural",
                   "worsened", "improved", _INC),
    ImpactVariable("land use/ water rights", "socio-cultural", "socio-cultural",
                   "worsened", "improved", _INC),
    ImpactVariable("cultural opportunities", "socio-cultural", "socio-cultural",
                   "reduced", "improved", _INC),
    ImpactVariable("recreational opportunities", "socio-cultural", "socio-cultural",
                   "reduced", "improved", _INC),
    ImpactVariable("community institutions", "socio-cultural", "socio-cultural",
                   "weakened", "strengthened", _INC),
    ImpactVariable("national institutions", "socio-cultural", "socio-cultural",
                   "weakened", "strengthened", _INC),
    ImpactVariable("SLM/ land degradation knowledge", "socio-cultural",
                   "socio-cultural", "reduced", "improved", _INC),
    ImpactVariable("conflict mitigation", "socio-cultural", "socio-cultural",
                   "worsened", "improved", _INC),
    ImpactVariable("situation of socially and economically disadvantaged groups",
                   "socio-cultural", "socio-cultural", "worsened", "improved", _INC),
    # --- ecological: water cycle/ runoff ----------------------------------
    ImpactVariable("water quantity", "ecological", "water cycle/ runoff",
                   "decreased", "increased", _INC),
    ImpactVariable("water quality", "ecological", "water cycle/ runoff",
                   "decreased", "increased", _INC),
    ImpactVariable("harvesting/ collection of water", "ecological",
                   "water cycle/ runoff", "reduced", "improved", _INC),
    ImpactVariable("surface runoff", "ecological", "water cycle/ runoff",
                   "increased", "decreased", _DEC),
    ImpactVariable("water drainage", "ecological", "water cycle/ runoff",
                   "reduced", "improved", _INC),
    ImpactVariable("groundwater table/ aquifer", "ecological",
                   "water cycle/ runoff", "lowered", "recharge", _INC),
    ImpactVariable("evaporation", "ecological", "water cycle/ runoff",
                   "increased", "decreased", _DEC),
    # --- ecological: soil -------------------------------------------------
    ImpactVariable("soil moisture", "ecological", "soil",
                   "decreased", "increased", _INC),
    ImpactVariable("soil cover", "ecological", "soil", "reduced", "improved", _INC),
    ImpactVariable("soil loss", "ecological", "soil",
                   "increased", "decreased", _DEC),
    ImpactVariable("soil accumulation", "ecological", "soil",
                   "decreased", "increased", _INC),
    ImpactVariable("soil crusting/ sealing", "ecological", "soil",
                   "increased", "reduced", _DEC),
    ImpactVariable("soil compaction", "ecological", "soil",
                   "increased", "reduced", _DEC),
    ImpactVariable("nutrient cycling/ recharge", "ecological", "soil",
                   "decreased", "increased", _INC),
    ImpactVariable("salinity", "ecological", "soil", "increased", "reduced", _DEC),
    ImpactVariable("soil organic matter/ below-ground C", "ecological", "soil",
                   "decreased", "increased", _INC),
    ImpactVariable("acidity", "ecological", "soil", "increased", "reduced", _DEC),
    # --- ecological: biodiversity -----------------------------------------
    ImpactVariable("vegetation cover", "ecological", "biodiversity",
                   "decreased", "increased", _INC),
    ImpactVariable("biomass/ above-ground C", "ecological", "biodiversity",
                   "decreased", "increased", _INC),
    ImpactVariable("plant diversity", "ecological", "biodiversity",
                   "decreased", "increased", _INC),
    ImpactVariable("invasive alien species", "ecological", "biodiversity",
                   "increased", "reduced", _DEC),
    ImpactVariable("animal diversity", "ecological", "biodiversity",
                   "decreased", "increased", _INC),
    ImpactVariable("beneficial species", "ecological", "biodiversity",
                   "decreased", "increased", _INC),
    ImpactVariable("harmful species", "ecological", "biodiversity",
                   "increased", "decreased", _DEC),
    ImpactVariable("habitat diversity", "ecological", "biodiversity",
                   "decreased", "increased", _INC),
    ImpactVariable(
        "pests/ diseases", "ecological", "biodiversity",
        "decreased", "increased", _DEC,
        source_note=(
            "QT §6.1 prints this row's poles as decreased (negative end) / "
            "increased (positive end), inverted relative to every other "
            "harmful-outcome row in the same table (cf. 'harmful species'). "
            "Poles are transcribed verbatim; good_direction follows the "
            "substantive meaning (fewer pests is better)."
        ),
    ),
    # --- ecological: climate and disaster risk reduction ------------------
    ImpactVariable("flood impacts", "ecological", "climate and disaster risk reduction",
                   "increased", "decreased", _DEC),
    ImpactVariable("landslides/ debris flows", "ecological",
                   "climate and disaster risk reduction", "increased", "decreased", _DEC),
    ImpactVariable("drought impacts", "ecological",
                   "climate and disaster risk reduction", "increased", "decreased", _DEC),
    ImpactVariable("impacts of cyclones, rain storms", "ecological",
                   "climate and disaster risk reduction", "increased", "decreased", _DEC),
    ImpactVariable("emission of carbon and greenhouse gases", "ecological",
                   "climate and disaster risk reduction", "increased", "reduced", _DEC),
    ImpactVariable("fire risk", "ecological", "climate and disaster risk reduction",
                   "increased", "reduced", _DEC),
    ImpactVariable("wind velocity", "ecological",
                   "climate and disaster risk reduction", "increased", "decreased", _DEC),
    ImpactVariable("micro-climate", "ecological",
                   "climate and disaster risk reduction", "worsened", "improved", _INC),
)


# ------------------------------------------------------ §6.4 / §6.5 classes
#: QT §6.4 — benefits compared with establishment and with maintenance costs,
#: each rated for short-term and long-term returns.
COST_BENEFIT_CLASSES: tuple[str, ...] = (
    "very negative", "negative", "slightly negative", "neutral/ balanced",
    "slightly positive", "positive", "very positive",
)
COST_BENEFIT_HORIZONS: dict[str, str] = {
    "short-term returns": "1-3 years",
    "long-term returns": "10 years",
}
COST_BENEFIT_COMPARISONS: tuple[str, ...] = (
    "benefits vs establishment costs",
    "benefits vs maintenance/ recurrent costs",
)

#: QT §6.5 — share of land users in the area who have adopted the Technology.
ADOPTION_CLASSES: tuple[str, ...] = (
    "single cases/ experimental", "1-10%", "10-50%", "more than 50%",
)
#: QT §6.5 — of those, the share who adopted without material incentives.
SPONTANEOUS_ADOPTION_CLASSES: tuple[str, ...] = (
    "0-10%", "10-50%", "50-90%", "90-100%",
)

#: The live database renders its own band labels (en-dashes, padded spaces,
#: and "11-50"/"91-100" where the QT writes "10-50"/"90-100"); these maps are
#: keyed by :func:`_band_key`, which removes all whitespace.
_ADOPTION_SYNONYMS: dict[str, str] = {
    "singlecases/experimental": "single cases/ experimental",
    "singlecases": "single cases/ experimental",
    "experimental": "single cases/ experimental",
    "1-10%": "1-10%",
    "10-50%": "10-50%",
    "11-50%": "10-50%",
    "morethan50%": "more than 50%",
    ">50%": "more than 50%",
    "51-100%": "more than 50%",
}
_SPONTANEOUS_SYNONYMS: dict[str, str] = {
    "0-10%": "0-10%",
    "10-50%": "10-50%",
    "11-50%": "10-50%",
    "50-90%": "50-90%",
    "51-90%": "50-90%",
    "90-100%": "90-100%",
    "91-100%": "90-100%",
}


def _key(value: str) -> str:
    """Lower-case, normalize dashes and non-breaking spaces, collapse runs."""
    text = str(value).strip().lower().replace("\xa0", " ")
    for dash in _DASHES:
        text = text.replace(dash, "-")
    return " ".join(text.split())


def _band_key(value: str) -> str:
    """Like :func:`_key` but with EVERY space removed.

    Percentage bands differ only in padding between the questionnaire
    ("1-10%") and the live database ("1 - 10 %"), so whitespace must not be
    part of the comparison.
    """
    return _key(value).replace(" ", "")


def normalize_adoption_band(value: str) -> str | None:
    """Map an adoption label (QT or live-database spelling) to a QT class."""
    return _ADOPTION_SYNONYMS.get(_band_key(value))


def normalize_spontaneous_band(value: str) -> str | None:
    """Map a spontaneous-adoption label to a QT class."""
    return _SPONTANEOUS_SYNONYMS.get(_band_key(value))


#: Live-database renderings of context classes that differ from the QT label,
#: as fingerprints (see :func:`_fingerprint`) -> QT label.
_CONTEXT_SYNONYMS: dict[str, dict[str, str]] = {
    # wocat.net renders the lowest altitude band as "0 - 100 m a.s.l."
    "altitude_zone": {"0-100": "< 100 m a.s.l."},
    # ... and the lowest rainfall band as "0 - 250 mm" on some records.
    "rainfall_band": {"0-250": "< 250 mm"},
}

_UNIT_SUFFIXES = ("mm", "cm", "masl")
_DASHES = "\u2010\u2011\u2012\u2013\u2014\u2212"


def _fingerprint(value: str) -> str:
    """Comparison key for a context label: digits, words and range dashes only.

    Absorbs the differences between the questionnaire's typography
    ("1,501-2,000 mm") and the live database's ("1 501 - 2 000 mm"):
    thousands separators, non-breaking spaces, en/em dashes and unit
    suffixes all disappear.

    >>> _fingerprint("1,501-2,000 mm") == _fingerprint("1 501 \u2013 2 000 mm")
    True
    """
    text = str(value).lower().replace("\xa0", " ")
    for dash in _DASHES:
        text = text.replace(dash, "-")
    text = "".join(ch for ch in text if ch.isalnum() or ch in "<>-")
    for suffix in _UNIT_SUFFIXES:
        if text.endswith(suffix):
            text = text[: -len(suffix)]
            break
    return text.strip("-")


_CONTEXT_INDEX: dict[str, dict[str, str]] = {
    kind: {_fingerprint(value): value for value in values}
    for kind, values in CONTEXT_CLASSES.items()
}


def normalize_context_value(kind: str, value: str) -> str | None:
    """Map a context label onto the canonical QT label for ``kind``.

    Returns ``None`` when the value is not a member of that vocabulary, so
    callers can reject rather than guess.

    >>> normalize_context_value("rainfall_band", "1 501 \u2013 2 000 mm")
    '1,501-2,000 mm'
    >>> normalize_context_value("agroclimatic_zone", "Sub-Humid")
    'sub-humid'
    >>> normalize_context_value("slope_class", "not a slope") is None
    True
    """
    index = _CONTEXT_INDEX.get(kind)
    if index is None:
        return None
    key = _fingerprint(value)
    return index.get(key) or _CONTEXT_SYNONYMS.get(kind, {}).get(key)


def normalize_slm_group(value: str) -> str | None:
    """Map an SLM group label onto its QT §3.5 spelling, or None."""
    key = _fingerprint(value)
    for group in SLM_GROUPS:
        if _fingerprint(group) == key:
            return group
    # the live database drops the parenthetical gloss on some group labels
    for group in SLM_GROUPS:
        head = group.split("(")[0]
        if _fingerprint(head) == key:
            return group
    return None


#: Live-database renderings of QT §6.1 variables that differ from the
#: questionnaire's own wording, as fingerprints -> QT name.
_IMPACT_SYNONYMS: dict[str, str] = {
    "excesswaterdrainage": "water drainage",
    "harvestingcollectionofwaterrunoffdewsnowetc": "harvesting/ collection of water",
}


def normalize_impact_name(value: str) -> str | None:
    """Map an impact-variable label onto its QT §6.1 name, or None."""
    key = _fingerprint(value)
    if key in _IMPACT_SYNONYMS:
        return _IMPACT_SYNONYMS[key]
    for name in IMPACT_BY_NAME:
        if _fingerprint(name) == key:
            return name
    # the live database writes "below ground C" where the QT writes "below-ground C"
    for name in IMPACT_BY_NAME:
        if _fingerprint(name.replace("-", " ")) == key:
            return name
    return None


def normalize_rating(value: str) -> str | None:
    """Map a rating label to one of :data:`IMPACT_RATING_KEYS`.

    Accepts the short keys the database renders ("slightly positive") and the
    full questionnaire labels ("slightly positive (+5-20%)").
    """
    key = _key(value)
    for rating in IMPACT_RATING_KEYS:
        if key == rating or key.startswith(rating + " "):
            return rating
    if key in ("negligible impact", "negligible"):
        return "negligible"
    return None


# ------------------------------------------------------------------ lookups
MEASURES_BY_CODE: dict[str, SLMMeasure] = {m.code: m for m in SLM_MEASURES}
DEGRADATION_BY_CODE: dict[str, DegradationType] = {
    d.code: d for d in DEGRADATION_TYPES
}
IMPACT_BY_NAME: dict[str, ImpactVariable] = {
    v.name: v for v in ON_SITE_IMPACT_VARIABLES
}


def measure(code: str) -> SLMMeasure:
    """Look up an SLM measure by code, e.g. ``"A2"``."""
    return MEASURES_BY_CODE[code]


def impact_variable(name: str) -> ImpactVariable:
    """Look up an on-site impact variable by its QT §6.1 name."""
    return IMPACT_BY_NAME[name]
