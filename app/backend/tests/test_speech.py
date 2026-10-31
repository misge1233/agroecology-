"""Tests for the chat voice (Phase U6).

Run anywhere: a minimal app mounts only the speech router (no recommender
warm-up, no rasters), upstream OpenAI calls and the local MMS models are
monkeypatched, so no network, key or model download is used.
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Settings
from app.routers import speech as speech_router
from app.services import local_speech as ls
from app.services import speech_numbers as sn
from app.services import speech_service as ss


def make_client(
    monkeypatch: pytest.MonkeyPatch,
    key: str = "sk-test",
    openai: dict[str, bool] | None = None,
    local: bool = False,
) -> TestClient:
    """App with the speech router; OpenAI model access and local voice are faked."""
    settings = Settings(_env_file=None, openai_api_key=key, chat_rate_limit_per_minute=1000, speech_local_enabled=local)
    monkeypatch.setattr(speech_router, "get_settings", lambda: settings)

    async def access(_s: Settings) -> dict[str, bool]:
        return openai if openai is not None else ({"stt": True, "tts": True} if key else {"stt": False, "tts": False})

    monkeypatch.setattr(ss, "check_access", access)
    monkeypatch.setattr(ls, "available", lambda: local)
    monkeypatch.setattr(ls, "asr_ready", lambda: True)
    app = FastAPI()
    app.include_router(speech_router.router)
    return TestClient(app)


# ------------------------------------------------------------ clean_for_speech
def test_clean_for_speech_strips_formatting_but_keeps_every_number() -> None:
    text = (
        "### Top practice\n"
        "**Mulch + Water harvesting** cut soil loss by ~76% [1][G2] (see https://doi.org/10.1/x).\n"
        "- Based on 3 field observations [3, 4]\n"
        "1. Read the [guide](https://example.org/guide)"
    )
    out = ss.clean_for_speech(text)
    assert "76%" in out and "3 field observations" in out
    for gone in ("**", "###", "[1]", "[G2]", "[3, 4]", "https://", "](", "- "):
        assert gone not in out
    assert "Read the guide" in out


def test_clean_for_speech_cuts_long_text_at_a_sentence_end() -> None:
    text = "One sentence here. " * 400
    out = ss.clean_for_speech(text, limit=500)
    assert len(out) <= 500
    assert out.endswith(".")


def test_clean_for_speech_keeps_ethiopic_sentence_marks() -> None:
    out = ss.clean_for_speech("ማልች ይጠቀሙ።\nውሃ ይሰብስቡ።")
    assert out == "ማልች ይጠቀሙ። ውሃ ይሰብስቡ።"


def test_audio_extension_accepts_browser_recording_types() -> None:
    assert ss.audio_extension("audio/webm;codecs=opus") == "webm"
    assert ss.audio_extension("audio/mp4") == "mp4"
    assert ss.audio_extension("video/mp4") is None


# ----------------------------------------------------------- numbers to words
@pytest.mark.parametrize(
    ("value", "om", "am"),
    [
        ("7", "torba", "ሰባት"),
        ("10", "kudhan", "አሥር"),
        ("15", "kudha shan", "አሥራ አምስት"),
        ("76", "torbaatamii jaha", "ሰባ ስድስት"),
        ("90", "sagaltama", "ዘጠና"),
        ("100", "dhibba tokko", "መቶ"),
        ("214", "dhibba lama fi kudha afur", "ሁለት መቶ አሥራ አራት"),
        ("1,416", "kuma tokko fi dhibba afur fi kudha jaha", "አንድ ሺህ አራት መቶ አሥራ ስድስት"),
        ("2.34", "lama tuqaa sadii afur", "ሁለት ነጥብ ሦስት አራት"),
        ("0", "duwwaa", "ዜሮ"),
    ],
)
def test_number_words(value: str, om: str, am: str) -> None:
    assert sn.number_words(value, "om") == om
    assert sn.number_words(value, "am") == am


def test_verbalize_spells_out_every_figure_with_its_unit() -> None:
    om = sn.verbalize("Rooba 756 mm, ho'a 20.7 °C, dhiqama ~76% hir'isa.", "om")
    assert not any(ch.isdigit() for ch in om)
    assert "milimeetira" in om and "digirii selsiyesii" in om and "dhibbeentaa torbaatamii jaha" in om
    am = sn.verbalize("የአፈር መሸርሸር 76% ቀንሷል፤ ከፍታ 1,416 m።", "am")
    assert not any(ch.isdigit() for ch in am)
    assert "ሰባ ስድስት በመቶ" in am and "አንድ ሺህ አራት መቶ አሥራ ስድስት ሜትር" in am


def test_verbalize_handles_oromo_prefix_percent_and_ethiopic_units() -> None:
    assert sn.verbalize("dhiqama %76 hir'isa", "om") == "dhiqama dhibbeentaa torbaatamii jaha hir'isa"
    assert sn.verbalize("ዝናብ 756 ሚሜ", "am") == "ዝናብ ሰባት መቶ ሃምሳ ስድስት ሚሊ ሜትር"


def test_verbalize_reads_a_hyphen_between_numbers_as_a_range_not_a_minus() -> None:
    assert "hir'ina" not in sn.verbalize("8-10", "om")
    assert sn.verbalize("-3", "om") == "hir'ina sadii"


# ------------------------------------------------------------ local voice text
def test_local_voice_reads_numbers_as_words_in_lowercase() -> None:
    assert ls.prepare_text("Gochaan 76% hir'isa.", "om") == "gochaan dhibbeentaa torbaatamii jaha hir'isa."


def test_local_voice_splits_long_answers_into_sentences() -> None:
    text = "First sentence here. " + ("word " * 120) + "። Last one."
    pieces = ls._chunks(text, limit=100)
    assert pieces[0] == "First sentence here."
    assert all(len(p) <= 100 for p in pieces)


# ------------------------------------------------------------------- routing
@pytest.mark.parametrize(
    ("local", "openai", "expected"),
    [
        (True, {"stt": True, "tts": True}, {"en": "openai", "am": "local", "om": "local"}),
        (True, {"stt": False, "tts": False}, {"en": None, "am": "local", "om": "local"}),
        (False, {"stt": True, "tts": True}, {"en": "openai", "am": "openai", "om": "openai"}),
        (False, {"stt": False, "tts": False}, {"en": None, "am": None, "om": None}),
    ],
)
def test_provider_prefers_local_voice_for_amharic_and_oromo(
    monkeypatch: pytest.MonkeyPatch, local: bool, openai: dict[str, bool], expected: dict[str, str | None]
) -> None:
    make_client(monkeypatch, openai=openai, local=local)
    settings = speech_router.get_settings()
    import asyncio

    for lang, want in expected.items():
        assert asyncio.run(ss.provider("tts", lang, settings)) == want  # type: ignore[arg-type]


def test_status_reports_per_language_capability(monkeypatch: pytest.MonkeyPatch) -> None:
    client = make_client(monkeypatch, openai={"stt": False, "tts": False}, local=True)
    assert client.get("/speech/status").json() == {
        "stt": {"en": False, "am": True, "om": True},
        "tts": {"en": False, "am": True, "om": True},
    }


def test_status_reports_no_access_without_a_key_or_local_voice(monkeypatch: pytest.MonkeyPatch) -> None:
    client = make_client(monkeypatch, key="")
    off = {"en": False, "am": False, "om": False}
    assert client.get("/speech/status").json() == {"stt": off, "tts": off}


# ------------------------------------------------------------------- endpoints
def test_speech_endpoints_answer_503_when_no_engine_serves_the_language(monkeypatch: pytest.MonkeyPatch) -> None:
    client = make_client(monkeypatch, key="")
    r = client.post("/speech/transcribe?language=om", content=b"x", headers={"Content-Type": "audio/webm"})
    assert r.status_code == 503
    r = client.post("/speech/synthesize", json={"text": "Hello", "language": "om"})
    assert r.status_code == 503


def test_transcribe_returns_text_and_passes_the_language(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    async def fake(audio: bytes, content_type: str, language: str, settings: Settings) -> str:
        seen.update(audio=audio, content_type=content_type, language=language)
        return "ሰላም"

    monkeypatch.setattr(ss, "transcribe", fake)
    client = make_client(monkeypatch)
    r = client.post(
        "/speech/transcribe?language=am",
        content=b"\x1aE\xdf\xa3fake-webm",
        headers={"Content-Type": "audio/webm;codecs=opus"},
    )
    assert r.status_code == 200
    assert r.json() == {"text": "ሰላም", "language": "am"}
    assert seen["language"] == "am" and seen["audio"] == b"\x1aE\xdf\xa3fake-webm"


def test_local_transcription_runs_the_mms_recognizer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ls, "transcribe", lambda data, lang: f"{lang}:{len(data)}")
    client = make_client(monkeypatch, openai={"stt": False, "tts": False}, local=True)
    r = client.post("/speech/transcribe?language=om", content=b"abc", headers={"Content-Type": "audio/webm"})
    assert r.json() == {"text": "om:3", "language": "om"}


@pytest.mark.parametrize(
    ("headers", "body", "status"),
    [
        ({"Content-Type": "text/plain"}, b"x", 415),
        ({"Content-Type": "audio/webm"}, b"", 400),
    ],
)
def test_transcribe_rejects_bad_uploads(
    monkeypatch: pytest.MonkeyPatch, headers: dict[str, str], body: bytes, status: int
) -> None:
    client = make_client(monkeypatch)
    r = client.post("/speech/transcribe?language=en", content=body, headers=headers)
    assert r.status_code == status


def test_transcribe_rejects_oversized_recordings(monkeypatch: pytest.MonkeyPatch) -> None:
    client = make_client(monkeypatch)
    big = b"0" * (10 * 1024 * 1024 + 1)
    r = client.post("/speech/transcribe?language=en", content=big, headers={"Content-Type": "audio/webm"})
    assert r.status_code == 413


def test_transcribe_rejects_unknown_languages(monkeypatch: pytest.MonkeyPatch) -> None:
    client = make_client(monkeypatch)
    r = client.post("/speech/transcribe?language=fr", content=b"x", headers={"Content-Type": "audio/webm"})
    assert r.status_code == 422


def test_synthesize_returns_the_providers_audio(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake(text: str, language: str, settings: Settings) -> tuple[bytes, str]:
        assert language == "om"
        return b"RIFFfake-wav", "audio/wav"

    monkeypatch.setattr(ss, "synthesize", fake)
    client = make_client(monkeypatch)
    r = client.post("/speech/synthesize", json={"text": "Gochaalee", "language": "om"})
    assert r.status_code == 200
    assert r.headers["content-type"] == "audio/wav"
    assert r.content == b"RIFFfake-wav"


def test_local_synthesis_returns_wav(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, str] = {}

    def fake(text: str, lang: str) -> bytes:
        seen.update(text=text, lang=lang)
        return b"RIFF"

    monkeypatch.setattr(ls, "synthesize_wav", fake)
    client = make_client(monkeypatch, openai={"stt": False, "tts": False}, local=True)
    r = client.post("/speech/synthesize", json={"text": "**Mulch** reduces loss by 76% [1].", "language": "om"})
    assert r.status_code == 200 and r.headers["content-type"] == "audio/wav"
    assert seen == {"text": "Mulch reduces loss by 76%.", "lang": "om"}


def test_synthesize_maps_upstream_failure_to_502(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fail(text: str, language: str, settings: Settings) -> tuple[bytes, str]:
        raise ss.SpeechError("synthesis_failed")

    monkeypatch.setattr(ss, "synthesize", fail)
    client = make_client(monkeypatch)
    r = client.post("/speech/synthesize", json={"text": "Hello", "language": "en"})
    assert r.status_code == 502


def test_local_recognition_is_not_offered_until_the_model_is_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    client = make_client(monkeypatch, openai={"stt": False, "tts": False}, local=True)
    monkeypatch.setattr(ls, "asr_ready", lambda: False)
    body = client.get("/speech/status").json()
    assert body["stt"] == {"en": False, "am": False, "om": False}
    assert body["tts"] == {"en": False, "am": True, "om": True}