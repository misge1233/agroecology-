"""Vegetation trend (brief E3 B5, optional): ``ndvi_trend`` from MODIS MOD13Q1.

MOD13Q1 is distributed by NASA LP DAAC; both the HTTPS data pool and AppEEARS need a
NASA Earthdata login, and the brief excludes sources that need an account. The layer
therefore stays ``required: false`` and every release records it as ``pending`` with
that reason. When a credential-free mirror is agreed, implement ``build`` here: annual
mean NDVI per year, the per-cell OLS slope over the window, bilinear to the grid.
"""
from __future__ import annotations

from ..core import BuildContext

GROUP = "vegetation"
LAYERS = ("ndvi_trend",)
SOURCE = "modis_ndvi"


def build(ctx: BuildContext, wanted: set[str]) -> None:
    """Record ``ndvi_trend`` as pending (credentials required)."""
    if "ndvi_trend" in wanted and not ctx.done("ndvi_trend"):
        ctx.mark("ndvi_trend", "pending", ctx.catalog.source(SOURCE)["reason"])
