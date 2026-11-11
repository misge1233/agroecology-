# Decision record: geospatial context v2 (E3, 10 Nov 2026)

Binding with `docs/roadmap/AE+_enhancement_roadmap.md` section 6, `docs/decisions/enhancement_v2.md`
and `docs/briefs/E3_geodata_v2.md`. Implementation: `pipelines/geodata/`.

## 1. Releases

A release is `geodata/<CC>/<release>/` (id `ET/2026.1`): one Cloud Optimized GeoTIFF per layer
(LZW, predictor, internal overviews; nearest overviews for classes, average otherwise),
`stack.vrt`, `manifest.json` (per layer: source, version, URL, licence, citation, download date,
file and data checksums, resampling, QA; plus git commit, grid hash, `sources.yaml` hash),
`qa_report.json`, `README.md`, `diff_vs_<previous>.md`, `diff_vs_legacy.md`. It is built in a
staging folder and renamed into place; an existing id is refused. Rasters are git-ignored; the
text files are kept in git as provenance. The unversioned `geodata/layers/` stays the default
until `GEODATA_RELEASE` is set.

## 2. Grid

WGS84, 0.00225 degrees (~250 m), `data/lookups/grid_definition.json` for Ethiopia (6,800 x 5,156).
A country without a grid file gets one from its bounding box by the rule that reproduces the
Ethiopian file exactly (`ceil` of the extent over the resolution, origin at the north-west corner).

## 3. Sources and licences

| Source | Layers | Version | Licence (to confirm where marked) |
|---|---|---|---|
| National belt shapefile | `aez_belt` | as received 2025 | national data, internal use (**confirm**) |
| WorldClim 2.1, 30 s and 2.5 min | `precip_annual`, `temp_mean_annual`, `precip_seasonality`, `lgp_days`, `pet_hargreaves_annual` | 2.1 (1970-2000) | WorldClim terms, research and non-commercial use (**confirm**) |
| CHIRPS v2.0 Africa monthly | `rain_mean_1991_2020`, `rain_cv_interannual`, `dry_season_length_months`, `aridity_index` | 2.0 | public domain / CC0 (**confirm**) |
| Copernicus DEM GLO-30 (AWS) | `elevation`, `slope`, `slope_length_factor`, `tpi`, `twi`, `flow_accumulation`, `dist_to_stream_m` | 2021 release | Copernicus DEM licence, attribution required |
| SoilGrids v2.0 (ISRIC) | `soil_clay`, `soil_ph`, `soil_soc`, `soil_sand`, `soil_bulk_density`, `soil_cec`, `soil_nitrogen`, `soil_awc` | 2.0 | CC BY 4.0 |
| SoilGrids250m 2017, BDRICM | `soil_depth_bedrock` (optional) | 2017-03-10 | CC BY 4.0 |
| ESA WorldCover 2021 (AWS) | `land_cover`, `cropland_fraction_1km` | v200 | CC BY 4.0 |
| Malaria Atlas Project, accessibility 2015 (WCS) | `travel_time_to_city_min` | 2015 v1.0 | CC BY 4.0 |
| Beck et al. 2018 Köppen-Geiger | `koppen_class` | V1 | CC BY 4.0 |
| MODIS MOD13Q1 | `ndvi_trend` (pending) | 061 | open, but needs an Earthdata login: excluded |

No source needs an account. CHIRPS moved from `products/CHIRPS-2.0/` to `products/CHIRPS/v2.0/`
(verified 10 Nov 2026); figshare answers scripts with a browser challenge, so the Köppen zip is
a manual download; the MAP global zip is replaced by a WCS clip of the country box.

## 4. Resampling

Continuous layers bilinear; classes nearest (Köppen, overlays) or mode (WorldCover, as the
legacy stack); the belt is rasterized. Derived terrain is aggregated from 90 m to 250 m by mean
(LS, TPI, TWI), minimum (distance to stream) and maximum (upstream area, so a cell holding a
river carries the river's area).

## 5. Derived-layer formulas

- **Slope (legacy)**: `np.gradient` of the 250 m elevation, latitude-aware cell size, percent.
- **tan b and S (30 m)**: latitude-aware gradient of each GLO-30 tile; `S = (sin b / 0.0896)^1.3`
  (Moore and Burch 1986); both averaged to 90 m.
- **Flow routing (90 m)**: WhiteboxTools (MIT; the `whitebox` Python package and its binary, both
  versions recorded in the manifest): FillDepressions with `fix_flats`, D8Pointer, D8FlowAccumulation
  in cells; cells x the area of a cell in their row gives km2 (a catchment spans a few degrees of
  latitude, so the area error is under 3%). Streams are WhiteboxTools ExtractStreams on that area
  raster. pysheds was planned but cannot be installed: it needs numba, which does not support
  numpy 2.4.6 (owner, 10 Nov 2026: do not downgrade numpy). GLO-30 cells exactly at 0 m are sea.
  Routed at 3 arc-seconds because D8 over Ethiopia at 30 m is 2.3e9 cells; the 90 m grid is
  snapped to the tile seams. Catchments entering the bounding box from outside are truncated
  (few in Ethiopia, which is mostly upstream). The binary is run as a subprocess by
  `terrain.run_wbt` with stdout and stderr captured; a run fails (`WhiteboxError`, carrying the
  binary's own message) on a non-zero exit code, an error line in the output, or a missing or
  unreadable output file. The `whitebox` package's `run_tool` is not used for running tools: it
  returns 0 whenever the process starts and swallows the binary's error lines unless verbose,
  which is how the first national run reported "depressions filled" in 9 s with no output (the
  captured message was `memory allocation of 2044863360 bytes failed`: the machine's commit
  charge was exhausted by another process). Inputs are written as striped, uncompressed,
  classic (non-Big) TIFFs in row blocks, the subset WhiteboxTools reads.
- **LS**: `(min(a, 300 m) / 22.13)^0.4 x S`, `a` = specific catchment area = upstream area / flow
  width (`sqrt(dx dy)`); the cap is the practical RUSLE slope length (Renard et al. 1997). This
  is the RUSLE approximation of Moore and Burch (1986), chosen over Desmet and Govers (1996)
  because it needs only upstream area and slope.
- **TWI**: `ln(a / max(tan b, 0.001))`.
- **TPI**: elevation minus the NaN-aware mean of the 11 x 11 window at 90 m (~1 km).
- **Distance to stream**: Euclidean distance (scipy) to the ExtractStreams cells (upstream area >=
  1 km2), in metres; the E-W cell size is taken at the middle latitude (error < 2.5% across
  Ethiopia). WhiteboxTools' EuclideanDistance is not used because on a geographic grid it measures
  in degrees, not metres.
- **Soil 0-30 cm**: thickness-weighted mean of 0-5, 5-15, 15-30 cm (5, 10, 15).
- **AWC**: Saxton and Rawls (2006) eqs 1-3, 5-8; sand, clay, OM = SOC x 1.724 (capped 8%),
  density factor = SoilGrids bulk density / normal density bounded to 0.9-1.3; AWC =
  `theta_33,DF - theta_1500`, in mm per m of soil.
- **CHIRPS**: annual totals from the 12 monthly files; mean and sample CV (ddof 1) of the 30
  years at 0.05 degrees, then bilinear; dry months = months whose 1991-2020 mean is below 50 mm,
  counted on the grid after warping the 12 climatological months.
- **PET and aridity**: Hargreaves-Samani `0.0023 x 0.408 Ra (Tmean + 17.8) sqrt(Tmax - Tmin)`
  per month (FAO-56 Ra at mid-month), Tmean from the 30 s normals, Tmax - Tmin from the 2.5 min
  normals; aridity = CHIRPS 1991-2020 mean / PET (UNEP P/PET). The rainfall and temperature
  periods differ (1991-2020 against 1970-2000); recorded in the manifest notes.
- **Cropland share**: each 10 m WorldCover pixel counted in the cell containing its centre;
  share of class 40 among valid pixels in a 1 km box (per-axis weights 0.5, 1, 1, 1, 0.5).

## 6. Legacy reproduction

The 11 legacy layers are rebuilt by the moved logic of `pipelines/features/get_*.py` and compared
cell for cell with `geodata/layers` (integers exactly, floats within 1e-3). The WorldClim monthly
rasters are clipped to the padded country box before the same arithmetic (identical values,
tested).

**Elevation and slope: a statistical tolerance instead of equality** (reviewer, 11 Nov 2026).
The GLO-30 tiles on AWS have been re-issued since the legacy stack was built, and the new
composite fills 197,136 cells near the north-east border that were nodata before. Measured on
the national rebuild: elevation median |diff| 0.015 m, p95 2.1 m, p99 5.8 m; slope median
0.005 %, p99 1.8 %. Accepted. `sources.yaml` records `legacy_tolerance` for these two layers
(elevation: median |diff| < 0.1 m and p99 < 10 m; slope: median < 0.05 % and p99 < 5 %, both
over the country mask); `qa.compare_arrays` reports the median, p95, p99 and max absolute
difference and the newly valid cells, the manifest carries them per layer
(`legacy_within_tolerance`, `legacy_abs_diff`, `legacy_newly_valid_cells`) and
`diff_vs_legacy.md` shows them. Every other legacy layer keeps strict equality. The retrain
check (`train_model.py --release`) must show the ranking metrics within one standard deviation
of the current stack before `GEODATA_RELEASE` is switched. The belt is the shapefile rasterized with **outer rings only**, which is how the legacy
raster was made (0 cells differ); honouring the polygon holes would change 93,119 cells (0.5% of
the country): belt islands enclosed by another belt. **Owner decision**: keep the legacy rule
(the model is trained on it) or switch to the hole-aware raster in a later release with a retrain.

## 7. Refresh cadence (roadmap 6.2)

| Layer | Source | Update behaviour | Cadence |
|---|---|---|---|
| Belt (AEZ) | national shapefile | static anchor | on national revision |
| Rainfall, temperature, seasonality, growing period | WorldClim 2.1 (1970 to 2000 normals) | static | re-verified each release |
| Recent climate normals | CHIRPS v2 (rolling 30-year window) | changes each year | annual |
| Elevation, slope, the new terrain layers | Copernicus GLO-30 | static | re-verified |
| Clay, pH, SOC, sand, bulk density, CEC, N, AWC, depth | SoilGrids | occasional | re-verified |
| Land cover, cropland share | ESA WorldCover 2021 (annual successor when available) | annual | annual |
| Vegetation trend | MODIS NDVI | annual | pending (credentials) |
| Access | MAP travel time 2015 | occasional | re-verified |
| Köppen class | Beck et al. 2018 | static | re-verified |

## 8. Build process (after the first national run, 11 Nov 2026)

- **One worker process per layer group.** `refresh.py` spawns itself with `--_group <name>` for
  each group, so every array is freed between groups and the peak working set and peak commit
  of each group are recorded (`manifest.peak_memory_mb`). The first run hit a `MemoryError` on a
  267 MiB array in soil after terrain. `--in-process` keeps one process (tests, debugging);
  `--groups a,b` reruns only those groups and takes the others from the staging folder.
- **Saxton-Rawls AWC** is computed in float32 and in blocks of 256 rows (about 20 temporaries;
  at full-grid float64 they cost 5 GB).
- **Outages.** DNS and connection errors (no HTTP answer) are retried with backoff (5 s doubling
  to 120 s) for up to 15 minutes per file before the file is given up; they do not consume the
  ordinary retries. HTTP 429/5xx keep their `Retry-After` handling. Every request to one server
  waits at least 1 s after the previous one (`polite_s`; CHIRPS answers 429 when hammered).
- **Disk pre-flight.** Before building, the free space of the release and cache drives is
  compared with an estimate of what the run still needs (downloads not yet cached, about 110 MB
  per layer still to write, 4 GB of terrain temporaries); below 15 GB, or below the estimate,
  the run warns and goes on (`manifest.disk_preflight`).
- **The machine, not the pipeline.** The national routing needs about 2 GB per f64 array in
  WhiteboxTools and the group workers up to ~12 GB; on the owner's machine the commit limit
  (RAM + pagefile) was exhausted by the Windows Search indexer (85 GB committed) after the
  cache filled with large rasters. Exclude `pipelines/geodata/cache` and `geodata/` from Windows
  Search indexing, or restart the `WSearch` service, before a build.

## 9. Serving, training, evidence

`GEODATA_RELEASE=ET/2026.1` (backend `.env`) replaces the engine's `extract_context` by an
adapter over `ContextExtractor.legacy_context` (same 11 fields, rounding and 120-cell fallback;
`recommend.py` is not edited) and adds `context.release` and `context.extended`; `/metadata`
reports `geodata.release`. `add_context.py` writes `ctx_<layer>` and `ctx_release` for store rows
at site or district precision that are not unchecked LLM geocodes; `schema.validate` checks
`ctx_*` against `sources.yaml`. `train_model.py --release` re-extracts the context features and
prints the quick-protocol ranking metrics of the current stack against the release.
