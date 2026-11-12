"""Methodology 2: LLM evidence reasoning over masked evidence cards (E6).

The engine asks a language model to rank the candidate practices of a harness query from
short evidence cards (one pooled contrast per study cell, built from the rows the fold's
mask allows), with retrieved passages and graph facts in the richer variants. The model
ranks and cites card ids; every effect estimate and interval is computed by code from the
cited cards (doctrine 1: the LLM never produces a number shown to anyone).

Modules: :mod:`cards` (cards and their per-query selection), :mod:`knowledge` (passages
and graph facts), :mod:`prompt` (the fixed prompt, version and output schema),
:mod:`client` (the cached, counted and capped API client), :mod:`engine` (the harness
engine), :mod:`run` (dry run, prefetch, harness runs, stability), :mod:`report`.
"""
from __future__ import annotations

from pathlib import Path

M2_DIR = Path(__file__).resolve().parent
CACHE_DIR = M2_DIR / "cache"
PRICES_PATH = M2_DIR / "prices.yaml"
