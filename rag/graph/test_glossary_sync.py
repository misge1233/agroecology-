"""The frontend's component glossary must mirror practice_components.py (U1).

The UI composes localised practice names from the same 44 canonical
components and the same alias table the knowledge graph uses. If either side
drifts, a practice would render under a different name than the graph
reports it — so this test reads the TypeScript source and compares.
"""
from __future__ import annotations

import json
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
    pairs = dict(re.findall(r'^[ ]{2}"?([^"\n:]+?)"?: "([^"]+)",?$', body, re.M))
    assert pairs == ALIASES


def _component_display_keys() -> list[str]:
    """Keys of the COMPONENTS table, wherever glossary.ts keeps it.

    Since U9 (1 Nov 2026) ``glossary.ts`` imports the table from
    ``component-names.json`` (``export const COMPONENTS: Record<string, Tri> =
    COMPONENT_NAMES;``) instead of spelling it out; the regex of the original test
    only knew the literal form, so the test, not the data, was stale (E4 Part 0).
    """
    source = GLOSSARY.read_text(encoding="utf-8")
    alias = re.search(r"export const COMPONENTS[^=]*=\s*([A-Za-z_][A-Za-z0-9_]*);", source)
    if alias:
        imported = re.search(rf'import {alias.group(1)} from "\./([^"]+\.json)";', source)
        assert imported, f"COMPONENTS aliases {alias.group(1)} but no JSON import of that name was found"
        table = json.loads((GLOSSARY.parent / imported.group(1)).read_text(encoding="utf-8"))
        assert all(isinstance(v, dict) and {"en", "am", "om"} <= set(v) for v in table.values())
        return list(table)
    body = _ts_table("COMPONENTS")
    return re.findall(r'^[ ]{2}"?([^"\n:]+?)"?: \{', body, re.M)


def test_component_display_table_covers_exactly_the_canonical_components():
    keys = _component_display_keys()
    assert sorted(keys) == sorted(CANONICAL_COMPONENTS)
    assert len(keys) == 44
