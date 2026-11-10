"""Shared pytest configuration for ``pipelines/`` (Phase E1).

Registers the ``data`` marker: tests that need the raw data files (ERA CSV,
CSA workbook, Habtamu export, catalogue docx). They skip themselves when the
files are absent, so ``python -m pytest pipelines -q`` runs anywhere.
"""
from __future__ import annotations


def pytest_configure(config) -> None:
    config.addinivalue_line("markers", "data: needs the raw data files; skipped when they are absent")
