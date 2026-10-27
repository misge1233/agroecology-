"""GET /geocode — place-name search for the Advisor's location step (U1).

Wraps the chat pipeline's curated gazetteer (``services.geocode``): offline,
deterministic, Ethiopia-only. The Nominatim network fallback stays off, as it
does for chat, so the endpoint never leaks a query to a third party.
"""
from __future__ import annotations

from fastapi import APIRouter, Query

from app.schemas import GeocodeResponse
from app.services.geocode import geocode_place

router = APIRouter(tags=["geocode"])


@router.get("/geocode", response_model=GeocodeResponse)
def geocode(q: str = Query(..., min_length=2, max_length=120)) -> GeocodeResponse:
    """Resolve a town/city name to WGS84 coordinates, or report ``found=False``."""
    hit = geocode_place(q, allow_network=False)
    if hit is None:
        return GeocodeResponse(query=q, found=False)
    return GeocodeResponse(
        query=q, found=True, name=hit.name, lat=hit.lat, lon=hit.lon, source=hit.source
    )
