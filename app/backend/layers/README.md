# Backend raster layers

The backend engine (`recommend.py` / `extract_features` path) samples the
11-layer GeoTIFF stack at request time. The **canonical copy lives at
`../../../geodata/layers/`** — it is not duplicated here to avoid a second
~730 MB copy.

Two ways to run the backend:

1. **Docker (recommended):** `docker-compose.yml` mounts `geodata/layers/`
   read-only into the container — nothing to do.
2. **Local dev:** either copy the GeoTIFFs into this folder, or (after the P1
   refactor) set `LAYERS_DIR=../../geodata/layers` in `app/backend/.env`.

Startup fails fast with a clear message if the layers are missing
(`recommender_service.warmup()`).
