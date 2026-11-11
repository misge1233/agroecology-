"""Layer-group modules of the geodata pipeline (brief E3 A1).

Each module exposes ``GROUP``, ``LAYERS`` and ``build(ctx, wanted)``. :data:`GROUPS`
is the build order: the belt first (it defines the country mask used in the
statistics), WorldClim before CHIRPS (aridity needs the Hargreaves PET).
"""
from __future__ import annotations

from . import (access, aez, climate_chirps, climate_worldclim, koppen, landcover, overlays, soil, terrain,
               vegetation)

GROUPS = {
    "aez": aez,
    "climate_worldclim": climate_worldclim,
    "climate_chirps": climate_chirps,
    "terrain": terrain,
    "soil": soil,
    "landcover": landcover,
    "access": access,
    "koppen": koppen,
    "vegetation": vegetation,
    "overlays": overlays,
}
