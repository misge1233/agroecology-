# E0/E1: Contracts, unified evidence store, taxonomies and registry (10 Nov 2026)

**Binding:**

- `docs/roadmap/AE+_enhancement_roadmap.md` (approved by the owner on 10 Nov 2026): sections 3, 5, 7, Appendix A and Appendix C;
- `docs/decisions/evidence_fusion.md` and CLAUDE.md §1 to §5;
- this brief.

**Purpose.** Build the one evidence store every later phase reads: ERA Ethiopia, the Adimassu compilation and Habtamu Sewnet's extraction database loaded into one frozen schema with provenance; the practice, outcome and challenge taxonomies with reviewable crosswalks; the parsed Agroecology+ Solutions Catalogue; and the data-driven registry of challenges and objectives for Ethiopia, served by one additive endpoint. No model training, no retrieval changes, no UI changes in this phase.

**Ground rules:**

- Production grade: Python 3.12, type hints, docstrings, logging, a CLI with `--dry-run` for every pipeline, tests for every module.
- **Additive only.** The current dataset files, `model/`, `app/backend/recommend.py`, the raster stack and the running app are untouched and keep working. Frozen names (`CSA_practices`, `practice_family`, `Study_No_`, `Indicator`, the 7 indicator strings, `csa_model.joblib`) stay exactly as they are; the new store uses new files and new column names (Appendix A).
- **Nothing is dropped silently.** Every row excluded by a loader is counted with its rule in the source's data card.
- **No automatic acceptance of a mapping.** Rules map; the LLM (optional, `--llm`) only proposes into review sheets; a human ticks. Nothing enters a frozen taxonomy without `accepted = yes` and a reviewer name.
- **Partner data stay out of git.** `data/raw/grist_habtamu/`, `data/raw/catalogue/`, the basin raster folders and `data/evidence/evidence_rows.*` are git-ignored (the first four already are; add the store). Taxonomies, aliases, review sheets, data cards, registry and tests are in git.
- Dependencies: pandas, numpy, pyarrow, pyyaml, python-docx (or pandoc through subprocess if already used), rapidfuzz for string similarity. Add them to `rag/requirements.txt` or a new `pipelines/requirements.txt`, pinned.
- Report as an **E1 block in `progress.md`** (Built, Files, Decisions, Verified, Needs local verification), then stop. The owner commits.

**Do not regress:** backend pytest (309 passed, 1 skipped on 1 Nov), frontend vitest and Playwright, `python model/evaluate.py --quick`, `python pipelines/dataset/build_practice_family.py --dataset ... --out /tmp/x.csv --no-sync-copies` (must still run).

---

## Part A: E0: contracts

**A1. Decision record.** `docs/decisions/enhancement_v2.md`: a one-page record of the roadmap decisions that bind the code: problem-based challenges derived from data; context is a vector (belt is an attribute); one evidence store with provenance; country as configuration; same inputs and same test for every method; geocoding with human check; partner data not redistributed. Link the roadmap. Add it to CLAUDE.md "Read first" list (one line) without changing the doctrine text.

**A2. Evidence schema module.** `pipelines/evidence/schema.py`:

- `EVIDENCE_COLUMNS`: an ordered mapping column → (dtype, nullable, allowed values) implementing roadmap Appendix A exactly, plus three optional columns added here: `hlpe_principle` (str or null), `mfl_domain` (str or null), `extra` (JSON string or null, for source fields with no home yet). `ctx_*` columns are not fixed in the schema; they are added by E3 and validated by prefix.
- `SCHEMA_VERSION = "1.0"`.
- `validate(df) -> ValidationReport` (counts per violation; raises on any error unless `strict=False`), checks: dtypes, enums (`source`, `loc_precision`, `loc_method`, `quality_flag`, `direction`), `row_id` uniqueness and pattern `<source>:<study_id>:<n>`, `lrr` equals `ln(mean_with / mean_without)` within 1e-9 wherever both means are positive, `var_lrr` null unless both SDs and Ns exist, `weight > 0`, `direction` consistent with the outcome taxonomy.
- `write_store(df, dir)`: `evidence_rows.parquet` (pyarrow, zstd) plus `evidence_rows.csv` mirror, and `store_manifest.json` (schema version, row counts per source, build time, git commit, input file hashes).
- `read_store(dir) -> DataFrame`.
- Tests: `pipelines/evidence/test_schema.py` on a synthetic frame (valid, each violation type, round trip).

**A3. Country configuration.** `countries/ET.yaml`:

```yaml
code: ET
name: Ethiopia
status: active
bbox: {lon_min: 32.9, lon_max: 48.2, lat_min: 3.3, lat_max: 14.9}
grid: data/lookups/grid_definition.json
aez:
  anchor_raster: geodata/layers/aez_belt.tif
  lookup: data/lookups/aez_belt_lookup.csv
  attributes: data/lookups/aez_attributes.csv
languages: [en, am, om]
evidence_sources: [ERA, CSA, HAB]
knowledge_sources: [catalogue, guidelines, gardian, era_papers]
exposure:
  min_rows: 30
  min_studies: 5
  min_docs: 3
overlays:
  omo_gibe:
    status: planned
    rasters: {hotspot_coldspot: data/raw/hotspot and coldspot/, typology: data/raw/Typology/}
contact: Alliance of Bioversity International and CIAT, Addis Ababa
```

plus `countries/KE.yaml` with `status: draft` and empty sources, `countries/README.md`, and `pipelines/common/country_config.py` with `load_country(code) -> CountryConfig` (dataclass, validated: bbox order, files exist when `status: active`), tested.

**A4. Taxonomy folder.** `data/taxonomy/README.md` describing the files of Part C, their columns and the review protocol (rules → proposal → human tick → frozen id; ids are never reused or renamed).

**A5. gitignore.** Add `data/evidence/evidence_rows.parquet`, `data/evidence/evidence_rows.csv` and `data/taxonomy/review/llm_cache.jsonl`.

---

## Part B: E1: loaders and the store

All loaders live in `pipelines/evidence/`, share `common.py` (numeric parsing, id helpers, LRR and variance, logging) and write through `schema.write_store`. Each produces a `DataFrame` in the schema and a data card `data/evidence/cards/<source>.md` (rows read, rows kept, rows dropped per rule with counts, coverage of key fields, licence and provenance notes).

**B1. `load_era.py`: all of ERA, not only the 7 indicators.** Input `data/raw/ERA_Ethiopia_dataset.csv` (14,792 rows, 137 columns, 306 studies, 101 `PrName` values, 59 `Outcode` values).

- `source = ERA`; `study_id = "ERA_" + Code` (identical to the existing `Study_No_`); `doi`, `citation` from Author, Date, Journal; `year` from Date.
- Location: Latitude and the longitude column (check its exact name), `Site.ID` as `site_name`, `loc_precision = site` when both coordinates exist, `loc_method = reported`.
- Practice: `practice_raw = PrName` (the frozen ERA label used today), keep `SubPrName`, the ERA practice codes `T1..T14` and `Tree` in `extra`; `comparator = C.Descrip`.
- Outcome: `outcome_raw = Partial.Outcome.Name when present else the ERA outcome name for Outcode`, with `Outcode` kept in `extra`; `outcome_id` through the outcome taxonomy (Part C). Rows whose `Outcode` is not yet in the taxonomy are **kept** with `outcome_id = null` and counted; they are not dropped.
- Numbers: `mean_with = MeanT`, `mean_without = MeanC`; `MeanT.Error`, `MeanC.Error` with `Mean.Error.Type` (SD, SE, CI or other) into `sd_*` or `se_*` (convert SE to SD with `Rep` where the type is SE; leave CI in `extra`); `n_with = n_without = Rep`; `Upper`, `Lower` in `extra`.
- `crop = Product`, `crop_group` through the existing `Crop_group` rule (reuse the function in `pipelines/dataset/`, wrap never fork); `duration_years = Duration`.
- Reported context: `ctx_reported_rain_mm = MAP`, `ctx_reported_altitude_m = Elevation`, soil texture and pH in the `ctx_reported_soil` field, `Mean.Annual.Precip` kept in `extra`.
- Sign convention: `lrr` is always `ln(mean_with / mean_without)`; direction comes from the outcome taxonomy, never from a flipped mean (`MeanFlip` goes to `extra` and the data card explains it).
- **Reconciliation test (mandatory):** applying the existing scope filter (the 7 indicators) and the existing drop rules from `docs/reports/ERA_preprocessing_report.md` to the loaded frame must reproduce the 7,250 ERA rows of `data/processed/CSA_ERA_final_model_ready.csv`: same `(study_id, practice_raw, Indicator, crop)` multiset and `lrr` equal within 1e-9. Report the result in the data card; if a residual difference exists, explain each case rather than forcing the match.

**B2. `load_csa.py`.** Input `data/raw/CSA_practices_by_Agroecology.xlsx` (Sheet1, columns `Study_No_, Reference, CSA_practi, CSA_catago, duration_o, Scale, study_site, Latitude, Longitude, Region, Rainfall, Altitude_r, Slope____, Soil_type, Crop_type, CSA_Pilar, Indicator, With, without, unit, Agro_zone`).

- `source = CSA`; `study_id = "CSA_" + Study_No_`; `citation` from `data/processed/csa_study_references.json` (`build_csa_references.py` logic, wrap never fork); `doi` where that file has one.
- `practice_raw = CSA_practi` (the frozen label), `CSA_catago` and `CSA_Pilar` in `extra`; `outcome_raw = Indicator`; `mean_with = With`, `mean_without = without`; no dispersion (null); `n_*` null; `weight` from the quality default.
- Location from Latitude and Longitude, `site_name = study_site`, `loc_precision = site`; `ctx_reported_*` from Rainfall, Altitude_r, Slope____, Soil_type, Agro_zone.
- Reconciliation test: the 1,414 CSA rows of the current dataset are reproduced exactly as in B1.

**B3. `load_habtamu.py`.** Input `data/raw/grist_habtamu/@HabtamuSewnet-MasterData.csv` (1,617 rows, 47 columns; the `.grist` file is the archival original and may be opened read-only with `sqlite3` as a cross-check that row counts agree).

- `source = HAB`; `study_id = "HAB_" + slug(Study_ID)`; `doi` normalised (strip `https://doi.org/`, lower-case; keep non-DOI identifiers such as `IJPSS.2014.8.004` in `extra` with `doi = null`); `citation = Study_ID`; `year` parsed from `Study_period` or the Study_ID suffix when it is a 4-digit year.
- Numeric parsing (`common.parse_number`): accepts plain numbers, thousands separators, `~`, `±` (keep the first number), `NR`, `NA`, empty → null; **ranges written as `a–b` or `a-b` or `a to b` → null for the means** (a range is not a mean) but → midpoint for `ctx_reported_*` with the range kept in `extra`; units stripped and recorded in `unit`. Every parsing decision is a counted rule in the data card.
- `mean_with = Mean_with`, `mean_without = Mean_without`, `sd_*`, `se_*`, `n_*` as given; `var_lrr` by the delta method when both SDs and Ns exist; `p-value`, `t-value`, `F-value`, `x2-value`, `correlation-r`, `R²`, CI and CV columns in `extra`.
- `practice_raw = Intervention_type`, `comparator = Comparator_description`, `duration_years` parsed from `Intervention_duration` (seasons → years at 0.5, ranges → midpoint); `crop` from `Cropping_system` when it names a crop.
- `outcome_raw = Outcome_name`, `Outcome_type(domain)` in `extra`; `hlpe_principle`, `mfl_domain` as given (normalise case and separators: `Recycling; Soil health`).
- `quality_flag` from `Quality_score` (High, Medium, Medium-High and Moderate-High → Medium, Moderate → Medium, NR → NR); `study_design`, `replication`, `scale` as given.
- Location: `lat = lon = null`, `loc_precision = country` (or `site` when `Agroecological_Zone` or `Supporting Evidence` names a site; still null coordinates), `loc_method = none`, `site_name = Agroecological_Zone`; `country` to ISO alpha-2 through a small lookup with an unmapped list in the data card (handle `Europe; North America` style multi-values by keeping the first and flagging).
- `ctx_reported_rain_mm`, `ctx_reported_altitude_m`, `ctx_reported_soil`, `ctx_reported_aez` from Precipitation, Altitude, Soil, Agroecological_Zone (and Köppen in `extra`).
- `evidence_text = Supporting Evidence`, `extraction_locator = Extraction Source (Location in PDF)`.
- Expected (from the 10 Nov profile; report the actual): 1,312 rows with a computable `lrr`, 646 with `var_lrr`, 158 Ethiopian rows (129 with `lrr`).

**B4. `build_evidence_store.py`.** Runs the three loaders (each also runnable alone), applies the taxonomies (Part C) to fill `practice_id`, `practice_family`, `practice_components`, `outcome_id`, `direction`, concatenates, computes `lrr`, `var_lrr`, `weight` (inverse variance when available, else a documented default per quality flag), validates, writes the store, the cards, `data/evidence/README.md` (what the store is, how to rebuild, what each card says) and a one-screen summary: rows per source, per country, per family, per objective group, share with coordinates, share with variance.

---

## Part C: Taxonomies and crosswalks

Files under `data/taxonomy/` (CSV, UTF-8, LF, header row; ids are upper snake case and permanent).

**C1. Practices.** `practices.csv`: `practice_id, name_en, practice_family (one of the frozen 5), components (semicolon list, from rag/graph/practice_components.py), era_codes (semicolon list), catalogue_ids, wocat_group, wocat_measure, status (seed|reviewed|frozen), notes`. `practice_aliases.csv`: `alias, source (CSA|ERA|HAB|CAT|WOCAT), practice_id, method (exact|normalised|component|era_code|catalogue|llm|manual), confidence, accepted (yes|no|), reviewer, date`.

Seeding rules, in order: (1) the 100 frozen `CSA_practices` labels each become a canonical practice (id from the label, family from `build_practice_family.classify`, components from the component layer); (2) ERA `PrName` values and `T1..T14` codes map to those practices where the label is identical, otherwise become new canonical practices; (3) catalogue names (C5) map by normalised match and component match, otherwise new; (4) Habtamu `Intervention_type` (458 values) map by rules; the rest go to the review sheet. Merging two seeded practices into one is **proposed** in `review/practice_merges.csv`, never applied in this phase.

**C2. Outcomes.** `outcomes.csv`: `outcome_id, name_en, direction (+1|-1), unit_class (yield|mass|fraction|concentration|money|count|rate|index|other), objective_group (productivity|soil_health|water|economics|resilience_biodiversity|livestock|other), legacy_indicator (one of the 7 frozen strings or empty), status, notes`. `outcome_aliases.csv` as for practices. Seeds: the 7 indicators (with `recommend.DIRECTION`); the 59 ERA `Outcode` values with their ERA names and a proposed direction; Habtamu `Outcome_name` (841) and `Outcome_type(domain)` by rules (normalised match, keyword rules such as `soil organic carbon|soc|som` → SOIL_ORGANIC_CARBON), rest to review. Direction for a new outcome is proposed and must be reviewed; until accepted the row's `direction` is null and the row is excluded from any ranking use (a column `direction_reviewed` in the store makes that explicit).

**C3. Challenges.** `challenges.csv`: `challenge_id, name_en, description_en, objective_groups (semicolon), practice_families (semicolon), catalogue_problem_terms (semicolon), status`. Seed list: SOIL_EROSION, GULLY_EROSION, SOIL_FERTILITY_DECLINE, MOISTURE_STRESS_DROUGHT, WATERLOGGING_EXCESS_RUNOFF, LOW_CROP_PRODUCTIVITY, FEED_SHORTAGE, PESTS_AND_DISEASES, DEFORESTATION_FUELWOOD, DEGRADED_HILLSIDES, LOW_INCOME_MARKET_ACCESS, SOIL_ACIDITY (lime brochure, acidic soils), WATER_SCARCITY_IRRIGATION. Each links to the outcome groups that measure it and the practice families and catalogue categories that address it; `catalogue_problem_terms` are the normalised "key problems to be addressed" phrases from C5 so the link from catalogue entry to challenge is data, not code.

**C4. `pipelines/taxonomy/propose_mappings.py`.** For a given source and target taxonomy: normalise (case, punctuation, units, plural, known synonyms), exact and token matches, component matches (practices), ERA-code matches, keyword rules (outcomes); unmatched → `data/taxonomy/review/<source>_<taxonomy>_review.csv` with the raw label, its row count, the top-3 candidates by `rapidfuzz` token-set ratio and empty `accepted, practice_id/outcome_id, reviewer, date` columns. `--llm` (optional, needs `OPENAI_API_KEY` from `app/backend/.env`, reuse the backend's OpenAI client): one constrained call per unmatched label listing the candidate ids and "NEW", JSON output, cached in `review/llm_cache.jsonl`; the proposal fills a `llm_suggestion` column only. `--apply-review` ingests accepted rows into the alias files. Print coverage per source (share of rows with a mapped id). Targets for this phase: ERA and CSA 100% by rules; catalogue 100% (30 entries, rules plus a manual list in the brief's spirit); Habtamu at least 60% of rows by rules, remainder in review.

**C5. Catalogue parser.** `pipelines/evidence/parse_catalogue.py`: reads `data/raw/catalogue/Catalogue 1-30 for dashboard testing.docx` (python-docx; the file is never modified) and writes `data/taxonomy/catalogue_entries.json` and `.csv` with: `catalogue_id (CAT_01..CAT_30), number, name, category, target_farming_system, suitable_land_use_and_agroecology, scaling_stage, scale, description, key_problems (list), principles (list), benefits (list), evidence_base (list), limitations, photo_captions (list), source_file, extracted_on`. Headings vary ("Solution name:", "Solution Name", bare numbered titles, a run of XML in one paragraph); parse by the numbered pattern and the field labels, and assert 30 entries with name and category. Photos are not extracted (captions only). Normalised `key_problems` feed C3.

---

## Part D: Registry and endpoint

**D1. `pipelines/evidence/build_registry.py --country ET`** → `data/evidence/registry_ET.json`:

```json
{"country": "ET", "built_at": "...", "store_manifest": "...", "thresholds": {...},
 "challenges": [{"id": "SOIL_EROSION", "name_en": "...", "objective_groups": [...],
   "objectives": [{"id": "SOIL_LOSS", "name_en": "...", "direction": -1, "n_rows": 296, "n_studies": 21, "n_practices": 17, "exposed": true}],
   "n_rows": ..., "n_studies": ..., "n_documented_practices": ..., "exposed": true, "exposure_reason": "rows>=30 and studies>=5"}],
 "practices": [{"id": "...", "name_en": "...", "family": "...", "challenges": [...], "n_rows": ..., "catalogue_ids": [...]}]}
```

Counts use only rows with `country = ET` and a reviewed direction; `exposed` follows `countries/ET.yaml` thresholds; items below threshold carry `"exposed": false, "documented_only": true` when the catalogue or guidelines document at least `min_docs` practices for them (for this phase the catalogue only; guidelines arrive in E2).

**D2. Backend endpoint (additive).** `GET /registry?country=ET` in a new router `app/backend/app/routers/registry.py` with a service that loads and caches the JSON (404 for an unknown country, 503 with a clear message when the file is missing: fail fast, degrade gracefully). Pydantic schemas in `schemas.py`; one test in `tests/test_registry.py` using a fixture registry. No change to existing endpoints or to the frontend.

---

## Part E: Tests, documentation, report

- Unit tests with synthetic fixtures for: schema, `common.parse_number` (table of the awkward strings seen in the Habtamu file: `700–900 mm yr⁻¹`, `~800`, `1,204`, `NR`, `12 ± 3`, `0–34 years`), each loader (5 to 10 fixture rows each), the catalogue parser (a 2-entry fixture docx built in the test), `propose_mappings` (rules), `build_registry` (thresholds), `country_config`.
- Data-dependent tests marked `@pytest.mark.data` (skipped when the raw files are absent): the two reconciliation tests of B1 and B2, the Habtamu row counts, catalogue = 30 entries.
- Documentation: `data/evidence/README.md`, `data/taxonomy/README.md`, `countries/README.md`, `docs/decisions/enhancement_v2.md`; one paragraph in the repo README's layout table for `countries/`, `data/evidence/`, `data/taxonomy/`, `pipelines/evidence/`, `pipelines/taxonomy/`.
- `progress.md` E1 block: Built, Files, Decisions (every judgement call: parsing rules, drop rules, seeding choices, default weights), Verified (commands and counts: rows per source, reconciliation result, mapping coverage per source, registry exposure table), Needs local verification (the review sheets for Habtamu and the owner).

## Acceptance

1. `python pipelines/evidence/build_evidence_store.py` runs end to end on the owner's machine and writes the store, three data cards and the README; `schema.validate` passes with zero errors.
2. Reconciliation: 7,250 ERA rows and 1,414 CSA rows reproduced exactly (or every residual explained in the card).
3. Habtamu loaded with the counts reported; no silent drops; the `.grist` cross-check agrees on 1,617 rows.
4. Taxonomies seeded; coverage: ERA 100%, CSA 100%, catalogue 100%, Habtamu ≥ 60% by rules; review sheets written for the rest with top-3 candidates; nothing accepted automatically.
5. Catalogue parsed: 30 entries with all fields, `key_problems` normalised.
6. `registry_ET.json` built; `GET /registry?country=ET` serves it; the exposure table is in the report.
7. All new tests pass; the existing backend, frontend and model smoke tests still pass; nothing committed.
