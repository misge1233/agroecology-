# E3: geospatial context v2, rebuilt from sources, versioned, refreshed on schedule (10 Nov 2026)

**Binding:** `docs/roadmap/AE+_enhancement_roadmap.md` section 6 and Appendix C, `docs/decisions/enhancement_v2.md`, `docs/decisions/CSA_feature_stack_plan.md` and `pipelines/features/README_feature_stack.md` (the current stack), CLAUDE.md, this brief. E3 is independent of E2 and may run in parallel; it depends on E1 (country configuration, evidence store).

**Purpose.** Replace the hand-built, unversioned raster stack with one pipeline that downloads every layer from its source, warps it to the country grid, checks it, and writes an immutable, documented release; add the layers the practice question needs beyond the belt; make serving and training read the same release; write the context features into the evidence store. The current stack keeps working until the backend is pointed at the new release.

**Ground rules:** as E1, plus:

- **Wrap, never fork.** The downloaders in `pipelines/features/get_*.py`, `build_stack.py`, `final_qa.py` and `extract_features.py` become the modules of the new pipeline; their logic is moved and imported, not rewritten, and their CLIs keep working.
- **A release is immutable.** `geodata/<cc>/<release>/` is never edited after `manifest.json` is written; a rerun writes a new release id.
- **No secrets, no credentials in code.** Sources that need an account (none are planned; GEE is excluded) are not used; every URL is public and recorded.
- The owner runs the download steps (they need the internet and the WorldClim archives); the brief gives one command per step and the expected sizes and durations.
- Report as an **E3 block in `progress.md`**, then stop. The owner commits.

**Do not regress:** `python pipelines/features/extract_features.py --lat 9.03 --lon 38.74 --clean` returns the same 11 values from the current stack; the backend's `/advise` on the current `LAYERS_DIR` is unchanged until the switch; all test suites.

---

## Part A: pipeline skeleton

**A1. Layout.** `pipelines/geodata/` with `refresh.py` (CLI), `sources.yaml`, `grid.py` (country grid from `countries/<cc>.yaml` and `grid_definition.json`), `download.py` (resumable, checksum-verified downloads into `pipelines/geodata/cache/<source>/`, cache git-ignored), `layers/` (one module per layer group wrapping the existing `get_*.py` functions: `climate_worldclim.py`, `climate_chirps.py`, `terrain.py`, `soil.py`, `landcover.py`, `aez.py`, `access.py`, `vegetation.py`), `qa.py` (wrapping `final_qa.py`), `release.py` (manifest, VRT, diff against the previous release), `extract.py` (the library version of `extract_features.py`, taking a release path).

**A2. `sources.yaml`.** One entry per layer: `id`, `group`, `source_name`, `url` or URL template, `version`, `licence`, `citation`, `native_resolution`, `resampling` (bilinear for continuous, nearest for classes), `dtype`, `nodata`, `unit`, `update_cadence` (static, annual, occasional), `required` (true for the current 11, false for the new ones so a failed optional download does not block a release), `manual` (true for the WorldClim archives when the owner prefers to drop the zip into the cache).

**A3. `refresh.py --country ET --release 2026.1 [--layers ...] [--dry-run] [--skip-download]`.** Steps: read config, download (or verify cache), build each layer onto the grid, QA, write `geodata/ET/2026.1/` with `<layer>.tif` (COG, LZW, overviews), `stack.vrt`, `manifest.json` (per layer: source, version, URL, download date, file checksum, resampling, QA summary; plus git commit, grid definition hash, the `sources.yaml` hash), `qa_report.json`, `README.md` (auto-generated layer table), and `diff_vs_<previous>.md` when a previous release exists (per layer: changed or identical by checksum, and for changed layers the mean and quantile shift over the country mask). Exit non-zero on any required-layer failure.

---

## Part B: layers

**B1. The current 11, reproduced.** belt, precip_annual, temp_mean_annual, precip_seasonality, lgp_days, elevation, slope, soil_clay, soil_ph, soil_soc, land_cover, from the same sources as today (WorldClim 2.1 30s, Copernicus GLO-30 on AWS, SoilGrids v2 `/vsicurl/` VRTs, ESA WorldCover 2021 S3 tiles, the national belt shapefile). Acceptance: cell-for-cell equality with `geodata/layers/` for every layer (allowing float tolerance 1e-3 and documenting any difference caused by a source update).

**B2. New terrain layers (from the GLO-30 mosaic already downloaded).** `slope_length_factor` (LS factor, Desmet and Govers or the simpler RUSLE approximation; document which), `tpi` (topographic position index, 1 km window), `twi` (topographic wetness index), `flow_accumulation` (D8, pysheds or richdem; whichever installs cleanly on Windows, recorded), `dist_to_stream_m` (streams defined at an accumulation threshold stated in `sources.yaml`). All at 250 m from a 30 m computation then aggregated (mean for LS, TPI, TWI; min for distance).

**B3. New soil layers (SoilGrids v2, 0-30 cm where available).** `soil_sand`, `soil_bulk_density`, `soil_depth_bedrock` (SoilGrids `bdod`, `sand`, and the depth-to-bedrock product; if the latter is unavailable record it as optional-missing), `soil_awc` derived from clay, sand and bulk density by a documented pedotransfer function (Saxton and Rawls 2006), `soil_cec`, `soil_nitrogen`.

**B4. Recent climate normals (CHIRPS v2.0, 1991 to 2020).** `rain_mean_1991_2020` (annual total from monthly CHIRPS), `rain_cv_interannual`, `dry_season_length_months` (months below 50 mm in the climatology), `aridity_index` using WorldClim PET or a Hargreaves PET from WorldClim temperature (documented). CHIRPS monthly files are public (ClimateHazardsCenter FTP/HTTPS); cache them (about 1.5 GB for the window, Africa clip).

**B5. Land and access.** `landcover_2021` (as now) plus `cropland_fraction_1km` (share of cropland cells in a 1 km window); `travel_time_to_city_min` from the Malaria Atlas Project 2015 accessibility raster (Weiss et al. 2018, public download; cite); `ndvi_trend` from MODIS is **optional**: implement the module against the AppEEARS or LP DAAC HTTPS download if it can run without credentials, otherwise leave `required: false` with a clear note; do not block the release on it.

**B6. Köppen class** from the Beck et al. 2018 1 km raster (public), nearest resampling, as a categorical attribute.

**B7. Omo-Gibe overlays (placeholder).** `refresh.py` accepts `countries/ET.yaml: overlays.omo_gibe.rasters` and, when the files exist, warps them to the grid as `overlay_hotspot_coldspot.tif` and `overlay_typology.tif` with a `mask_omo_gibe.tif` (basin extent from the raster footprint); when absent, the manifest records them as `pending`. No modelling use in E3.

---

## Part C: serving and training read one release

**C1. Library.** `pipelines/geodata/extract.py`: `ContextExtractor(release_dir)` with `at(lat, lon) -> dict` (every layer, nearest-valid fallback as today, plus `release_id`) and `batch(df, lat_col, lon_col) -> DataFrame` with `ctx_<layer>` columns; `extract_features.py` becomes a thin CLI over it and still returns the legacy 11 fields with `--clean`.

**C2. Backend.** `GEODATA_RELEASE` setting (for example `ET/2026.1`) resolved against a `GEODATA_DIR` default `../../geodata`; when set, `recommend.extract_context` reads through `ContextExtractor` (additive adapter, `recommend.py` behaviour unchanged for the 11 legacy fields); when unset, the current `LAYERS_DIR` path is used. `/metadata` reports the release id and `/advise` responses carry `context.release`. The context card data gains the new layers under `context.extended` (frontend ignores them for now).

**C3. Evidence store context.** `pipelines/evidence/add_context.py --release ET/2026.1`: for every store row with `loc_precision` in (`site`, `district`) and `loc_method` not `geocoded_llm_unchecked`, write the `ctx_*` columns and `ctx_release`; rows outside the country mask keep nulls and are counted. Validation: `schema.validate` accepts `ctx_*` by prefix (E1 left this open) and checks ranges against `sources.yaml` (`valid_min`, `valid_max`). Reconciliation: for the 7,250 legacy ERA rows the six legacy numeric features (`Rainfall`, `Altitude_r`, `temp_mean_annual`, `precip_seasonality`, `slope`, `soil_clay`) match the frozen dataset values within 1e-3 (the legacy rows were enriched from the same sources; differences are reported, not hidden).

**C4. Retrain hook.** `model/train_model.py --release ET/2026.1` re-extracts the 13 legacy features for the training rows from the release before fitting (through `ContextExtractor`), so a future release can be retrained with one command; without the flag nothing changes. A metrics regression check prints the grouped ranking metrics of the quick protocol for the current stack versus the release.

---

## Part D: country abstraction dry run

`refresh.py --country KE --dry-run` resolves `countries/KE.yaml` (bbox, grid defined from the bbox at 0.00225 degrees, AEZ anchor `null`) and prints the plan: every global layer applies, the belt layer is reported as "no national anchor: belt attribute unavailable; Köppen class and GAEZ zones will stand in". No download for KE in E3.

---

## Part E: tests, docs, report

- Unit tests with tiny synthetic rasters (5 x 5 grids): grid construction, warping to grid, QA rules, LS/TPI/TWI/flow computations on a known DEM, pedotransfer function, manifest writing and diffing, `ContextExtractor` nearest-valid fallback, `add_context` range checks.
- Data tests (`@pytest.mark.data`): legacy 11 layers equal to the current stack; legacy feature reconciliation on the 7,250 rows; `extract_features.py --clean` output unchanged.
- Docs: `pipelines/geodata/README.md` (how to run a release, time and disk per step, how to add a layer, how the annual refresh works and what changes), `geodata/README.md` updated to point at releases, `docs/decisions/geodata_v2.md` (sources, licences, resampling, derived-layer formulas, the cadence table from the roadmap).
- `progress.md` E3 block: release id, per-layer table (source, version, size, QA result, changed versus the old stack), timing and disk, the reconciliation result, the new layers' summary statistics over Ethiopia, the backend switch instructions (`GEODATA_RELEASE=ET/2026.1` in `backend/.env`, restart), and open items (optional layers not built, licences to confirm).

## Acceptance

1. `python pipelines/geodata/refresh.py --country ET --release 2026.1` builds a complete release on the owner's machine from cached or freshly downloaded sources; the manifest lists every layer with checksum, source and licence; QA passes.
2. The 11 legacy layers equal the current stack; `extract_features.py --clean` returns identical values for the demo points in `data/lookups/demo_points.csv`.
3. At least the required new layers are present: LS factor, TPI, TWI, flow accumulation, distance to stream, sand, bulk density, AWC, CEC, recent rainfall mean and CV, dry season length, aridity index, cropland fraction, travel time, Köppen class. Optional layers are reported as built or pending.
4. Backend serves from the release when `GEODATA_RELEASE` is set and from the old stack when it is not; `/metadata` shows the release id; existing API tests pass in both modes.
5. `add_context.py` writes `ctx_*` for every eligible store row; the legacy six features reconcile within tolerance; the store validates.
6. `refresh.py --country KE --dry-run` prints a complete plan without downloading.
7. All tests pass; nothing committed.
