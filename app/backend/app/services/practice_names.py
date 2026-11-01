"""Display names of frozen practice labels in en/am/om (U9, D10/D11).

Chat answers are written by the backend, so they need the same practice names
the UI shows ("Mulch + Water harvesting", not the frozen data-contract string
"Mulch-Water Harvesting"; translated in am/om). Single source of truth: the
UI's ``app/frontend/src/i18n/component-names.json``; component splitting is
the canonical ``rag.graph.practice_components.decompose`` (the UI mirrors it).
A missing names file degrades to the frozen label — never an error.
"""
from __future__ import annotations

import json
import logging
import sys
from functools import lru_cache
from typing import Any

from app.config import get_settings

logger = logging.getLogger(__name__)

JOINER = " + "


@lru_cache(maxsize=1)
def _names() -> dict[str, dict[str, str]]:
    path = get_settings().backend_root.parent / "frontend" / "src" / "i18n" / "component-names.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # optional: fall back to the frozen labels
        logger.warning("Component names unavailable (%s) — frozen practice labels are used.", exc)
        return {}


def _decompose(practice: str) -> tuple[str, ...]:
    repo_root = get_settings().backend_root.parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from rag.graph.practice_components import decompose

    return decompose(practice)


def practice_name(practice: str | None, language: str = "en") -> str:
    """Localised display name of a frozen ``CSA_practices`` string."""
    if not practice:
        return ""
    names = _names()
    if not names:
        return practice
    try:
        parts = _decompose(practice)
    except Exception:  # unknown shape: show as sent
        return practice
    out = []
    for comp in parts:
        entry: dict[str, Any] = names.get(comp) or {}
        out.append(entry.get(language) or entry.get("en") or comp)
    return JOINER.join(out) if out else practice
