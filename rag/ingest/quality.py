"""Chunk-quality scoring for the Tier-2 guidance corpus (Phase P9, from P8).

GARDIAN documents are OCR'd reports and books; ~11 % of the 19,997 guidance
chunks are tables, reference lists or OCR-shattered text (reviewer sample,
25 Oct 2026). Such chunks must never become a knowledge candidate or an LLM
passage. This module scores a chunk from cheap, documented text statistics;
``chunk_guidance.py --min-quality`` gates new chunks and
``prune_collection.py`` removes failing ids from an existing collection.

Tier 1 (``era_corpus``) is NEVER filtered — it is the frozen, P3-evaluated
evidence corpus.

Statistics (all on the raw chunk text):

* ``alpha_ratio``      share of alphabetic characters (OCR noise, tables and
                       numeric dumps lower it);
* ``short_token_share`` share of tokens with <= 2 alphanumeric characters
                       (shattered words, cell separators, page furniture);
* ``caps_share``       share of tokens longer than one character written in
                       all capitals (headings, tables of acronyms);
* ``digit_share``      share of digit characters (tables, reference years);
* ``mean_word_len``    mean token length (OCR fragments pull it down,
                       URL/formula runs push it up);
* ``reference_pattern`` density of bibliography cues — "(19xx)" / "et al." /
                       "pp." / "Vol." / DOI strings — per 100 tokens;
* ``table_pattern``    density of table cues — runs of numbers separated by
                       whitespace, "Table n", "%" columns — per 100 tokens;
* ``bibliography_pattern`` density of author-initial cues ("Abera, W.",
                       "A.B.", URLs, "pp.", "Vol.") per 100 tokens — catches
                       reference lists written without parenthesised years;
* ``dot_leader_pattern`` density of "....." runs per 100 tokens — tables of
                       contents and lists of figures.

``score`` is 1.0 minus weighted penalties, clipped to [0, 1]; ``flags`` names
every statistic that crossed its threshold. The default gate (``MIN_QUALITY
= 0.55``) was calibrated on the labelled sample in ``quality_sample.csv``
(see the P9 report): precision on "garbage" ≥ 95 % at that threshold.
"""
from __future__ import annotations

import re
import statistics
from typing import Any

MIN_QUALITY = 0.55

_ALNUM_RE = re.compile(r"[^0-9A-Za-z]")
_REF_RE = re.compile(
    r"\(\s*(?:19|20)\d{2}[a-z]?\s*\)|\bet al\.|\bpp\.\s*\d|\bVol\.\s*\d|\bdoi:|10\.\d{4,}/|\bIn:\s|\bed(?:s)?\.\s",
    re.IGNORECASE,
)
_TABLE_RE = re.compile(
    r"(?:\b\d+(?:[.,]\d+)?\s+){3,}\d+(?:[.,]\d+)?\b|\bTable\s+\d|\bFig(?:ure|\.)\s*\d|\s\|\s|\t",
    re.IGNORECASE,
)
_NUMERIC_TOKEN_RE = re.compile(r"^[\d.,%()\-–/]+$")
_BIB_RE = re.compile(
    r"\b[A-Z][a-z]+,\s(?:[A-Z]\.\s?){1,3}|\b[A-Z]\.\s?[A-Z]\.|\bhttps?://|\bdoi\b|\bpp\.|\bVol\.|\bJ\.\s[A-Z]"
)
_DOT_LEADER_RE = re.compile(r"\.{6,}|(?:\.\s){6,}|_{6,}")

#: statistic -> (threshold, direction, penalty). direction "<" means a value
#: BELOW the threshold is bad; ">" means above.
THRESHOLDS: dict[str, tuple[float, str, float]] = {
    "alpha_ratio": (0.70, "<", 0.45),
    "short_token_share": (0.35, ">", 0.35),
    "caps_share": (0.30, ">", 0.50),
    "digit_share": (0.12, ">", 0.25),
    "mean_word_len": (3.6, "<", 0.25),
    "reference_pattern": (2.5, ">", 0.30),
    "table_pattern": (2.0, ">", 0.30),
    "numeric_token_share": (0.30, ">", 0.30),
    "bibliography_pattern": (7.0, ">", 0.50),
    "dot_leader_pattern": (2.5, ">", 0.50),
}


def text_stats(text: str) -> dict[str, float]:
    """The raw statistics behind the score (exposed for calibration)."""
    text = text or ""
    tokens = text.split()
    n = max(1, len(tokens))
    chars = max(1, len(text))
    alnum = [_ALNUM_RE.sub("", tok) for tok in tokens]
    return {
        "n_tokens": float(len(tokens)),
        "alpha_ratio": sum(c.isalpha() for c in text) / chars,
        "short_token_share": sum(1 for a in alnum if len(a) <= 2) / n,
        "caps_share": sum(1 for tok in tokens if len(tok) > 1 and tok.isupper() and tok.isalpha()) / n,
        "digit_share": sum(c.isdigit() for c in text) / chars,
        "mean_word_len": statistics.fmean(len(tok) for tok in tokens) if tokens else 0.0,
        "reference_pattern": 100.0 * len(_REF_RE.findall(text)) / n,
        "table_pattern": 100.0 * len(_TABLE_RE.findall(text)) / n,
        "numeric_token_share": sum(1 for tok in tokens if _NUMERIC_TOKEN_RE.match(tok)) / n,
        "bibliography_pattern": 100.0 * len(_BIB_RE.findall(text)) / n,
        "dot_leader_pattern": 100.0 * len(_DOT_LEADER_RE.findall(text)) / n,
    }


def chunk_quality(text: str) -> dict[str, Any]:
    """``{"score": float in [0, 1], "flags": [...], "stats": {...}}``.

    Deterministic and dependency-free, so it runs in the backend request
    path (knowledge candidates), the chunker and the prune tool alike.
    """
    stats = text_stats(text)
    flags: list[str] = []
    penalty = 0.0
    for name, (threshold, direction, weight) in THRESHOLDS.items():
        value = stats[name]
        bad = value < threshold if direction == "<" else value > threshold
        if bad:
            flags.append(name)
            # graded: how far past the threshold, capped at the full weight
            if direction == "<":
                excess = (threshold - value) / threshold if threshold else 1.0
            else:
                excess = (value - threshold) / threshold if threshold else 1.0
            penalty += weight * min(1.0, 0.5 + excess)
    if stats["n_tokens"] < 20:
        flags.append("too_short")
        penalty += 0.5
    score = max(0.0, min(1.0, 1.0 - penalty))
    return {"score": round(score, 3), "flags": flags, "stats": {k: round(v, 4) for k, v in stats.items()}}


def is_garbage(text: str, min_quality: float = MIN_QUALITY) -> bool:
    return chunk_quality(text)["score"] < min_quality
