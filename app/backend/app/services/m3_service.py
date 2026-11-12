"""The E7 decision behind the API: ``ADVISOR_ENGINE=m3`` (``m3_gate``; additive, never default).

Wraps :class:`model.m3.serve.GateRanker` over the M1 v2 artifact that ``m1_service`` loads:
M1 v2 supplies every number, interval, lead source and citation; for thin-evidence requests
(median distinct training study groups per candidate below the served threshold) the order
comes from ``gpt-4.1-mini`` asked with the evaluated no-evidence prompt. The call is cached on
disk per (rendered context, objective, crop, candidate set), limited to ``M3_TIMEOUT_SECONDS``
(default 8 s) with the M1 v2 order as fallback, its cost written to a ledger and logged, and
the spend capped by ``M3_BUDGET_USD``. Without an API key the M1 v2 order is served.

Fail fast: with ``ADVISOR_ENGINE=m3`` a missing gate config or M1 v2 artifact aborts startup.
"""
from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any

from app.config import get_settings

logger = logging.getLogger(__name__)

ENGINE = "m3"
_LOCK = threading.Lock()
_RANKER: Any = None
_KEY: tuple | None = None


def enabled(settings: Any = None) -> bool:
    return str((settings or get_settings()).advisor_engine).strip().lower() == ENGINE


def _dir(value: str, settings: Any) -> Path:
    p = Path(value)
    return p if p.is_absolute() else (settings.backend_root / p).resolve()


def ranker(settings: Any = None, *, m1_engine: Any = None, client: Any = None) -> Any:
    """The cached :class:`GateRanker`; ``m1_engine``/``client`` are injected by tests."""
    global _RANKER, _KEY
    s = settings or get_settings()
    key = (str(_dir(s.m3_artifact_dir, s)), id(m1_engine) if m1_engine is not None else None)
    with _LOCK:
        # a call without a client reuses the cached ranker of the same gate and engine (the
        # request path never passes one); an explicit client (tests) rebuilds it
        if _RANKER is not None and client is None and (_KEY == key or (m1_engine is not None and _KEY[0] == key[0]
                                                                       and _RANKER.m1 is m1_engine)):
            return _RANKER
        from app.services import m1_service
        from model.m2.client import ChatClient, Ledger
        from model.m2.run import maps_from_taxonomy
        from model.m3.serve import GateRanker, load_config
        from pipelines.taxonomy import taxonomy_io as tio

        cfg = load_config(_dir(s.m3_artifact_dir, s))
        eng = m1_engine if m1_engine is not None else m1_service.load(s)
        if client is None:
            cache = _dir(s.m3_cache_dir, s)
            client = ChatClient(cfg["llm_model"], budget_usd=float(s.m3_budget_usd), cache_dir=cache,
                                ledger=Ledger(cache / "ledger.jsonl"), api_key=s.openai_api_key or None,
                                timeout=float(s.m3_timeout_seconds), max_attempts=1)
        _RANKER = GateRanker(eng, cfg, client, maps_from_taxonomy(tio.Taxonomy.load()), timeout_s=float(s.m3_timeout_seconds))
        _KEY = key
        logger.info("Advisory engine m3 (gate threshold %s, %s) ready", cfg["threshold"], cfg["llm_model"])
        return _RANKER


def reset() -> None:
    global _RANKER, _KEY
    with _LOCK:
        _RANKER, _KEY = None, None


def warmup(settings: Any = None) -> None:
    """Fail fast at startup when ``ADVISOR_ENGINE=m3`` and the config or artifact is missing."""
    s = settings or get_settings()
    if enabled(s):
        ranker(s)


def info(settings: Any = None) -> dict[str, Any]:
    s = settings or get_settings()
    if not enabled(s):
        return {}
    try:
        from model.m3.serve import load_config

        cfg = load_config(_dir(s.m3_artifact_dir, s))
        return {"gate_threshold": cfg.get("threshold"), "llm_model": cfg.get("llm_model"),
                "timeout_s": float(s.m3_timeout_seconds), "decision": cfg.get("decision")}
    except Exception:  # noqa: BLE001 - informational only
        return {}
