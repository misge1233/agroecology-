"""Local voice for Amharic and Afaan Oromoo (Phase U6), on the backend CPU.

Meta's MMS models (CC-BY-NC-4.0, research use):

* text-to-speech: one VITS voice per language, ``facebook/mms-tts-amh`` and
  ``facebook/mms-tts-orm`` (~145 MB each, 16 kHz);
* speech-to-text: ``facebook/mms-1b-all`` with the ``amh`` / ``orm`` language
  adapter (~3.9 GB, shared by both languages).

Optional: needs ``requirements-voice.txt``. ``available()`` is False without
those packages and the router falls back to OpenAI audio or to the browser.
Models load lazily (or in a background thread at startup, see ``preload``)
and are reused; inference runs in a worker thread so the event loop stays free.

Spoken text is the answer itself: formatting removed (``clean_for_speech``),
numbers spelled out in the language (``speech_numbers.verbalize``), and for
Amharic romanized with ``uroman`` because that voice reads romanized input.
No word or value is changed.
"""
from __future__ import annotations

import importlib.util
import io
import logging
import re
import threading
import wave
from functools import lru_cache
from typing import Any, Literal

from app.services.speech_numbers import verbalize

logger = logging.getLogger(__name__)

LocalLang = Literal["am", "om"]
TTS_MODELS: dict[str, str] = {"am": "facebook/mms-tts-amh", "om": "facebook/mms-tts-orm"}
ASR_MODEL = "facebook/mms-1b-all"
ASR_ADAPTERS: dict[str, str] = {"am": "amh", "om": "orm"}
SAMPLE_RATE = 16_000

_asr_lock = threading.Lock()
_tts_lock = threading.Lock()
_current_adapter: str | None = None


def available() -> bool:
    """True when the optional packages for local voice are installed."""
    return all(importlib.util.find_spec(m) is not None for m in ("torch", "transformers", "av", "uroman"))


def supports(lang: str) -> bool:
    return lang in TTS_MODELS


def asr_ready() -> bool:
    """True when the recognizer is loaded, or fully downloaded so it loads in seconds.

    Until then local speech-to-text is not offered (``/speech/status``), so a
    recording never waits on a multi-gigabyte download.
    """
    if _asr.cache_info().currsize:
        return True
    try:
        from huggingface_hub import try_to_load_from_cache

        cached = try_to_load_from_cache(ASR_MODEL, "model.safetensors")
        return isinstance(cached, str)
    except Exception:  # pragma: no cover - depends on the hub package
        return False


# ------------------------------------------------------------------ models
@lru_cache(maxsize=len(TTS_MODELS))
def _tts(lang: str) -> tuple[Any, Any]:
    from transformers import AutoTokenizer, VitsModel

    logger.info("Loading local TTS voice %s", TTS_MODELS[lang])
    tokenizer = AutoTokenizer.from_pretrained(TTS_MODELS[lang])
    model = VitsModel.from_pretrained(TTS_MODELS[lang]).eval()
    return tokenizer, model


@lru_cache(maxsize=1)
def _asr() -> tuple[Any, Any]:
    from transformers import AutoProcessor, Wav2Vec2ForCTC

    logger.info("Loading local speech recognizer %s", ASR_MODEL)
    processor = AutoProcessor.from_pretrained(ASR_MODEL)
    model = Wav2Vec2ForCTC.from_pretrained(ASR_MODEL).eval()
    return processor, model


@lru_cache(maxsize=1)
def _romanizer() -> Any:
    import uroman

    return uroman.Uroman()


def preload(languages: list[str], with_asr: bool) -> None:
    """Warm the models in a daemon thread so the first request is not slow."""

    def run() -> None:
        try:
            for lang in languages:
                if supports(lang):
                    _tts(lang)
            if with_asr:
                _asr()
            logger.info("Local voice ready for %s (recognizer: %s)", ",".join(languages), with_asr)
        except Exception as exc:  # pragma: no cover - depends on network/cache
            logger.warning("Local voice preload failed: %s", exc)

    threading.Thread(target=run, name="local-voice-preload", daemon=True).start()


# --------------------------------------------------------------- synthesis
_SENTENCE = re.compile(r"(?<=[.!?።])\s+")


def _chunks(text: str, limit: int = 280) -> list[str]:
    """Sentence-sized pieces: the VITS voices degrade on very long inputs."""
    out: list[str] = []
    for sentence in _SENTENCE.split(text):
        sentence = sentence.strip()
        while len(sentence) > limit:
            cut = sentence.rfind(" ", 0, limit)
            cut = cut if cut > limit // 2 else limit
            out.append(sentence[:cut].strip())
            sentence = sentence[cut:].strip()
        if sentence:
            out.append(sentence)
    return out


def prepare_text(text: str, lang: LocalLang) -> str:
    """What the voice actually reads: numbers as words, Amharic romanized."""
    spoken = verbalize(text, lang)
    if lang == "am":
        spoken = _romanizer().romanize_string(spoken)
    return spoken.lower()


def synthesize_wav(text: str, lang: LocalLang) -> bytes:
    """Blocking: cleaned answer text in, 16 kHz mono WAV bytes out."""
    import numpy as np
    import torch

    tokenizer, model = _tts(lang)
    pieces = [p for p in _chunks(text) if p]
    pause = np.zeros(int(SAMPLE_RATE * 0.28), dtype=np.float32)
    audio: list[Any] = []
    with _tts_lock, torch.inference_mode():
        for piece in pieces:
            inputs = tokenizer(prepare_text(piece, lang), return_tensors="pt")
            if inputs["input_ids"].shape[-1] == 0:
                continue
            wav = model(**inputs).waveform[0].cpu().numpy().astype(np.float32)
            audio.extend([wav, pause])
    if not audio:
        raise ValueError("nothing_to_say")
    samples = np.clip(np.concatenate(audio), -1.0, 1.0)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(model.config.sampling_rate)
        out.writeframes((samples * 32767).astype(np.int16).tobytes())
    return buf.getvalue()


# ------------------------------------------------------------- recognition
def decode_audio(data: bytes) -> Any:
    """Any browser recording (webm/opus, mp4, ogg, wav) to 16 kHz mono float32."""
    import av
    import numpy as np

    frames: list[Any] = []
    with av.open(io.BytesIO(data)) as container:
        resampler = av.AudioResampler(format="s16", layout="mono", rate=SAMPLE_RATE)
        for frame in container.decode(audio=0):
            for out in resampler.resample(frame):
                frames.append(out.to_ndarray().reshape(-1))
        for out in resampler.resample(None):
            frames.append(out.to_ndarray().reshape(-1))
    if not frames:
        return np.zeros(0, dtype=np.float32)
    return np.concatenate(frames).astype(np.float32) / 32768.0


def transcribe(data: bytes, lang: LocalLang) -> str:
    """Blocking: one recording to text with the language's MMS adapter."""
    global _current_adapter
    import torch

    samples = decode_audio(data)
    if samples.size < SAMPLE_RATE // 4:
        return ""
    processor, model = _asr()
    adapter = ASR_ADAPTERS[lang]
    with _asr_lock, torch.inference_mode():
        if _current_adapter != adapter:
            processor.tokenizer.set_target_lang(adapter)
            model.load_adapter(adapter)
            _current_adapter = adapter
        inputs = processor(samples, sampling_rate=SAMPLE_RATE, return_tensors="pt")
        logits = model(**inputs).logits
        ids = torch.argmax(logits, dim=-1)[0]
        text = processor.decode(ids)
    return text.strip()
