"""E7 hybrids of Methodology 1 v2 and the zero-evidence LLM ranking (``m3_stack``, ``m3_gate``).

Every number, interval and citation comes from M1 v2 (conformal, evidence); the LLM ranking
(``gpt-4.1-mini`` ``m2_zero`` from E6, fold-independent, no new calls) only influences the
order. All choices are made on M1 v2's inner out-of-fold predictions of the training
queries (nested), never on the outer fold.
"""
from __future__ import annotations
