# pipelines/geodata: versioned geospatial context (E3)

One pipeline downloads every layer from its public source, warps it onto the country grid,
checks it and writes an **immutable, documented release** `geodata/<CC>/<release>/`. Serving
(`GEODATA_RELEASE`), training (`model/train_model.py --release`) and the evidence store
(`pipelines/evidence/add_context.py`) all read a release through one library,
`extract.ContextExtractor`. Decisions: `docs/decisions/geodata_v2.md`.

## Run a release

```bash
# 0. once: the flow-routing tool (WhiteboxTools; the package fetches its ~25 MB binary on first use)
python -m pip install whitebox==2.3.6
# 1. look first (no download, no write)
python pipelines/geodata/refresh.py --country ET --release 2026.1 --dry-run
# 2. manual sources (see below), then build
python pipelines/geodata/refresh.py --country ET --release 2026.1 --prune-downloads
# 3. evidence store context, retrain check, backend switch
python pipelines/evidence/add_context.py --release ET/2026.1
python model/train_model.py --release ET/2026.1 --quick --no-copy --artifacts model/artifacts/release_check
# backend/.env: GEODATA_RELEASE=ET/2026.1, then restart the API
```

Options: `--layers a,b` rebuilds only those layers and carries the rest from the previous
release; `--groups terrain,soil` reruns only those layer groups and takes the others from the
staging folder of an earlier run; `--skip-download` uses the cache only; `--prune-downloads`
deletes big raw files once their clips or intermediates are cached (the records and checksums
stay); `--rebuild` ignores layers already in the staging folder; `--in-process` builds every
group in one process instead of one worker process per group (the default, which frees memory
between groups and logs each group's peak memory). `GEODATA_CACHE=D:\geocache` moves the cache
to another drive. A failed run keeps `geodata/<CC>/.<release>.partial/` and the next run resumes
from it (built layers are kept, failed ones are rebuilt). A published release id is refused
(immutability): use the next id (`2026.2`).

**Before a national build**: the run prints the free space of the release and cache drives
against what it still needs and warns below 15 GB. WhiteboxTools needs about 2 GB per working
array on the 90 m grid and the group workers up to ~12 GB; if a build fails with
`memory allocation ... failed` or `MemoryError` on a machine with enough RAM, check the commit
charge (`Get-CimInstance Win32_OperatingSystem | Select FreeVirtualMemory`) and the processes
holding it (`Get-Process | Sort PagedMemorySize64 -Desc | Select -First 5`); on the owner's
machine the Windows Search indexer held 85 GB after indexing the cache. Exclude
`pipelines\geodata\cache` and `geodata\` from indexing (Windows Settings > Searching Windows >
Excluded folders) or restart the `WSearch` service, then resume. A short internet outage is
ridden out (DNS and connection errors are retried for up to 15 minutes per file).

**Manual sources** (`manual: true` in `sources.yaml`): the WorldClim 30 arc-second archives
(the owner may fetch them with `python pipelines/geodata/download.py --source worldclim_prec_30s`
and `--source worldclim_tavg_30s`) and the Köppen zip (figshare blocks scripts: download
`Beck_KG_V1.zip` from https://doi.org/10.6084/m9.figshare.6396959 into
`pipelines/geodata/cache/koppen_beck2018/`). `--dry-run` prints the exact paths.

## Time and disk per step (Ethiopia, 6,800 x 5,156 cells)

| Step | Download | Disk kept (with `--prune-downloads`) | Time (estimate) |
|---|---|---|---|
| belt (local shapefile) | 0 | 0 | < 1 min |
| WorldClim prec + tavg 30 s, tmin/tmax 2.5 min | 6.2 GB | 0.5 GB of clips | 10-20 min after download |
| CHIRPS monthly 1991-2020 (360 files, throttled) | 1.5 GB | 1.5 GB | 15-30 min |
| GLO-30 tiles (up to 204, ocean tiles 404) | up to 8 GB | ~3 GB of 90 m intermediates | 30-60 min tile pass; flow routing about 5-15 min (measured 3.5 s per 4 M cells on a crop of the real DEM; WhiteboxTools: up to ~12 GB RAM and ~4 GB of temporary rasters) |
| SoilGrids (19 streamed warps) + BDRICM | ~1.5 GB streamed | ~1 GB of clips | 1-2 h (network bound) |
| WorldCover 2021 (28 tiles) | ~3.5 GB | 0 | 30-45 min (10 m cropland count) |
| MAP travel time (WCS clip), Köppen | 0.2 GB | 0.2 GB | minutes |
| release (about 30 COGs) | | ~2.5 GB | QA and diffs 5-10 min |

Without `--prune-downloads` the cache needs about 22 GB more.

## Add a layer

1. Add the source (URL, licence, citation, version) and the layer (keys of brief A2 plus
   `valid_min`/`valid_max`, `max_nodata_share`, `kind`, `classes`) to `sources.yaml`.
2. Compute it in the group module under `layers/` (or a new module registered in
   `layers/__init__.py:GROUPS`): fetch through `ctx.downloader`, compute on `ctx.grid`, call
   `ctx.emit(layer_id, array, inputs)`.
3. Add a unit test on a tiny synthetic raster; build a new release id.

`ctx_<layer>` then appears in `ContextExtractor.batch`, in the backend's `context.extended`,
and in the evidence store after `add_context.py` (range-checked against `sources.yaml`).

## The annual refresh

Each year: `refresh.py --country ET --release <year>.1`. Layers whose sources change
(land cover, recent climate, vegetation trend when available) get new values; the static ones
(belt, WorldClim normals, terrain) rebuild from the cached sources and are proven unchanged by
the data checksum in `diff_vs_<previous>.md` (identical / changed, mean and quantile shift
over the country mask). Cadence per source: `docs/decisions/geodata_v2.md`. Then rerun
`add_context.py`, the retrain check, and switch `GEODATA_RELEASE` once reviewed.

## Files

| File | What |
|---|---|
| `refresh.py` | CLI: plan, download, build, QA, publish |
| `sources.yaml` | every source and layer (URL, version, licence, citation, resampling, ranges) |
| `grid.py` | country grid (`grid_definition.json`, or the bbox rule) |
| `download.py` | resumable, checksum-recorded downloads (`cache/<source>/downloads.json`); `--check` HEADs every URL |
| `layers/*.py` | one module per group; the legacy logic of `pipelines/features/get_*.py` moved here |
| `qa.py` | per-layer checks, legacy comparison, the dataset checks of `final_qa.py` |
| `release.py` | staging, `stack.vrt`, manifest, README, diffs, publish |
| `extract.py` | `ContextExtractor` (serving, training, evidence store) |
| `vector.py` | minimal shapefile reader and rasterizer (no vector library needed) |

The `pipelines/features/get_*.py`, `extract_features.py` and `final_qa.py` CLIs keep working:
they import the moved functions. `build_stack.py` (an older batch helper with alternative
sources: WorldClim BIO, GAEZ LGP, SoilGrids via the GDAL CLI) is left as it was; the release
pipeline does not use it.
