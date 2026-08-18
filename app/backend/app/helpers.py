"""Shared helpers: error envelope, request id middleware, chat rate limiter."""
from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


def error_envelope(code: str, message: str, details: Any = None, status: int = 400):
    raise HTTPException(
        status_code=status,
        detail={"error": {"code": code, "message": message, "details": details}},
    )


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id
        start = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - start) * 1000
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time-Ms"] = f"{elapsed_ms:.1f}"
        logger.info(
            "request_id=%s method=%s path=%s status=%s latency_ms=%.1f",
            request_id,
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
        )
        return response


# Simple in-memory sliding-window rate limiter for /chat.
_chat_hits: dict[str, list[float]] = {}


def check_chat_rate_limit(client_key: str, limit_per_minute: int) -> None:
    now = time.time()
    window = 60.0
    hits = [t for t in _chat_hits.get(client_key, []) if now - t < window]
    if len(hits) >= limit_per_minute:
        error_envelope(
            "rate_limited",
            "Too many chat requests. Please wait a moment and try again.",
            status=429,
        )
    hits.append(now)
    _chat_hits[client_key] = hits
