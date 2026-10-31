"""Voice endpoints for the chat (Phase U6).

* ``POST /speech/transcribe?language=en|am|om``: the raw recording is the
  request body (``Content-Type: audio/webm`` and similar), so no multipart
  dependency is needed. Returns ``{"text": ..., "language": ...}``.
* ``POST /speech/synthesize``: JSON ``{"text", "language"}``; returns MP3.

Both share the chat's per-client rate limit bucket (prefixed) and answer 503
``speech_unavailable`` when no OpenAI key is configured, so the UI can fall
back to the browser's speech engines.
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.config import get_settings
from app.helpers import check_chat_rate_limit, error_envelope
from app.services import speech_service

router = APIRouter(prefix="/speech", tags=["speech"])


class TranscribeResponse(BaseModel):
    text: str
    language: Literal["en", "am", "om"]


class SynthesizeRequest(BaseModel):
    text: str = Field(min_length=1, max_length=20_000)
    language: Literal["en", "am", "om"] = "en"


async def _guard(request: Request, direction: Literal["stt", "tts"], language: str) -> None:
    settings = get_settings()
    if await speech_service.provider(direction, language, settings) is None:  # type: ignore[arg-type]
        error_envelope("speech_unavailable", "Server speech is not available for this language.", status=503)
    client = request.client.host if request.client else "unknown"
    check_chat_rate_limit(f"speech:{client}", settings.chat_rate_limit_per_minute)


class SpeechStatus(BaseModel):
    #: Per language: can the server transcribe / read aloud? (local MMS or OpenAI)
    stt: dict[str, bool]
    tts: dict[str, bool]


@router.get("/status", response_model=SpeechStatus)
async def status() -> SpeechStatus:
    """Which server speech directions work right now, per language."""
    return SpeechStatus(**await speech_service.capabilities(get_settings()))


@router.post("/transcribe", response_model=TranscribeResponse)
async def transcribe(
    request: Request,
    language: Literal["en", "am", "om"] = Query("en"),
) -> TranscribeResponse:
    await _guard(request, "stt", language)
    settings = get_settings()
    content_type = request.headers.get("content-type", "")
    if speech_service.audio_extension(content_type) is None:
        error_envelope("unsupported_audio", f"Unsupported audio type: {content_type or 'none'}.", status=415)
    audio = await request.body()
    if not audio:
        error_envelope("empty_audio", "No audio received.", status=400)
    if len(audio) > settings.speech_max_upload_mb * 1024 * 1024:
        error_envelope("audio_too_large", f"Recordings are limited to {settings.speech_max_upload_mb} MB.", status=413)
    try:
        text = await speech_service.transcribe(audio, content_type, language, settings)
    except speech_service.SpeechError:
        error_envelope("transcription_failed", "The recording could not be transcribed.", status=502)
    return TranscribeResponse(text=text, language=language)


@router.post("/synthesize")
async def synthesize(body: SynthesizeRequest, request: Request) -> Response:
    await _guard(request, "tts", body.language)
    try:
        audio, media_type = await speech_service.synthesize(body.text, body.language, get_settings())
    except speech_service.SpeechError as exc:
        status = 400 if str(exc) == "nothing_to_say" else 502
        error_envelope(str(exc), "The answer could not be read aloud.", status=status)
    return Response(content=audio, media_type=media_type, headers={"Cache-Control": "no-store"})
