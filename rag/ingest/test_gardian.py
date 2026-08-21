"""Unit tests for the P5a guidance-corpus pipeline's pure functions.

Run from rag/ingest (or with rag/ingest on the path):
    cd rag/ingest && python -m pytest test_gardian.py -q
No network, no `datasets`, no pypdf — the fetch/chunk modules defer their
heavy imports, so the filter rules and tier tagging test anywhere.
"""
from __future__ import annotations

import chunk_guidance as cg
import fetch_gardian as fg


# ------------------------------------------------------------ field extraction
def test_as_text_flattens_lists_and_dicts():
    assert fg.as_text("  Ethiopia ") == "Ethiopia"
    assert fg.as_text(["Ethiopia", "Kenya"]) == "Ethiopia; Kenya"
    assert fg.as_text({"a": "x", "b": ["y", "z"]}) == "x; y; z"
    assert fg.as_text(None) == ""
    assert fg.as_text(2021) == "2021"


def test_first_present_probes_candidates_case_insensitively():
    record = {"Title": "Bund manual", "text": "", "content": "body text"}
    assert fg.first_present(record, fg.TITLE_KEYS) == "Bund manual"
    assert fg.first_present(record, fg.TEXT_KEYS) == "body text"  # skips empty
    assert fg.first_present(record, fg.COUNTRY_KEYS) == ""


def test_extract_year_and_safe_doc_id():
    assert fg.extract_year({"date": "Published 2019-05-01"}) == 2019
    assert fg.extract_year({"year": "n.d."}) is None
    assert fg.safe_doc_id("hdl:10568/12345", 7) == "hdl_10568_12345"
    assert fg.safe_doc_id("", 7) == "doc000007"


# ------------------------------------------------------------- Ethiopia rule
def test_ethiopia_country_metadata_is_authoritative():
    assert fg.is_ethiopia("Ethiopia; Kenya", "", "") == (True, "country_metadata")
    # Metadata present but no Ethiopia -> rejected even if the text mentions it.
    ok, via = fg.is_ethiopia("Kenya", "Ethiopia study", "ethiopia " * 10)
    assert ok is False and via == "country_metadata"


def test_ethiopia_falls_back_to_title_then_text():
    assert fg.is_ethiopia("", "Soil bunds in ETHIOPIA", "") == (True, "title")
    body_hits = "ethiopia " * fg.ETHIOPIA_TEXT_MIN
    assert fg.is_ethiopia("", "Soil bunds", body_hits) == (True, "text")
    # One passing mention is not enough.
    assert fg.is_ethiopia("", "Soil bunds", "in ethiopia once")[0] is False


# ------------------------------------------------------- agroecology relevance
def test_family_matches_on_title_keyword():
    fams = fg.matched_families("Agroforestry extension manual", "")
    assert "Agro-forestry and forest management" in fams


def test_family_matches_on_two_distinct_text_keywords():
    text = "apply compost and manure to restore fertility"
    assert fg.matched_families("Generic title", text) == [
        "Integrated soil fertility management"
    ]
    # A single text keyword is not enough.
    assert fg.matched_families("Generic title", "apply compost only") == []


def test_irrelevant_document_matches_no_family():
    assert fg.matched_families(
        "Household survey methods", "questionnaire design and sampling"
    ) == []


def test_multiple_families_can_match():
    text = ("terracing and water harvesting on steep land; "
            "intercropping with crop rotation in the valley")
    fams = fg.matched_families("", text)
    assert "Erosion control and water management" in fams
    assert "Crop production and management" in fams


# ------------------------------------------------------------- tier tagging
def make_manifest_rec() -> dict:
    return {
        "doc_id": "hdl_10568_12345",
        "tier": "guidance",
        "title": "Soil bund construction manual",
        "year": 2021,
        "url": "https://gardian.example/doc",
        "doi": None,
        "text_file": "texts/hdl_10568_12345.txt",
    }


def test_guidance_chunks_schema_prefix_and_no_era_code():
    # "soil bund" is a practice keyword, so every chunk passes the relevance
    # filter; ids carry the chunk's original document position.
    text = ("build the soil bund carefully " * 100).strip()  # 2+ chunks
    chunks = cg.guidance_chunks(make_manifest_rec(), text, min_words=40)
    assert len(chunks) >= 2
    for i, c in enumerate(chunks):
        assert c["chunk_id"] == f"G_hdl_10568_12345_{i:03d}"
        assert c["chunk_id"].startswith(cg.CHUNK_ID_PREFIX)
        assert c["tier"] == "guidance"
        assert c["era_code"] is None          # never fake Tier-1 linkage
        assert c["source"] == "gardian"
        assert c["url"] == "https://gardian.example/doc"
        assert c["title"] == "Soil bund construction manual"
        assert c["year"] == 2021
        assert c["kw_distinct"] >= 1


def test_guidance_chunks_drops_short_pieces():
    assert cg.guidance_chunks(make_manifest_rec(), "too short", min_words=40) == []


def test_guidance_chunks_drops_keywordless_chunks():
    # Long enough, Ethiopia-flavoured, but no practice keyword -> filtered.
    text = ("this ethiopia report discusses policy and finance topics " * 50).strip()
    assert cg.guidance_chunks(make_manifest_rec(), text, min_words=40) == []


def test_guidance_chunks_caps_per_doc_by_keyword_density():
    # 6 chunks' worth of text: alternate a dense passage (3 distinct
    # keywords) with a sparse one (1 keyword) and cap at 2 — the two
    # densest chunks must win, output in document order.
    dense = "apply mulch on the terrace beside the soil bund daily today " * 38
    sparse = "the fodder store report continues with more plain sentences " * 38
    text = "\n\n".join([sparse, dense, sparse, dense, sparse, dense])
    capped = cg.guidance_chunks(make_manifest_rec(), text, min_words=40,
                                max_per_doc=2)
    assert len(capped) == 2
    assert all(c["kw_distinct"] >= 3 for c in capped)
    positions = [int(c["chunk_id"].rsplit("_", 1)[1]) for c in capped]
    assert positions == sorted(positions)  # document order preserved
    uncapped = cg.guidance_chunks(make_manifest_rec(), text, min_words=40,
                                  max_per_doc=0)
    assert len(uncapped) > 2               # 0 = no cap


def test_keyword_stats_distinct_vs_total():
    distinct, total = cg.keyword_stats("mulch and mulch on the terrace")
    assert distinct == 2 and total == 3
    assert cg.keyword_stats("no relevant terms here") == (0, 0)


# --------------------------------------------- real-schema adaptations (P5a)
def test_id_probe_matches_real_sieverid_field():
    record = {"sieverID": "7039eda0-f558-4000-9612-a031926aa8b8", "content": "x"}
    assert fg.first_present(record, fg.ID_KEYS) == "7039eda0-f558-4000-9612-a031926aa8b8"


def test_url_from_metadata_extracts_embedded_source_url():
    record = {"metadata": "a5bf57d5; gardian_index; "
                          "https://cgspace.cgiar.org/rest/bitstreams/9aa6/retrieve; "
                          "Climate information is"}
    assert fg.url_from_metadata(record) == \
        "https://cgspace.cgiar.org/rest/bitstreams/9aa6/retrieve"
    assert fg.url_from_metadata({"metadata": "hash; gardian_index; no url here"}) == ""
    assert fg.url_from_metadata({}) == ""


def test_display_title_head_words_and_ellipsis():
    long = fg.display_title("Climate information is now an agricultural input "
                            "just like seeds fertilizers or equipment which are")
    assert long is not None and long.endswith(" …")
    assert len(long.split()) == fg.TITLE_HEAD_WORDS + 1  # words + ellipsis
    assert fg.display_title("Short doc") == "Short doc"
    assert fg.display_title("") is None
