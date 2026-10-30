"""Tier-2 chunk-quality filter (P9). Pure functions; no index, no network."""
from __future__ import annotations

import chunk_guidance as cg
import quality as q

PROSE = (
    "Soil bunds are earth embankments built along the contour to slow runoff and trap "
    "sediment on cultivated slopes. Farmers in the Ethiopian highlands space them according "
    "to slope, maintain them after each rainy season and often stabilise them with grass "
    "strips. Bunds combined with mulch retain more moisture during dry spells. " * 2
)
REFERENCE_LIST = (
    "Abera, W. (2019). Soil loss in Ethiopia. J. Soil Sci. 12(3), pp. 45-61. doi:10.1000/abc "
    "Kihara, J., et al. (2016). ISFM in East Africa. Agron. J. 108, pp. 1-12. "
    "Tilahun, S. (2014). Runoff. Catena 118, pp. 44-50. Vol. 3 (2010) pp. 3-9. "
    "Belay, T. (2012). Bunds. In: Proc. Vol. 2, pp. 101-110. doi:10.1000/xyz (2011) (2013) "
) * 2
TABLE = (
    "Table 3 Yield 2012 2013 2014 Mean 1.2 1.4 1.1 1.23 2.3 2.1 2.6 2.33 0.9 1.1 1.0 1.0 "
    "Treatment T1 T2 T3 T4 12.5 13.1 11.9 14.0 % 45 51 48 50 | 3 | 4 | 5 |" * 3
)
OCR_NOISE = "a b c d th e qu ick br ow n f ox j um ps ov er th e la zy do g 1 2 3 x y z " * 6
CAPS = "SOIL AND WATER CONSERVATION PROGRAMME ANNUAL REPORT MINISTRY OF AGRICULTURE ETHIOPIA " * 5


def test_prose_scores_high_and_is_unflagged():
    out = q.chunk_quality(PROSE)
    assert out["score"] >= 0.9 and out["flags"] == []


def test_reference_list_is_garbage():
    out = q.chunk_quality(REFERENCE_LIST)
    assert out["score"] < q.MIN_QUALITY
    assert "reference_pattern" in out["flags"] or "digit_share" in out["flags"]


def test_table_is_garbage():
    out = q.chunk_quality(TABLE)
    assert out["score"] < q.MIN_QUALITY
    assert "table_pattern" in out["flags"] or "numeric_token_share" in out["flags"]


def test_ocr_shatter_is_garbage():
    out = q.chunk_quality(OCR_NOISE)
    assert out["score"] < q.MIN_QUALITY
    assert "short_token_share" in out["flags"]


def test_all_caps_heading_block_is_garbage():
    out = q.chunk_quality(CAPS)
    assert out["score"] < q.MIN_QUALITY and "caps_share" in out["flags"]


def test_empty_and_tiny_chunks_are_garbage():
    assert q.chunk_quality("")["score"] == 0.0
    assert "too_short" in q.chunk_quality("mulch helps")["flags"]


def test_score_is_deterministic_and_bounded():
    for text in (PROSE, REFERENCE_LIST, TABLE, OCR_NOISE, CAPS):
        a, b = q.chunk_quality(text), q.chunk_quality(text)
        assert a == b and 0.0 <= a["score"] <= 1.0


def test_chunk_guidance_gate_drops_garbage_and_records_quality():
    rec = {"doc_id": "d1", "title": "T", "year": 2020, "url": "u"}
    # Long prose (windowed into several chunks) followed by a reference list
    # that mentions a practice keyword, so only the quality gate can drop it.
    text = PROSE * 5 + "\n\n" + REFERENCE_LIST * 2 + " mulch soil bund"
    kept = cg.guidance_chunks(rec, text, min_words=20, max_per_doc=0, min_quality=q.MIN_QUALITY)
    unfiltered = cg.guidance_chunks(rec, text, min_words=20, max_per_doc=0, min_quality=0.0)
    assert kept and all(c["quality"] >= q.MIN_QUALITY for c in kept)
    assert len(unfiltered) > len(kept)
    assert all("quality" in c for c in unfiltered)
    assert any(c["quality"] < q.MIN_QUALITY for c in unfiltered)


def test_prune_funnel_refuses_nothing_but_lists_ids():
    import prune_collection as pc

    chunks = [
        {"chunk_id": "G_a_000", "text": PROSE},
        {"chunk_id": "G_a_001", "text": TABLE},
        {"chunk_id": "G_a_002", "text": REFERENCE_LIST},
    ]
    remove, flags = pc.funnel(chunks, q.MIN_QUALITY)
    assert remove == ["G_a_001", "G_a_002"]
    assert sum(flags.values()) >= 2
    assert "era_corpus" in pc.FROZEN_COLLECTIONS
