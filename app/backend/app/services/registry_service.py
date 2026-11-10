"""Challenge/objective registry (Phase E1, brief D2).

Serves ``registry_<CC>.json`` written by ``pipelines/evidence/build_registry.py``.
The file is read once and cached; the cache is refreshed when the file's
modification time changes, so a rebuilt registry is picked up without a restart.

Fail fast, degrade gracefully: an unknown country is a 404; a known country
(``countries/<CC>.yaml`` exists) whose registry has not been built is a 503 with
the command that builds it; the rest of the API is unaffected either way.
"""
from __future__ import annotations

import json
import logging
import re
import threading
from pathlib import Path
from typing import Any

from app.config import get_settings

logger = logging.getLogger(__name__)

_CODE_RE = re.compile(r"^[A-Za-z]{2}$")
_LOCK = threading.Lock()
_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}


class UnknownCountry(LookupError):
    """No country configuration and no registry for this code."""


class RegistryUnavailable(RuntimeError):
    """The country is configured but its registry file is missing or unreadable."""


def _paths(code: str) -> tuple[Path, Path]:
    s = get_settings()
    return s.resolved_evidence_dir / f"registry_{code}.json", s.resolved_countries_dir / f"{code}.yaml"


def get_registry(country: str) -> dict[str, Any]:
    """Registry dict for ``country`` (ISO alpha-2, case-insensitive)."""
    if not _CODE_RE.match(country or ""):
        raise UnknownCountry(country)
    code = country.upper()
    registry_file, country_file = _paths(code)
    if not registry_file.exists():
        if country_file.exists():
            raise RegistryUnavailable(
                f"Registry for {code} is not built. Run `python pipelines/evidence/build_registry.py --country {code}`."
            )
        raise UnknownCountry(code)
    mtime = registry_file.stat().st_mtime
    with _LOCK:
        hit = _CACHE.get(code)
        if hit and hit[0] == mtime:
            return hit[1]
        try:
            data = json.loads(registry_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.error("registry %s unreadable: %s", registry_file, exc)
            raise RegistryUnavailable(f"Registry for {code} could not be read.") from exc
        _CACHE[code] = (mtime, data)
        logger.info("registry %s loaded (%d challenges)", code, len(data.get("challenges", [])))
        return data


def clear_cache() -> None:
    """Drop cached registries (tests)."""
    with _LOCK:
        _CACHE.clear()
