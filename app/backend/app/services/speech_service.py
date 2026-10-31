"""Voice for the chat (Phase U6): speech-to-text and text-to-speech.

Both directions use the OpenAI audio API over plain ``httpx`` (the same
pattern as ``openai_chat.py``; no SDK dependency):

* ``transcribe`` turns a short recording of the user's question into text.
  English is pinned with ``language="en"``; Amharic and Afaan Oromoo are
  steered with a one-line prompt in that language instead, because the
  ``language`` parameter is not guaranteed for them and an unsupported code
  would fail the whole request.
* ``synthesize`` reads an assistant answer aloud. The text is only *cleaned
  for speech* (Markdown, citation markers and URLs removed); words and numbers
  are never rewritten, so the spoken answer carries exactly the model's
  figures (CLAUDE.md doctrine 1).

A missing ``OPENAI_API_KEY`` makes ``is_ready()`` false; the router answers
503 and the UI falls back to the browser's own speech engines.
"""
from __future__ import annotations

import logging
import re
import time
from typing import Literal

import httpx

from app.config import Settings

logger = logging.getLogger(__name__)

Language = Literal["en", "am", "om"]

OPENAI_TRANSCRIBE_URL = "https://api.openai.com/v1/audio/transcriptions"
OPENAI_SPEECH_URL = "https://api.openai.com/v1/audio/speech"
OPENAI_MODELS_URL = "https://api.openai.com/v1/models"

#: Longest text the speech endpoint accepts (OpenAI limit is 4096 characters).
MAX_TTS_CHARS = 4000

#: A short prompt in the user's language biases recognition toward it.
_STT_PROMPTS: dict[str, str] = {
    "en": "A farmer in Ethiopia asks about agricultural practices, soil, water and crops.",
    "am": "አንድ ገበሬ ስለ እርሻ ልማዶች፣ አፈር፣ ውሃና ሰብል ይጠይቃል።",
    "om": "Qonnaan bulaan tokko waa'ee gochaalee qonnaa, biyyee, bishaanii fi midhaanii gaafata.",
}

#: Delivery instructions for the TTS model, one per UI language.
_TTS_INSTRUCTIONS: dict[str, str] = {
    "en": "Speak clearly and calmly, like an agricultural extension officer advising a farmer.",
    "am": "Speak in Amharic with natural Ethiopian pronunciation, clearly and calmly, like an extension officer advising a farmer.",
    "om": "Speak in Afaan Oromoo with natural Oromo pronunciation, clearly and calmly, like an extension officer advising a farmer.",
}

_AUDIO_EXTENSIONS: dict[str, str] = {
    "audio/webm": "webm",
    "audio/ogg": "ogg",
    "audio/mp4": "mp4",
    "audio/mpeg": "mp3",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
}


class SpeechError(RuntimeError):
    """The upstream speech service failed or returned nothing usable."""


def is_ready(settings: Settings) -> bool:
    """True when server-side speech is configured (an OpenAI key is set)."""
    return bool(settings.openai_api_key.strip())


#: Cached result of the model-access probe: (checked_at, {"stt": bool, "tts": bool}).
_access_cache: tuple[float, dict[str, bool]] | None = None
ACCESS_TTL_SECONDS = 600.0


async def check_access(settings: Settings) -> dict[str, bool]:
    """Whether the key's project can use the configured STT and TTS models.

    A key alone is not enough: an OpenAI project may lack access to audio
    models (403 ``model_not_found``). ``GET /v1/models/{id}`` answers that for
    free, so the UI can pick the browser engines up front instead of failing
    on the user's first recording. Cached for ``ACCESS_TTL_SECONDS``.
    """
    global _access_cache
    if not is_ready(settings):
        return {"stt": False, "tts": False}
    now = time.monotonic()
    if _access_cache and now - _access_cache[0] < ACCESS_TTL_SECONDS:
        return _access_cache[1]
    result: dict[str, bool] = {}
    async with _client(settings) as client:
        for key, model in (("stt", settings.speech_stt_model), ("tts", settings.speech_tts_model)):
            try:
                res = await client.get(f"{OPENAI_MODELS_URL}/{model}")
                result[key] = res.status_code == 200
            except httpx.HTTPError as exc:
                logger.warning("Speech model probe failed for %s: %s", model, exc)
                result[key] = False
    if not all(result.values()):
        logger.info("Server speech access: %s (browser speech will be used where missing)", result)
    _access_cache = (now, result)
    return result


def audio_extension(content_type: str) -> str | None:
    """File extension for an uploaded recording's MIME type, or None if unsupported."""
    base = content_type.split(";", 1)[0].strip().lower()
    return _AUDIO_EXTENSIONS.get(base)


_CITATION = re.compile(r"\[(?:G|W)?\d+(?:\s*[,–-]\s*(?:G|W)?\d+)*\]")
_LINK = re.compile(r"\[([^\]]+)\]\((?:[^)]+)\)")
_URL = re.compile(r"https?://\S+")
_MD_MARKS = re.compile(r"(\*\*|__|\*|_|`+|^#{1,6}\s*|^>\s*)", re.MULTILINE)
_BULLET = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+", re.MULTILINE)


def clean_for_speech(text: str, limit: int = MAX_TTS_CHARS) -> str:
    """Strip Markdown, citation markers and URLs so the answer reads naturally.

    Only formatting is removed: no word or number is changed. Long answers are
    cut at the last sentence end before ``limit``.
    """
    out = _LINK.sub(r"\1", text)
    out = _URL.sub("", out)
    out = _CITATION.sub("", out)
    out = _BULLET.sub("", out)
    out = _MD_MARKS.sub("", out)
    # Each former line becomes its own sentence-ish pause.
    lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
    out = " ".join(ln if ln.endswith((".", "?", "!", "።")) else ln.rstrip(":;,") + "." for ln in lines)
    out = re.sub(r"\s+([,.;:!?])", r"\1", out)
    out = re.sub(r"\s{2,}", " ", out).strip()
    if len(out) > limit:
        cut = out[:limit]
        end = max(cut.rfind(". "), cut.rfind("። "), cut.rfind("? "), cut.rfind("! "))
        out = cut[: end + 1] if end > limit // 2 else cut
    return out


def _client(settings: Settings) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=settings.openai_timeout_seconds,
        headers={"Authorization": f"Bearer {settings.openai_api_key}"},
    )


LANGUAGES: tuple[Language, ...] = ("en", "am", "om")
Provider = Literal["local", "openai"]


def local_languages(settings: Settings) -> set[str]:
    from app.services import local_speech

    if not settings.speech_local_enabled or not local_speech.available():
        return set()
    wanted = {x.strip() for x in settings.speech_local_languages.split(",") if x.strip()}
    return {lang for lang in wanted if local_speech.supports(lang)}


async def provider(direction: Literal["stt", "tts"], language: Language, settings: Settings) -> Provider | None:
    """Which engine serves this direction and language, or None.

    Local MMS first for its languages (dedicated Amharic / Oromo voices and
    recognition adapters; OpenAI's models do not cover Afaan Oromoo), then
    OpenAI when the project can use the configured model.
    """
    if language in local_languages(settings):
        from app.services import local_speech

        if direction == "tts" or (settings.speech_local_asr and local_speech.asr_ready()):
            return "local"
    if (await check_access(settings))[direction]:
        return "openai"
    return None


async def capabilities(settings: Settings) -> dict[str, dict[str, bool]]:
    """Per direction and language: can the server do it? (GET /speech/status)."""
    return {
        direction: {lang: (await provider(direction, lang, settings)) is not None for lang in LANGUAGES}
        for direction in ("stt", "tts")
    }


async def transcribe(audio: bytes, content_type: str, language: Language, settings: Settings) -> str:
    """Speech-to-text for one recording through the language's provider."""
    which = await provider("stt", language, settings)
    if which == "local":
        from starlette.concurrency import run_in_threadpool

        from app.services import local_speech

        try:
            text = await run_in_threadpool(local_speech.transcribe, audio, language)
        except Exception as exc:
            logger.warning("Local transcription failed (%s): %s", language, exc)
            raise SpeechError("transcription_failed") from exc
        logger.info("Locally transcribed %d bytes of %s audio into %d characters", len(audio), language, len(text))
        return text
    if which is None:
        raise SpeechError("transcription_failed")
    return await _openai_transcribe(audio, content_type, language, settings)


async def _openai_transcribe(audio: bytes, content_type: str, language: Language, settings: Settings) -> str:
    """Speech-to-text for one recording. Raises SpeechError on upstream failure."""
    ext = audio_extension(content_type) or "webm"
    data: dict[str, str] = {
        "model": settings.speech_stt_model,
        "prompt": _STT_PROMPTS[language],
        "response_format": "json",
    }
    if language == "en":
        data["language"] = "en"
    files = {"file": (f"question.{ext}", audio, content_type.split(";", 1)[0])}
    async with _client(settings) as client:
        try:
            res = await client.post(OPENAI_TRANSCRIBE_URL, data=data, files=files)
            res.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("Transcription failed (%s): %s", language, exc)
            raise SpeechError("transcription_failed") from exc
    text = str(res.json().get("text", "")).strip()
    logger.info("Transcribed %d bytes of %s audio into %d characters", len(audio), language, len(text))
    return text


async def synthesize(text: str, language: Language, settings: Settings) -> tuple[bytes, str]:
    """Text-to-speech for one answer: (audio bytes, media type). Raises SpeechError."""
    spoken = clean_for_speech(text)
    if not spoken:
        raise SpeechError("nothing_to_say")
    which = await provider("tts", language, settings)
    if which == "local":
        from starlette.concurrency import run_in_threadpool

        from app.services import local_speech

        try:
            audio = await run_in_threadpool(local_speech.synthesize_wav, spoken, language)
        except Exception as exc:
            logger.warning("Local speech synthesis failed (%s): %s", language, exc)
            raise SpeechError("synthesis_failed") from exc
        logger.info("Locally synthesized %d characters of %s speech", len(spoken), language)
        return audio, "audio/wav"
    if which is None:
        raise SpeechError("synthesis_failed")
    return await _openai_synthesize(spoken, language, settings), "audio/mpeg"


async def _openai_synthesize(spoken: str, language: Language, settings: Settings) -> bytes:
    """OpenAI text-to-speech for already-cleaned text, as MP3 bytes."""
    payload = {
        "model": settings.speech_tts_model,
        "voice": settings.speech_tts_voice,
        "input": spoken,
        "instructions": _TTS_INSTRUCTIONS[language],
        "response_format": "mp3",
    }
    async with _client(settings) as client:
        try:
            res = await client.post(OPENAI_SPEECH_URL, json=payload)
            res.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("Speech synthesis failed (%s): %s", language, exc)
            raise SpeechError("synthesis_failed") from exc
    logger.info("Synthesized %d characters of %s speech", len(spoken), language)
    return res.content
