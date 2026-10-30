"""POST /advise — the evidence-tiered advisory (Phase P9).

Wraps ``/recommend``: the same request plus ``language``; the response carries
the mode, its reasons (catalog keys), the unchanged ``/recommend`` payload
(or null), the knowledge candidates and the per-candidate evidence counts.
A rank-impossible pair is a 200 in knowledge-led mode, never a 4xx.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Request

from app.helpers import error_envelope
from app.schemas import AdviseRequest, AdviseResponse
from app.services.advisory_service import advise

logger = logging.getLogger(__name__)
router = APIRouter(tags=["advise"])


@router.post("/advise", response_model=AdviseResponse)
def post_advise(body: AdviseRequest, request: Request):
    try:
        result = advise(
            lat=body.lat, lon=body.lon, practice_family=body.practice_family,
            indicator=body.indicator, crop_type=body.crop_type, top_n=body.top_n,
            language=body.language,
        )
    except ValueError as exc:  # anything other than the two rank-impossible errors
        error_envelope("advise_error", str(exc), status=422)
    rid = getattr(request.state, "request_id", "-")
    logger.info(
        "request_id=%s advise mode=%s family=%s indicator=%s candidates=%d",
        rid, result["mode"], body.practice_family, body.indicator, len(result["knowledge_candidates"]),
    )
    return result
