"""The frontend's component glossary must mirror practice_components.py (U1).

The UI composes localised practice names from the same 44 canonical
components and the same alias table the knowledge graph uses. If either side
drifts, a practice would render under a different name than the graph
reports it — so this test reads the TypeScript source and compares.
"""
from __future__ import annotations

import re
from pathlib import Path

from rag.graph.practice_components import ALIASES, CANONICAL_COMPONENTS

GLOSSARY = Path(__file__).resolve().parents[2] / "app" / "frontend" / "src" / "i18n" / "glossary.ts"


def _ts_table(name: str) -> str:
    source = GLOSSARY.read_text(encoding="utf-8")
    match = re.search(rf"export const {name}[^=]*=\s*\{{(.*?)\n\}};", source, re.S)
    assert match, f"{name} not found in glossary.ts"
    return match.group(1)


def test_component_alias_table_matches_python():
    body = _ts_table("COMPONENT_ALIASES")
    pairs = dict(re.findall(r'^\s{2}"?([^"\n:]+?)"?: "([^"]+)",?$', body, re.M))
    assert pairs == ALIASES


def test_component_display_table_covers_exactly_the_canonical_components():
    body = _ts_table("COMPONENTS")
    keys = re.findall(r'^\s{2}"?([^"\n:]+?)"?: \{', body, re.M)
    assert sorted(keys) == sorted(CANONICAL_COMPONENTS)
    assert len(keys) == 44
