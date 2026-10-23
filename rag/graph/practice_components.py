"""Decompose the frozen ``CSA_practices`` labels into atomic components.

``CSA_practices`` is a FROZEN data-contract column (CLAUDE.md doctrine 4):
100 distinct strings, many of them combinations written with ``-`` as the
join character, e.g. ``Biochar-Inorganic Fertilizer-Organic Fertilizer``.
This module adds a NEW DERIVED LAYER on top of it — it never rewrites the
dataset:

1. **Split** a practice label on ``-`` into raw component strings, except
   for the literals in :data:`PROTECTED_COMPONENTS`, whose names contain a
   hyphen of their own (``In-situ water harvesting`` must NOT become
   ``In`` + ``situ water harvesting``). Labels with no ``-`` — including
   ``Intercropping or Rotation`` — stay a single component.
2. **Normalize** each raw string to a canonical component label via
   :data:`ALIASES`, which absorbs the case and spelling differences between
   the two data sources (ERA Title Case vs CSA lower case) and the typos
   carried in the frozen strings (``Drought tolerrant crops``,
   ``organic amedements``).

Scope of aliasing (deliberate, see ``rag/graph/README.md``): only
case/spelling variants of the SAME label are merged. Semantically adjacent
but distinctly named practices from the two sources — ``Organic Fertilizer``
(ERA) vs ``Organic Amendments`` (CSA), ``Reduced Tillage`` (ERA) vs
``Conservation Tillage`` (CSA) — are kept apart here and are instead related
downstream by the WOCAT crosswalk, which maps both onto the same SLM
measures. Merging them is a research judgement for the owner, not something
this module should decide silently.

Measured on ``data/processed/CSA_ERA_final_model_ready.csv`` (23 Oct 2026):
100 practices -> 46 raw ``-``-split tokens -> 45 after protecting
``In-situ water harvesting`` -> **44 canonical components**.
"""
from __future__ import annotations

from collections.abc import Iterable

# Practice labels whose own name contains the split character. Matched
# case-insensitively against the whole label or against a segment of it
# BEFORE splitting, so the hyphen inside them is never treated as a join.
PROTECTED_COMPONENTS: tuple[str, ...] = ("In-situ water harvesting",)

SPLIT_CHAR = "-"

#: raw component string (lower-cased, whitespace-collapsed) -> canonical label.
#: Every raw token observed in the frozen dataset appears here, so
#: ``build_graph.py`` can assert full coverage and fail loudly on new data.
ALIASES: dict[str, str] = {
    # --- ERA-source components (already Title Case) -----------------------
    "agroforestry fallow": "Agroforestry Fallow",
    "agroforestry pruning": "Agroforestry Pruning",
    "alleycropping": "Alleycropping",
    "biochar": "Biochar",
    "crop residue incorporation": "Crop Residue Incorporation",
    "crop rotation": "Crop Rotation",
    "exclosure": "Exclosure",
    "feed addition": "Feed Addition",
    "feed processing": "Feed Processing",
    "feed substitution": "Feed Substitution",
    "improved fallow": "Improved Fallow",
    "improved varieties": "Improved Varieties",
    "inorganic fertilizer": "Inorganic Fertilizer",
    "inorganic fertilizer reduction": "Inorganic Fertilizer Reduction",
    "intercropping": "Intercropping",
    "intercropping or rotation": "Intercropping or Rotation",
    "mulch": "Mulch",
    "multistrata agroforestry": "Multistrata Agroforestry",
    "organic fertilizer": "Organic Fertilizer",
    "other agroforestry": "Other Agroforestry",
    "parklands": "Parklands",
    "pasture management": "Pasture Management",
    "reduced tillage": "Reduced Tillage",
    "supplemental irrigation": "Supplemental Irrigation",
    "water harvesting": "Water Harvesting",
    "ph control": "pH Control",
    # --- cross-source case variants ---------------------------------------
    # ERA writes "Deficit Irrigation", CSA writes "Deficit irrigation";
    # same practice, so they collapse to one component.
    "deficit irrigation": "Deficit Irrigation",
    # --- CSA-source components (lower case in the frozen strings) ---------
    "animal feed management": "Animal Feed Management",
    "biological swc practices": "Biological SWC Practices",
    "conservation tillage": "Conservation Tillage",
    "drip irrigation": "Drip Irrigation",
    "furrow irrigation": "Furrow Irrigation",
    "grazing management": "Grazing Management",
    "in-situ water harvesting": "In-situ Water Harvesting",
    "isfm": "ISFM",
    "iwm": "IWM",
    "physical swc measures": "Physical SWC Measures",
    "physical + biological swc practices": "Physical + Biological SWC Practices",
    "weeding": "Weeding",
    # --- CSA typos / local spellings carried in the frozen strings --------
    "drought tolerrant crops": "Drought Tolerant Crops",       # sic: "tolerrant"
    "organic amedements": "Organic Amendments",                # sic: "amedements"
    "agronomic/biological swcp": "Agronomic/Biological SWC Practices",
    "furrow irrigation_alternate": "Alternate Furrow Irrigation",
    "overhead irrigation with mulching": "Overhead Irrigation with Mulching",
}

#: Raw tokens that are known typos/local spellings rather than plain case
#: differences — reported by ``build_graph.py`` and the phase report so the
#: owner can see exactly what was normalized.
TYPO_ALIASES: tuple[str, ...] = (
    "drought tolerrant crops",
    "organic amedements",
    "agronomic/biological swcp",
    "furrow irrigation_alternate",
)


def _clean(text: str) -> str:
    """Collapse whitespace and strip — the only cosmetic change made."""
    return " ".join(str(text).split())


def split_practice(label: str) -> tuple[str, ...]:
    """Split one frozen ``CSA_practices`` label into raw component strings.

    Splits on ``-`` but keeps every literal in :data:`PROTECTED_COMPONENTS`
    intact:

    >>> split_practice("Biochar-Inorganic Fertilizer-Organic Fertilizer")
    ('Biochar', 'Inorganic Fertilizer', 'Organic Fertilizer')
    >>> split_practice("In-situ water harvesting")
    ('In-situ water harvesting',)
    >>> split_practice("Intercropping or Rotation")
    ('Intercropping or Rotation',)
    """
    text = _clean(label)
    placeholders: dict[str, str] = {}
    for i, protected in enumerate(PROTECTED_COMPONENTS):
        token = f"\x00{i}\x00"
        lowered = text.lower()
        start = lowered.find(protected.lower())
        while start != -1:
            text = text[:start] + token + text[start + len(protected):]
            placeholders[token] = protected
            lowered = text.lower()
            start = lowered.find(protected.lower())
    parts: list[str] = []
    for raw in text.split(SPLIT_CHAR):
        piece = _clean(raw)
        for token, protected in placeholders.items():
            piece = piece.replace(token, protected)
        if piece:
            parts.append(piece)
    return tuple(parts)


def normalize_component(raw: str) -> str:
    """Map one raw component string to its canonical label.

    Unknown strings are returned whitespace-cleaned but otherwise unchanged,
    so new data degrades gracefully; ``build_graph.py`` reports them.

    >>> normalize_component("Deficit irrigation")
    'Deficit Irrigation'
    >>> normalize_component("organic amedements")
    'Organic Amendments'
    """
    cleaned = _clean(raw)
    return ALIASES.get(cleaned.lower(), cleaned)


def decompose(label: str) -> tuple[str, ...]:
    """Frozen practice label -> ordered, de-duplicated canonical components.

    >>> decompose("Biochar-Inorganic Fertilizer-Organic Fertilizer")
    ('Biochar', 'Inorganic Fertilizer', 'Organic Fertilizer')
    """
    seen: dict[str, None] = {}
    for raw in split_practice(label):
        seen.setdefault(normalize_component(raw), None)
    return tuple(seen)


def is_known(raw: str) -> bool:
    """True when ``raw`` is a component string this module recognises."""
    return _clean(raw).lower() in ALIASES


def alias_clusters(raw_tokens: Iterable[str]) -> dict[str, list[str]]:
    """Canonical label -> the distinct raw spellings observed for it (>1 only).

    Takes the raw tokens AS WRITTEN in the data rather than reading
    :data:`ALIASES`, because case-only variants (``Deficit Irrigation`` /
    ``Deficit irrigation``) share a single alias key and would otherwise be
    invisible. This is what ``build_graph.py`` reports.
    """
    clusters: dict[str, set[str]] = {}
    for raw in raw_tokens:
        cleaned = _clean(raw)
        clusters.setdefault(normalize_component(cleaned), set()).add(cleaned)
    return {k: sorted(v) for k, v in sorted(clusters.items()) if len(v) > 1}


CANONICAL_COMPONENTS: tuple[str, ...] = tuple(sorted(set(ALIASES.values())))
