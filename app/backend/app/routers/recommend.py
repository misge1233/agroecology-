import logging

from fastapi import APIRouter, Query, Request

from app.helpers import error_envelope
from app.schemas import ContextResponse, RecommendRequest, RecommendResponse
from app.services import recommender_service as svc

logger = logging.getLogger(__name__)
router = APIRouter(tags=["recommend"])


@router.get("/context", response_model=ContextResponse)
def get_context(
    lat: float = Query(...),
    lon: float = Query(...),
):
    """Resolve the auto-derived agro-ecological context for a map point."""
    lat_lo, lat_hi = svc.LAT_BOUNDS
    lon_lo, lon_hi = svc.LON_BOUNDS
    if not (lat_lo <= lat <= lat_hi and lon_lo <= lon <= lon_hi):
        error_envelope(
            "out_of_bounds",
            f"Point ({lat}, {lon}) is outside Ethiopia "
            f"(lat {lat_lo}–{lat_hi}, lon {lon_lo}–{lon_hi}).",
            status=422,
        )
    ctx = svc.extract_context(lat, lon)
    return ContextResponse(lat=lat, lon=lon, aez_belt=ctx.get("aez_belt"), context=ctx)


@router.post("/recommend", response_model=RecommendResponse)
def post_recommend(body: RecommendRequest, request: Request):
    try:
        result = svc.recommend(
            lat=body.lat,
            lon=body.lon,
            practice_family=body.practice_family,
            indicator=body.indicator,
            crop_type=body.crop_type,
            top_n=body.top_n,
        )
    except ValueError as exc:
        # Enum membership is already enforced by the schema; this covers any
        # engine-level rejection (e.g. an out-of-support combination).
        error_envelope("recommend_error", str(exc), status=422)

    rid = getattr(request.state, "request_id", "-")
    logger.info(
        "request_id=%s lat=%.4f lon=%.4f family=%s indicator=%s top_n=%d",
        rid,
        body.lat,
        body.lon,
        body.practice_family,
        body.indicator,
        body.top_n,
    )
    return result
