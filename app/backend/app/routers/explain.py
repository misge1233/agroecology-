import logging

from fastapi import APIRouter, Request

from app.helpers import error_envelope
from app.schemas import ExplainRequest, ExplainResponse
from app.services import explain_service

logger = logging.getLogger(__name__)
router = APIRouter(tags=["explain"])


@router.post("/explain", response_model=ExplainResponse)
def post_explain(body: ExplainRequest, request: Request):
    """Grounded, cited explanation of a /recommend result (RAG layer)."""
    if not explain_service.is_ready():
        error_envelope(
            "rag_not_ready",
            "RAG index not built — run rag/ingest (fetch_papers → parse_and_chunk "
            "→ build_index) to create rag/index/store and rag/corpus/chunks.jsonl.",
            status=503,
        )

    try:
        result = explain_service.explain(
            recommendation=body.recommendation,
            question=body.question,
            k=body.k,
        )
    except Exception as exc:  # corrupt index / retriever failure → clean envelope
        logger.exception("Explain failed: %s", exc)
        error_envelope(
            "explain_failed",
            "The explanation layer could not query the evidence index. "
            "If the index was interrupted mid-build, re-run rag/ingest/build_index.py.",
            status=503,
        )
    rid = getattr(request.state, "request_id", "-")
    logger.info(
        "request_id=%s explain grounded=%s llm_used=%s citations=%d",
        rid,
        result["grounded"],
        result["llm_used"],
        len(result["citations"]),
    )
    return result
