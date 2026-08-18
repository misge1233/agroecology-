# Migration map — original project folders → `agroadvisor-et/`

Executed 18 Aug 2026 (Phase P0 of `research_project_plan.md`). All originals
were **copied, never moved or deleted** — the source folders remain intact until
you choose to remove them. Layer copies were verified byte-identical (size + `cmp`).

Legend: `AEZ/` = `AEZ map and soil type/`, `FS/` = `AEZ/feature_stack/`,
`APP/` = `agroecology_ai/`.

## Documentation

| Original | New location |
|---|---|
| `AEZ/SYSTEM_OVERVIEW.md` | `docs/reports/SYSTEM_OVERVIEW_v1_prototype.md` |
| `AEZ/ERA_preprocessing_report.md` | `docs/reports/` |
| `AEZ/dataset_preprocessing_report.md` | `docs/reports/` |
| `AEZ/feature_selection_report.md` | `docs/reports/` |
| `AEZ/merged_dataset_notes.md` | `docs/reports/` |
| `APP/README.md` | `docs/reports/README_v1_prototype_app.md` |
| `AEZ/data_dictionary.md` | `docs/data_dictionary.md` |
| `AEZ/CSA_feature_decision.md` | `docs/decisions/` |
| `AEZ/CSA_feature_stack_plan.md` | `docs/decisions/` |
| `AEZ/practice_family_mapping.md` | `docs/decisions/` |
| `RAG idea and Source.txt` | `docs/decisions/rag_sources_original_note.txt` |
| `APP/agroecology_ai_prompt.md` | `docs/decisions/` |
| `APP/agroecology_ai_ui_redesign_prompt.md` | `docs/decisions/` |
| `AgroGuide_CSA_Recommender.pptx` | `docs/presentations/` |
| `FS/README.md` | `pipelines/features/README_feature_stack.md` |

## Data

| Original | New location |
|---|---|
| `FS/dataset/ERA_Ethiopia_dataset.csv` | `data/raw/` (git-ignored; Dataverse is source of truth) |
| `FS/dataset/CSA_practices_by_Agroecology.xlsx` | `data/raw/` |
| `FS/dataset/CSA_ERA_final_model_ready.csv` | `data/processed/` |
| `FS/dataset/CSA_ERA_merged_model_ready.csv` | `data/processed/` |
| `FS/dataset/CSA_practices_model_ready.csv` | `data/processed/` |
| `FS/dataset/ERA_Ethiopia_model_ready.csv` | `data/processed/` |
| `FS/aez_belt_lookup.csv`, `FS/aez_attributes.csv`, `FS/grid_definition.json` | `data/lookups/` |
| `FS/demo_points.csv`, `FS/enriched_demo.csv`, `FS/enriched_demo_final.csv` | `data/lookups/` |
| `AEZ/agroecology_zones.csv`, `AEZ/combined_aez_x_soilgrid.csv`, `AEZ/soil_wrb1_grid_metadata.csv` | `data/lookups/` |

## Geodata

| Original | New location |
|---|---|
| `APP/backend/layers/*.tif` + `stack_all.vrt` (11 layers) | `geodata/layers/` — **canonical copy**, verified identical |
| `AEZ/agroecology_belt/` (AEZ shapefile) | `geodata/sources/agroecology_belt/` |
| `AEZ/soil_wrb1/` | `geodata/sources/soil_wrb1/` |
| `AEZ/additional/` (AEZ_32, Agroclimatic_zone, …) | `geodata/sources/additional/` |
| `FS/raw/wc2.1_30s_prec.zip`, `wc2.1_30s_tavg.zip` (~5.3 GB WorldClim) | **not copied** — re-downloadable from worldclim.org; see `geodata/README.md` |
| `FS/layers/` (duplicate stack copy) | **not copied** — superseded by `geodata/layers/` |

## Pipelines & model

| Original | New location |
|---|---|
| `FS/get_*.py`, `build_stack.py`, `build_zonal_attributes.py`, `add_aez_belt.py`, `extract_features.py`, `diag_soil.py`, `final_qa.py`, `make_maps.py` | `pipelines/features/` |
| `FS/build_practice_family.py` | `pipelines/dataset/` |
| `AEZ/practice image/` (generator, prompts) | `pipelines/practice_images/` |
| `FS/feature_selection.py`, `FS/train_model.py` | `model/` |
| `FS/artifacts/csa_model.joblib`, `model_metrics.json` | `model/artifacts/` |

## App

| Original | New location |
|---|---|
| `APP/backend/` (code, tests, artifacts, dataset, lookups) | `app/backend/` — **excluding** `.venv/`, `__pycache__/`, `.pytest_cache/`, `layers/` |
| `APP/backend/layers/` | not duplicated — see `app/backend/layers/README.md` |
| `APP/frontend/` | `app/frontend/` — **excluding** `node_modules/`, `.next/`, `tsconfig.tsbuildinfo` |
| `APP/docker-compose.yml` | `docker-compose.yml` (repo root) |

## Deliberately NOT migrated (superseded duplicates)

| Original | Reason |
|---|---|
| `FS/recommend.py`, `FS/groq_agent.py` | older copies; `app/backend/recommend.py` / `groq_agent.py` are canonical |
| `FS/artifacts/` duplicate of backend artifacts | single canonical artifact kept in `model/artifacts/` (same file as backend's) |
| `FS/dataset/CSA_ERA_merged_model_ready.csv` vs `_final_` | both kept in `data/processed/` for provenance (byte-identical, 2,315,033 B) |
| all `__pycache__/`, `.venv/`, `.next/`, `node_modules/`, `.pytest_cache/` | build junk, recreated by tooling |

## Housekeeping notes

- `_to_delete/hardlink_test_aez_belt.tif` (project root): a leftover from a
  filesystem test during migration — safe to delete.
- New files created (not migrated): `README.md`, `.gitignore`, this file,
  `geodata/README.md`, `app/backend/layers/README.md`, `rag/` package,
  `paper/` skeleton, `paper/references/era_doi_list.csv`.
