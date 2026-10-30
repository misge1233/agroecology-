"""Practice-mention keywords → canonical practice components (Phase P9).

The Tier-2 guidance corpus was admitted with ``fetch_gardian.FAMILY_KEYWORDS``
(keyword → practice family). The evidence-tiered advisory needs one level
finer: which of the 44 canonical **components** (``practice_components``) a
guidance passage talks about, so documented practices can be proposed by
component and mapped back onto the frozen ``CSA_practices`` labels.

This module **extends** the family table — it imports it, maps every keyword
it contains onto a component (or lists it in ``FAMILY_ONLY_KEYWORDS`` when a
keyword names a family-level topic rather than a practice) and asserts full
coverage at import time, so the two tables cannot drift apart silently.
Matching is lower-cased substring matching, exactly as in ``chunk_guidance``.

Nothing here quantifies anything: a keyword hit is a *mention*, reported as
counts of passages/documents with their citations (CLAUDE.md doctrine 1 as
amended in P9).
"""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Iterable

from rag.graph.practice_components import CANONICAL_COMPONENTS
from rag.ingest.fetch_gardian import FAMILY_KEYWORDS

#: canonical component -> lower-cased substrings that mention it.
COMPONENT_KEYWORDS: dict[str, tuple[str, ...]] = {
    # ---- Integrated soil fertility management
    "Inorganic Fertilizer": ("inorganic fertilizer", "fertilizer application", "fertiliser", "mineral fertilizer", "urea", "dap "),
    "Inorganic Fertilizer Reduction": ("fertilizer reduction", "reduced fertilizer", "reduced inorganic", "lower fertilizer rate"),
    "Organic Fertilizer": ("organic fertilizer", "compost", "manure", "green manure", "vermicompost", "farmyard"),
    "Organic Amendments": ("organic amendment", "soil amendment"),
    "Biochar": ("biochar",),
    "ISFM": ("isfm", "integrated soil fertility"),
    "pH Control": ("liming", "lime application", "soil acidity"),
    "Crop Residue Incorporation": ("crop residue", "residue incorporation", "residue retention"),
    # ---- Crop production and management
    "Improved Varieties": ("improved variet", "improved seed"),
    "Intercropping": ("intercrop",),
    "Crop Rotation": ("crop rotation",),
    "Mulch": ("mulch",),
    "Conservation Tillage": ("conservation tillage", "conservation agriculture"),
    "Reduced Tillage": ("reduced tillage", "zero tillage", "no-till", "minimum tillage"),
    "Drought Tolerant Crops": ("drought tolerant", "drought-tolerant"),
    "Improved Fallow": ("improved fallow",),
    "Weeding": ("weeding", "weed control"),
    # ---- Erosion control and water management
    "Physical SWC Measures": ("soil bund", "stone bund", "terrac", "check dam", "gully", "contour"),
    "Biological SWC Practices": ("grass strip", "vetiver", "biological soil and water", "vegetative barrier"),
    "Physical + Biological SWC Practices": ("soil and water conservation", "erosion control", "watershed management", "runoff management"),
    "Water Harvesting": ("water harvesting",),
    "In-situ Water Harvesting": ("in-situ water harvesting", "in situ water harvesting", "tied ridge", "tied-ridge"),
    "Drip Irrigation": ("drip irrigation",),
    "Furrow Irrigation": ("furrow irrigation",),
    "Alternate Furrow Irrigation": ("alternate furrow",),
    "Deficit Irrigation": ("deficit irrigation",),
    "Supplemental Irrigation": ("supplemental irrigation", "supplementary irrigation", "small-scale irrigation"),
    "Overhead Irrigation with Mulching": ("overhead irrigation", "sprinkler irrigation"),
    "Exclosure": ("exclosure",),
    # ---- Agro-forestry and forest management
    "Alleycropping": ("alley cropping", "alleycropping"),
    "Parklands": ("parkland", "faidherbia"),
    "Multistrata Agroforestry": ("multistrata", "multi-strata", "homegarden", "home garden"),
    "Other Agroforestry": ("agroforestry", "agro-forestry", "tree planting", "afforestation", "reforestation", "farm forestry", "farmer managed natural regeneration", "woodlot"),
    "Agroforestry Fallow": ("agroforestry fallow", "tree fallow"),
    "Agroforestry Pruning": ("pruning",),
    # ---- Livestock production and management
    "Grazing Management": ("grazing management", "rotational grazing", "rangeland", "controlled grazing"),
    "Pasture Management": ("pasture management", "pasture improvement"),
    "Animal Feed Management": ("fodder", "forage production", "animal feed", "feed management", "livestock feed"),
    "Feed Addition": ("feed supplement", "supplementary feed", "concentrate feed"),
    "Feed Processing": ("feed processing", "urea treatment", "silage", "hay making"),
    "Feed Substitution": ("feed substitution",),
}

#: ``FAMILY_KEYWORDS`` entries that name a topic rather than one practice and
#: therefore map to no single component (they still admit documents).
FAMILY_ONLY_KEYWORDS: frozenset[str] = frozenset({
    "soil fertility", "row planting", "soil erosion",
})

_UNMAPPED_COMPONENTS: frozenset[str] = frozenset({
    # Components with no stable English keyword in guidance prose; they are
    # still proposable through the graph (evidence for other objectives).
    "Intercropping or Rotation", "IWM", "Agronomic/Biological SWC Practices",
})


def _check_tables() -> None:
    unknown = set(COMPONENT_KEYWORDS) - set(CANONICAL_COMPONENTS)
    if unknown:
        raise RuntimeError(f"COMPONENT_KEYWORDS names unknown components: {sorted(unknown)}")
    missing = set(CANONICAL_COMPONENTS) - set(COMPONENT_KEYWORDS) - _UNMAPPED_COMPONENTS
    if missing:
        raise RuntimeError(f"components without keywords: {sorted(missing)}")
    covered = {kw for kws in COMPONENT_KEYWORDS.values() for kw in kws} | FAMILY_ONLY_KEYWORDS
    drifted = {kw for kws in FAMILY_KEYWORDS.values() for kw in kws} - covered
    if drifted:
        raise RuntimeError(f"FAMILY_KEYWORDS entries not mapped to a component: {sorted(drifted)}")


_check_tables()

#: keyword -> (component, compiled pattern). A keyword must start at a word
#: boundary so "organic fertilizer" never fires inside "inorganic fertilizer"
#: and "urea" never inside "bureau"; it may end mid-word ("terrac" → terraces,
#: "intercrop" → intercropping), as in chunk_guidance's substring rule.
_KEYWORD_INDEX: tuple[tuple[str, str, re.Pattern[str]], ...] = tuple(
    (kw, component, re.compile(r"(?<![a-z0-9])" + re.escape(kw)))
    for component, kws in COMPONENT_KEYWORDS.items() for kw in kws
)


def components_in_text(text: str) -> dict[str, int]:
    """Canonical components mentioned in ``text`` with their hit counts."""
    lowered = (text or "").lower()
    hits: dict[str, int] = defaultdict(int)
    for _keyword, component, pattern in _KEYWORD_INDEX:
        n = len(pattern.findall(lowered))
        if n:
            hits[component] += n
    return dict(hits)


def components_in_texts(texts: Iterable[str]) -> dict[str, int]:
    """Number of texts (passages) mentioning each component."""
    counts: dict[str, int] = defaultdict(int)
    for text in texts:
        for component in components_in_text(text):
            counts[component] += 1
    return dict(counts)
