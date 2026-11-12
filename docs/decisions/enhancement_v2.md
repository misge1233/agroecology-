# Decision record: enhancement v2 (E0, 10 November 2026)

**Status:** binding for phases E0 to E10. **Source:** `docs/roadmap/AE+_enhancement_roadmap.md`
(approved by the owner on 10 November 2026; sections 3, 5, 7, Appendix A and Appendix C).
This page lists only the decisions that bind the code. CLAUDE.md doctrine (every number has a
source, cite or stay silent, wrap never fork, frozen schema names, fail fast and degrade
gracefully) and `docs/decisions/evidence_fusion.md` are unchanged.

## 1. Challenges are problems, derived from data

The entry point is the user's problem (soil erosion, gully erosion, moisture stress...), not a
practice family. Challenges live in `data/taxonomy/challenges.csv`; each links to the objective
groups and outcomes that measure it, the practice families that address it and the catalogue
"key problems" terms that document it. A challenge or objective is shown for a country only when
the evidence store holds at least `min_rows` rows across `min_studies` studies, or the knowledge
layer documents at least `min_docs` practices ("documented only" below that). Thresholds live in
`countries/<cc>.yaml`. The registry (`data/evidence/registry_<cc>.json`, `GET /registry`) is built
from the store, never written by hand.

## 2. Context is a vector; the belt is one attribute

Suitability and effect estimates are functions of the context vector (climate, terrain, soil,
land cover, ...). Classes (AEZ belt, Köppen, typology) are attributes shown to the user and
available to models, never the join key, the candidate filter or the grouping of explanations.

## 3. One evidence store with provenance

All field evidence (ERA, the Adimassu compilation, Habtamu's database, WOCAT and future country
data) is loaded into one frozen schema (`pipelines/evidence/schema.py`, version 1.0, roadmap
Appendix A): one row per with/without contrast with `source`, `study_id`, `doi`,
`extraction_locator`, `evidence_text`, location precision and method, and a quality flag as
reported by the source. No engine reads a raw file. Loaders keep every source row and count every
rule in a data card. `lrr` is always `ln(mean_with / mean_without)`; direction comes from the
outcome taxonomy and is used only once a human has reviewed it. Taxonomy mappings are proposed by
rules (and optionally an LLM) and accepted only by a named reviewer.

## 4. Country is configuration

Nothing in pipelines, models or UI hard-codes Ethiopia: `countries/ET.yaml` does (bounding box,
grid, AEZ anchor and lookups, languages, evidence and knowledge sources, exposure thresholds,
overlays, contact). Replicating to another country means a configuration file, a national AEZ
product, national datasets and translations (`countries/KE.yaml` is the draft dry run).

## 5. Same inputs and same test for every method

Methodology 1 (evidence model plus RAG), Methodology 2 (LLM evidence reasoning) and their hybrid
are compared only on the protocol of roadmap section 11: identical inputs, study-grouped and
spatial hold-out, masked retrieval, the metrics of Appendix B computed by one implementation. No
method sees held-out studies through any channel (dataset, index, graph or prompt).

## 6. Geocoding with a human check

Rows without coordinates (Habtamu's database) are geocoded from the paper text and a gazetteer
with `loc_method = geocoded_llm_unchecked`; they are excluded from training until a reviewer
checks them (all Ethiopian studies, a 20% sample of the rest), then `geocoded_llm_checked`.

## 7. Partner data are not redistributed

Habtamu's database, the catalogue docx, the Omo-Gibe rasters and the evidence rows built from
them stay out of git (`.gitignore`) and out of any public artifact. Taxonomies, aliases, review
sheets, data cards, the registry, code and tests are in git. Sending partner text to an external
API (the optional `--llm` mapping proposal) is the owner's decision per run.


## Addendum, 12 Nov 2026: evidence cards sent to the OpenAI API (E6, Methodology 2)

The owner decided, after confirming with the data holder, that the evidence cards of
Methodology 2 may be sent to the OpenAI API **from all sources, including Habtamu's database**
(decision 7 above: sending partner text to an external API is the owner's decision; this is
that decision for E6). What is sent per query: the query context in words and numbers, the
objective, the crop, the candidate practice names, and up to 32 evidence cards (one pooled
effect per study cell with its site context, country, year, quality flag, short citation and
DOI), up to 4 retrieved passages trimmed to 120 tokens, and graph facts from the catalogue.
No partner file is sent whole. Models: `gpt-4o-mini` for every variant and one stronger model
for the full variant, run only after the owner's go on the printed estimate; budget cap 100 USD
for the phase. The model never produces a number shown to anyone: estimates are computed by
code from the cited cards. Recorded also in `model/m2/model_card.md`.

**Owner decision, 12 Nov 2026 (model scope).** Methodology 2 is evaluated with deployable,
low-cost models only: `gpt-4o-mini` (all four variants) and `gpt-4.1-mini` as the stronger model
(`m2_zero` and `m2_graph`, the reviewer's addition to test whether the evidence effect holds with
a stronger model). Frontier models (`gpt-4.1`, `o3`, `gpt-5` class) are out of scope for cost.
