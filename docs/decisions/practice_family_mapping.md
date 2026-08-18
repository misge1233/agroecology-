# Practice → practice_family crosswalk

`practice_family` groups every practice into the **five expert categories** defined in the
AICCRA / Adimassu et al. CSA paper (the 25 experts were grouped into these five themes):

The `practice_family` values are stored as the **full category names** (not abbreviations):

| Abbrev (internal) | practice_family value (stored) |
|---|---|
| CPM | Crop production and management |
| LPM | Livestock production and management |
| ISFM | Integrated soil fertility management |
| ECWM | Erosion control and water management |
| FAF | Agro-forestry and forest management |

The paper explicitly notes practices can span categories ("thematic areas have no distinct
boundaries"); each practice is therefore assigned to the single **best-fit** family, with the
rules below. Source of truth: the paper's Tables 2–10 and Appendices 1–9 category listings.

## CSA-source practices (20 CSA_catago categories) — explicit assignment

| CSA_practices | practice_family | Basis |
|---|---|---|
| Physical SWC measures | ECWM | SWC structures |
| Physical + biological SWC practices | ECWM | SWC |
| Biological SWC practices | ECWM | SWC |
| agronomic/biological SWCP | ECWM | SWC |
| In-situ water harvesting | ECWM | water management |
| Deficit irrigation | ECWM | irrigation |
| furrow irrigation | ECWM | irrigation |
| furrow irrigation_alternate | ECWM | irrigation |
| drip irrigation | ECWM | irrigation |
| overhead irrigation with mulching | ECWM | irrigation |
| IWM | ECWM | integrated water/watershed management |
| ISFM | ISFM | soil fertility |
| organic amedements | ISFM | organic soil amendments |
| Animal feed management | LPM | livestock feeding |
| grazing management | LPM | livestock/rangeland management |
| Exclosure | FAF | area exclosure / restoration (paper lists exclosure under FAF) |
| Intercropping | CPM | cropping system |
| Conservation tillage | CPM | tillage / crop management (paper: minimum/zero tillage under CPM) |
| weeding | CPM | weed management |
| Drought tolerrant crops | CPM | variety choice |

## ERA-source practices (81, incl. combined "A-B-C") — keyword + priority

ERA names are tokenised and matched to category keyword sets. When a combined practice
matches several categories (the paper's acknowledged overlap), it is resolved to ONE family
by priority: **FAF > LPM > ISFM > ECWM > CPM** — distinctive whole-system practices first,
then the dominant ERA soil-fertility theme (ISFM), then water/erosion (ECWM), with crop
management (CPM) as the base default.

Keyword themes:
- **FAF:** agroforestry, parkland, multistrata, alley crop, afforestation/reforestation,
  exclosure, silvopasture, prosopis, woodlot, natural regeneration, pruning, tree/shrub.
- **LPM:** feed, forage, fodder, grazing, livestock, animal, breed, supplement, silage,
  dairy, pasture, herd.
- **ISFM:** fertilizer (inorganic/organic), biochar, compost/vermicompost, manure, lime,
  gypsum, pH control, nutrient, bio-fertiliser, bioslurry, green manure, residue
  incorporation, microdose, amendment, inoculant.
- **ECWM:** irrigation (all types), water harvesting, bund, terrace, fanya juu, tied ridge,
  mulch, runoff, check dam, shallow well, water storage, spate, drip, furrow, sprinkler,
  deficit, grass strip, trench, waterway, sub-soiler, moisture, broad-bed (BBF/BBM), pond,
  diversion, contour, percolation.
- **CPM:** variety/cultivar, intercrop, rotation, tillage (minimum/zero/reduced), weed, pest,
  IPM, planting date, sowing, seed, cover crop, fallow, drought-tolerant, conservation
  agriculture, advisory, insurance, diversification, residue, relay, push-pull, striga.

Worked examples:
- `Inorganic Fertilizer` → ISFM; `Improved Varieties` → CPM; `Water Harvesting` → ECWM;
  `Parklands` → FAF; `Feed Addition` → LPM.
- `Inorganic Fertilizer-Water Harvesting` → **ISFM** (fertilizer beats water).
- `Improved Varieties-Supplemental Irrigation` → **ECWM** (irrigation beats crop mgmt).
- `Agroforestry Pruning-Inorganic Fertilizer` → **FAF** (agroforestry beats fertilizer).
- `Mulch-Reduced Tillage` → **ECWM** (mulch beats tillage/CPM).

## Overlaps flagged by the paper (assigned to best-fit here)

Exclosure (FAF/ECWM/LPM → FAF), Silvo-pastoral (LPM/FAF → LPM via feed, or FAF via
agroforestry keyword → FAF by priority), Alley cropping (FAF/ECWM → FAF), Conservation
agriculture (CPM/ECWM), Tied-ridge (ECWM/ISFM → ISFM if "+4R" else ECWM), Intercropping
(CPM/ISFM/ECWM → CPM), Mulch/residue (ECWM/ISFM/CPM), Liming & green manure (CPM/ISFM → ISFM).

## Notes
- Assignments follow the paper wherever it lists a practice; ambiguous combined ERA practices
  use the documented priority rule (recorded here for transparency).
- `practice_family` is the harmonised feature that lets the recommender compare practices
  across both data sources on equal footing; original `CSA_practices` is retained for traceability.
