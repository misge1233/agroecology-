"""POST /rank — Methodology 1 v2 ranking for any registry challenge and objective (E5 Part 4).

Available only with ``ADVISOR_ENGINE=m1_v2`` (503 otherwise); unknown challenge or
objective ids are a 422 in the error envelope. Additive: the legacy ``/recommend`` and
``/advise`` paths are unchanged.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Request

from app.helpers import error_envelope
from app.schemas import RankRequestBody, RankResponse
from app.services import m1_service

logger = logging.getLogger(__name__)
router = APIRouter(tags=["rank"])


@router.post("/rank", response_model=RankResponse)
def post_rank(body: RankRequestBody, request: Request):
    try:
        result = m1_service.rank(body.lat, body.lon, body.challenge_id, body.outcome_id, body.crop_type,
                                 body.top_n, body.country)
    except m1_service.EngineUnavailable as exc:
        error_envelope("engine_unavailable", str(exc), status=503)
    except LookupError as exc:
        error_envelope("rank_error", str(exc), status=422)
    except RuntimeError as exc:  # artifact missing although enabled
        error_envelope("engine_unavailable", str(exc), status=503)
    rid = getattr(request.state, "request_id", "-")
    ordering = result.get("ordering") or {}
    logger.info("request_id=%s rank engine=%s order=%s challenge=%s outcome=%s candidates=%d", rid, result["engine"],
                ordering.get("source", "m1_v2"), body.challenge_id, body.outcome_id, result["n_candidates"])
    return result
