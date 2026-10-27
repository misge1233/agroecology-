"""Backend message catalogs for the three UI languages (Phase U1).

Scope: the **deterministic** texts the API itself produces — chat
clarifications, social replies, error messages, the evidence-led narrative
fallback, and the explanation fallback/evidence-base sentences. Everything the
ML engine or the data contract emits (practice names, indicator keys, family
names, the ``effect`` string from ``recommend.py``) stays **English** on the
wire; the UI translates those for display from its own glossary.

Rules:

* ``en`` is the reference catalog and must reproduce the pre-U1 texts
  byte-for-byte (asserted in ``tests/test_i18n.py`` against a snapshot).
* ``am`` (Amharic, Ethiopic script) and ``om`` (Afaan Oromoo, Qubee) are
  **machine drafts** awaiting native review — see
  ``docs/i18n/TRANSLATION_STATUS.md``. A missing key falls back to ``en``
  rather than raising, so a half-reviewed catalog can never break a request.
* Numbers stay Western digits in all three languages: the numeric guardrail
  in ``explain_service`` matches ``\\d`` and is therefore script-independent.
"""
from __future__ import annotations

from typing import Any, Literal

from . import am, en, om

Language = Literal["en", "am", "om"]

LANGUAGES: tuple[str, ...] = ("en", "am", "om")
DEFAULT_LANGUAGE = "en"

#: Human-readable names, used in the LLM instruction and ``/metadata``.
LANGUAGE_NAMES: dict[str, str] = {
    "en": "English",
    "am": "Amharic (አማርኛ)",
    "om": "Afaan Oromoo",
}

_CATALOGS: dict[str, dict[str, str]] = {
    "en": en.STRINGS,
    "am": am.STRINGS,
    "om": om.STRINGS,
}


def normalize_language(value: Any) -> str:
    """Coerce any input to a supported language code (default ``en``)."""
    code = str(value or "").strip().lower()[:2]
    return code if code in _CATALOGS else DEFAULT_LANGUAGE


def catalog(language: str) -> dict[str, str]:
    """The raw string table for a language."""
    return _CATALOGS[normalize_language(language)]


def t(language: str, key: str, **kwargs: Any) -> str:
    """Translate ``key`` for ``language``, formatting ``kwargs`` into it.

    Falls back to the English string when the key is missing from the
    requested catalog, and raises ``KeyError`` only if English lacks it too —
    that is a programming error, not a translation gap.
    """
    table = catalog(language)
    template = table.get(key)
    if template is None:
        template = en.STRINGS[key]
    return template.format(**kwargs) if kwargs else template


def term(language: str, kind: str, value: str | None) -> str:
    """Display form of a data-contract term (indicator, family, AEZ belt…).

    ``kind`` is one of ``indicator``, ``family``, ``aez``, ``direction``.
    Unknown values pass through unchanged, so a new belt or indicator in the
    data can never crash a reply — it just shows in English.
    """
    if value is None:
        return ""
    return catalog(language).get(f"{kind}.{value}") or en.STRINGS.get(f"{kind}.{value}") or value


def reply_instruction(language: str) -> str:
    """The one line appended to every LLM system prompt (U1 §D)."""
    return t(language, "prompt.reply_in")
