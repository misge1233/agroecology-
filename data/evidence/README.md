# data/evidence: the unified evidence store

One table of with/without contrasts from every field-evidence source, in one
frozen schema with provenance (schema version 1.1, roadmap
Appendix A; `pipelines/evidence/schema.py`). Every later phase reads this store;
no engine reads a raw file.

| File | In git | What it is |
|---|---|---|
| `evidence_rows.parquet` | no (partner data) | the store (pyarrow, zstd) |
| `evidence_rows.csv` | no (partner data) | CSV mirror for inspection |
| `store_manifest.json` | yes | schema version, rows per source, build time, git commit, SHA-256 of every input, weight parameters, validation report, reconciliation results |
| `cards/ERA.md`, `cards/CSA.md`, `cards/HAB.md` | yes | one data card per source |
| `registry_ET.json` | yes | challenges and objectives for Ethiopia with exposure flags (`build_registry.py`) |
| `review/geocoding_review.csv`, `.html` | yes | E2: one row per Habtamu study (site, coordinates, precision, method, confidence, quote) and a Leaflet map for the reviewer |
| `review/habtamu_papers_missing.csv` | yes | E2: Habtamu papers with a DOI but no open-access full text (landing URL for the owner) |
| `hab_geocoding.csv` | yes | E2: geocoding applied to the store (`geocode_sites.py --apply-geocoding`) |

Last build: 2026-11-10T17:46:44+00:00 (commit `c51e191e46d3791d39ae4f6ad09a8ec533854a3b`):
CSA 3,344, ERA 14,792, HAB 1,617 rows.

```
Evidence store: 19,753 rows, 1,104 studies, schema 1.1
  per source: ERA 14,792, CSA 3,344, HAB 1,617
  per country: ET 18,294, CN 143, IT 142, ES 140, US 100, IN 86, FR 63, KE 60, +45 more
  per family: Integrated soil fertility management 8,724, Erosion control and water management 4,418, Crop production and management 3,860, Livestock production and management 1,417, Agro-forestry and forest management 1,230, (unmapped) 104
  per objective group: productivity 10,324, economics 2,871, water 2,680, soil_health 1,677, livestock 1,236, other 415, resilience_biodiversity 374, climate 110, (unmapped) 66
  with coordinates: 93.8%   with var_lrr: 18.2%   with lrr: 92.6%   reviewed direction: 97.3%
```

## Rebuild

```bash
python -m pip install -r pipelines/requirements.txt        # once, in the backend venv
python pipelines/evidence/crop_lookup.py                   # only if data/taxonomy/crop_harmonisation.csv is missing
python pipelines/evidence/parse_catalogue.py               # catalogue docx -> data/taxonomy/catalogue_entries.*
python pipelines/evidence/build_evidence_store.py          # loaders + taxonomy rules + store + cards + this README
python pipelines/evidence/build_registry.py --country ET   # registry_ET.json (prints the change against the file on disk)
# E2: reviews, geocoding
python pipelines/taxonomy/propose_mappings.py --apply-outcome-review   # accepted rows of review/outcomes_direction_review.csv
python pipelines/taxonomy/propose_mappings.py --apply-review           # accepted Habtamu sheet rows and practice merges
python pipelines/evidence/fetch_habtamu_papers.py --email you@example.org
python pipelines/evidence/geocode_sites.py --llm                       # review sheet + map
python pipelines/evidence/geocode_sites.py --apply-geocoding           # writes hab_geocoding.csv, rebuilds store and registry
python -m pytest pipelines -q                              # unit tests (+ data tests when the raw files exist)
```

Every script takes `--dry-run` (compute and report, write nothing).

## Rules that matter when reading the store

- **Row** = one with/without contrast. `row_id = <source>:<study_id>:<n>`.
- **`lrr`** is always `ln(mean_with / mean_without)` when both means are positive, else null;
  a mean is never flipped. **`direction`** comes from the outcome taxonomy and is null
  (`direction_reviewed = false`) until a human has reviewed the outcome; such rows are
  excluded from any ranking use. Only the 7 legacy indicators are reviewed today
  (their direction is `recommend.DIRECTION`).
- **`var_lrr`** is the delta-method variance, only when both SDs and both Ns exist.
- **`weight`** = inverse variance (capped at the 99th percentile) or a default of
  `factor(quality_flag) x median inverse variance` (factors in the manifest).
- **Nothing is dropped**: the loaders keep every source row. Rows that the legacy model
  excluded (other outcomes, non-positive means, ratios above 20, duplicates) are in the store;
  exact repeats carry `extra.dup_of`. The legacy rules are applied only by the
  reconciliation (`pipelines/evidence/reconcile.py`), which reproduces the 7,250 ERA and
  1,414 CSA rows of `data/processed/CSA_ERA_final_model_ready.csv`.
- **Schema 1.1 (E2)**: the taxonomy gains the `climate` objective group and the outcome statuses
  `excluded`, `context_dependent` and `merged`; their rows keep their `outcome_id` but carry
  `direction = null` and never count.
- **Location (E2)**: Habtamu rows geocoded from the papers carry `loc_method =
  geocoded_llm_unchecked` until a reviewer accepts the row in `review/geocoding_review.csv`
  (`geocoded_llm_checked`); unchecked rows stay out of training (E3/E5 filter).
- `practice_components` is a `;`-joined list; `extra` is a JSON object; `ctx_reported_slope_pct`
  is an extra `ctx_` column (validated by prefix).
- Taxonomy ids come from rule mappings in `data/taxonomy/*_aliases.csv` with `accepted` empty:
  proposals, not decisions. See `data/taxonomy/README.md`.

## What each card says

Rows read and kept, rows dropped per rule (zero for all three loaders), every parsing and
mapping rule with its row count, coverage of key fields, licence and provenance, the
taxonomy mapping coverage and, for ERA and CSA, the reconciliation table with the result.
The HAB card adds the `.grist` row-count cross-check and the Ethiopian counts.
