import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from app.config import get_settings
from app.helpers import check_chat_rate_limit
from app.schemas import ChatRequest
from app.services.chat_service import run_chat, stream_chat

logger = logging.getLogger(__name__)
router = APIRouter(tags=["chat"])


@router.post("/chat")
async def chat(body: ChatRequest, request: Request):
    settings = get_settings()
    client = request.client.host if request.client else "unknown"
    check_chat_rate_limit(client, settings.chat_rate_limit_per_minute)

    history = [m.model_dump() for m in body.history]
    last_rec = body.last_recommendation

    if body.stream:
        async def event_gen():
            async for chunk in stream_chat(
                body.message, history, last_rec, body.top_n
            ):
                yield chunk

        return StreamingResponse(
            event_gen(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    result = await run_chat(body.message, history, last_rec, body.top_n)
    return JSONResponse(result)
