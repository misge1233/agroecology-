"""GET /registry: data-driven challenges and objectives for a country (Phase E1, additive)."""
from __future__ import annotations

from fastapi import APIRouter, Query

from app.helpers import error_envelope
from app.schemas import RegistryResponse
from app.services import registry_service

router = APIRouter(tags=["registry"])


@router.get("/registry", response_model=RegistryResponse)
def registry(country: str = Query(default="ET", min_length=2, max_length=2, description="ISO 3166-1 alpha-2")):
    """Serve ``data/evidence/registry_<CC>.json`` (404 unknown country, 503 not built)."""
    try:
        return registry_service.get_registry(country)
    except registry_service.UnknownCountry:
        error_envelope("unknown_country", f"No registry or country configuration for {country!r}.", status=404)
    except registry_service.RegistryUnavailable as exc:
        error_envelope("registry_unavailable", str(exc), status=503)
