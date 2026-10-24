"""Unit tests for the practice -> practice_family classifier (Phase P6a.1).

Pure-function tests on ``classify_era`` / ``classify``: no dataset, no pandas
frame, no network. They pin the worked examples written down in
``docs/decisions/practice_family_mapping.md`` so the keyword table and the
documented priority rule cannot drift apart again.

Run from the repo root:
    python -m pytest pipelines/dataset/test_practice_family.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PIPELINE_DIR = Path(__file__).resolve().parent
if str(PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(PIPELINE_DIR))

from build_practice_family import (  # noqa: E402
    CPM,
    CSA_MAP,
    ECWM,
    FAF,
    FULL,
    ISFM,
    KW,
    LPM,
    PRIORITY,
    classify,
    classify_era,
)


# ------------------------------------------------- the P6a.1 regression itself
@pytest.mark.parametrize("label,expected", [
    # Irrigation alone, and irrigation over crop management -> ECWM.
    ("Supplemental Irrigation", ECWM),
    ("Improved Varieties-Supplemental Irrigation", ECWM),
    # ...but fertilizer outranks water in the documented PRIORITY, exactly as
    # for the mapping document's worked example
    # "Inorganic Fertilizer-Water Harvesting -> ISFM (fertilizer beats water)".
    # Forcing this one to ECWM would special-case it against the stated rule.
    ("Inorganic Fertilizer-Supplemental Irrigation", ISFM),
])
def test_supplemental_irrigation_leaves_livestock(label, expected):
    """The P6a.1 fix: 'supplement' no longer drags irrigation into LPM.

    These three labels carry the 311 rows the erratum corrects. None of them
    stays in LPM; where they land afterwards is decided by the unchanged
    PRIORITY rule, which splits them 301 -> ECWM and 10 -> ISFM.
    """
    assert classify_era(label)[0] not in (LPM,)
    assert classify_era(label)[0] == expected


def test_the_two_fertilizer_plus_water_labels_resolve_identically():
    """Same keyword signature must give the same family — no special cases."""
    assert (classify_era("Inorganic Fertilizer-Supplemental Irrigation")[0]
            == classify_era("Inorganic Fertilizer-Water Harvesting")[0] == ISFM)


def test_lpm_no_longer_carries_the_bare_supplement_token():
    assert "supplement" not in KW["LPM"]
    assert "supplementation" in KW["LPM"]
    assert "feed supplement" in KW["LPM"]


def test_feed_supplementation_still_reaches_livestock():
    """The keyword the LPM token was meant for still works."""
    assert classify_era("Feed Supplementation")[0] == LPM
    assert classify_era("Mineral Supplementation")[0] == LPM
    assert classify_era("Feed Supplement Blocks")[0] == LPM


def test_the_existing_feed_practices_are_unaffected():
    """They match on 'feed', never on the removed token."""
    assert classify_era("Feed Addition-Feed Processing")[0] == LPM
    assert classify_era("Feed Substitution")[0] == LPM


# ------------------------------- worked examples from practice_family_mapping.md
@pytest.mark.parametrize("label,expected", [
    ("Inorganic Fertilizer", ISFM),
    ("Improved Varieties", CPM),
    ("Water Harvesting", ECWM),
    ("Parklands", FAF),
    ("Feed Addition", LPM),
    ("Agroforestry Fallow", FAF),
    ("Improved Varieties-Supplemental Irrigation", ECWM),
    ("Inorganic Fertilizer-Water Harvesting", ISFM),
    ("Agroforestry Pruning-Inorganic Fertilizer", FAF),
    ("Mulch-Reduced Tillage", ECWM),
])
def test_mapping_document_worked_examples(label, expected):
    assert classify_era(label)[0] == expected


def test_priority_order_resolves_multi_keyword_names():
    family, was_multi = classify_era("Agroforestry Pruning-Inorganic Fertilizer")
    assert (family, was_multi) == (FAF, True)          # FAF beats ISFM
    family, was_multi = classify_era("Inorganic Fertilizer")
    assert (family, was_multi) == (ISFM, False)        # single clean hit
    assert PRIORITY == ["FAF", "LPM", "ISFM", "ECWM", "CPM"]


def test_no_keyword_match_falls_back_to_cpm_and_is_flagged():
    family, was_multi = classify_era("Entirely Unknown Practice")
    assert family == CPM
    assert was_multi is None          # None == "defaulted, please review"


# -------------------------------------------------------- CSA-source dispatch
def test_csa_rows_use_the_explicit_lookup_not_the_keywords():
    # "Conservation tillage" would hit the ECWM/CPM keywords, but the paper
    # assigns the CSA category explicitly.
    assert classify("CSA", "Conservation tillage") == CPM
    assert classify("CSA", "Deficit irrigation") == ECWM
    assert classify("CSA", "Exclosure") == FAF
    assert classify("CSA", "organic amedements") == ISFM
    assert classify("CSA", "grazing management") == LPM


def test_unknown_csa_category_defaults_to_cpm():
    assert classify("CSA", "Not A CSA Category") == CPM


def test_era_rows_go_through_the_keyword_classifier():
    assert classify("ERA", "Supplemental Irrigation") == ECWM
    assert classify("ERA", "Inorganic Fertilizer") == ISFM


# --------------------------------------------------------------- table health
def test_every_csa_category_maps_to_a_real_family():
    assert len(CSA_MAP) == 20
    assert set(CSA_MAP.values()) <= set(FULL.values())


def test_keyword_table_covers_exactly_the_five_families():
    assert set(KW) == set(PRIORITY) == set(FULL)
    for family, keywords in KW.items():
        assert keywords, family
        assert all(k == k.lower() for k in keywords), family
        assert len(keywords) == len(set(keywords)), family


def test_classification_is_case_insensitive():
    assert classify_era("SUPPLEMENTAL IRRIGATION")[0] == ECWM
    assert classify_era("supplemental irrigation")[0] == ECWM
