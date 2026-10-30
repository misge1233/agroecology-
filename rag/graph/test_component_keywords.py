"""Keyword → component table (P9)."""
from __future__ import annotations

from rag.graph import component_keywords as ck
from rag.graph.practice_components import CANONICAL_COMPONENTS, decompose
from rag.ingest.fetch_gardian import FAMILY_KEYWORDS


def test_every_family_keyword_maps_to_a_component_or_is_declared_family_only():
    covered = {kw for kws in ck.COMPONENT_KEYWORDS.values() for kw in kws} | ck.FAMILY_ONLY_KEYWORDS
    for family, kws in FAMILY_KEYWORDS.items():
        for kw in kws:
            assert kw in covered, (family, kw)


def test_component_names_are_canonical():
    assert set(ck.COMPONENT_KEYWORDS) <= set(CANONICAL_COMPONENTS)


def test_mentions_are_counted_per_component_longest_keyword_first():
    text = "Apply inorganic fertilizer with compost; mulch the rows and build soil bunds on the contour."
    hits = ck.components_in_text(text)
    assert hits["Inorganic Fertilizer"] == 1
    assert hits["Organic Fertilizer"] == 1
    assert hits["Mulch"] == 1
    assert hits["Physical SWC Measures"] == 2  # "soil bund" + "contour"
    assert "Exclosure" not in hits


def test_passage_counts_count_passages_not_hits():
    counts = ck.components_in_texts(["mulch mulch mulch", "mulch and biochar", "nothing here"])
    assert counts == {"Mulch": 2, "Biochar": 1}


def test_components_roll_up_onto_frozen_practices():
    assert "Mulch" in decompose("Mulch-Water Harvesting")
    assert "Water Harvesting" in decompose("Mulch-Water Harvesting")
