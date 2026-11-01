"""One display-rounding rule for every number a user sees (U9, guard v2).

The backend (chat summaries, the numeric guard) and the frontend
(``src/lib/numbers.ts``) round the same way, so a value written in a sentence
always matches the value shown on a card. Both implementations are pinned by
the shared fixture ``app/frontend/src/lib/number-format.fixture.json``.

Rule: half away from zero; magnitudes of 10 or more to whole numbers, smaller
ones to one decimal (``-79.4 -> -79``, ``2.34 -> 2.3``, ``-0.05 -> -0.1``).
"""
from __future__ import annotations

import math
from typing import Any, Literal

Source = Literal["model", "study", "passage", "context", "count"]


def round_half_away(value: float, decimals: int = 0) -> float:
    """Round half away from zero (Python's ``round`` is banker's rounding)."""
    factor = 10 ** decimals
    return math.copysign(math.floor(abs(value) * factor + 0.5) / factor, value)


def display_value(value: float) -> float:
    """The value as shown: whole numbers from 10 up, one decimal below."""
    v = float(value)
    out = round_half_away(v, 0) if abs(v) >= 10 else round_half_away(v, 1)
    return 0.0 if out == 0 else out


def display_text(value: float) -> str:
    """``display_value`` as text without a trailing ``.0`` (``80``, ``2.3``)."""
    v = display_value(value)
    return str(int(v)) if float(v).is_integer() else f"{v:.1f}"


def number(value: float, unit: str | None, source: Source, ref: str | None = None) -> dict[str, Any]:
    """A provenance object for the wire: ``{value, unit, source, ref, display}``."""
    return {"value": float(value), "unit": unit, "source": source, "ref": ref, "display": display_text(value)}
