"""Guideline ingest (E2 C1-C2): page split, image-page rule, chunk metadata, citation label.

The 2-page fixture PDF is written by the test itself (plain PDF 1.4 text objects),
so no binary file is committed. The pdftotext-based test skips when the tool is absent.
"""
from __future__ import annotations

import pytest

from rag.ingest import ingest_guidelines as ig


def tiny_pdf(path, pages: list[str]) -> None:
    """Write a minimal valid PDF with one text line per page."""
    objs = ["<< /Type /Catalog /Pages 2 0 R >>", None]
    kids = []
    font_id = 3
    objs.append("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    for text in pages:
        content = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET"
        objs.append(f"<< /Length {len(content)} >>\nstream\n{content}\nendstream")
        cid = len(objs)
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {cid} 0 R "
                    f"/Resources << /Font << /F1 {font_id} 0 R >> >> >>")
        kids.append(len(objs))
    objs[1] = f"<< /Type /Pages /Kids [{' '.join(f'{k} 0 R' for k in kids)}] /Count {len(kids)} >>"
    out = b"%PDF-1.4\n"
    offsets = []
    for i, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n{body}\nendobj\n".encode("latin-1")
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    path.write_bytes(out)


@pytest.mark.skipif(ig.find_tool("pdftotext") is None, reason="pdftotext not installed")
def test_extract_pages_two_page_pdf(tmp_path):
    pdf = tmp_path / "g.pdf"
    tiny_pdf(pdf, ["Soil bunds are built along the contour on slopes of 3-15 percent.", "Page two text."])
    pages = ig.extract_pages(pdf, ig.find_tool("pdftotext"))
    assert len(pages) == 2
    assert "Soil bunds" in pages[0] and "Page two" in pages[1]


def test_image_page_rule():
    assert ig.image_pages([1500, 40, 1800, 1700]) == ([2], False)
    assert ig.image_pages([10, 20, 900]) == ([1, 2, 3], True)       # mostly image pages: whole document
    assert ig.image_pages([]) == ([], False)


def test_language_and_citation():
    assert ig.detect_language("የአፈርና ውሃ ጥበቃ ስራ") == "am"
    assert ig.detect_language("Soil and water conservation") == "en"
    rec = {"publisher": "Ministry of Agriculture; WLRC; CDE Bern", "year": "2016",
           "title": "Guidelines for Development Agents on Soil and Water Conservation in Ethiopia (2nd edition)"}
    assert ig.citation_label(rec, 34) == ("MoA 2016, Guidelines for Development Agents on Soil and Water "
                                          "Conservation in Ethiopia, p. 34")
    assert ig.short_publisher("Ministry of Agriculture with GIZ SLM") == "MoA"
    assert ig.short_publisher("Ministry of Agriculture of Ethiopia") == "MoA"
    assert ig.short_publisher("CIFOR-ICRAF") == "CIFOR-ICRAF"


def test_guideline_chunks_metadata():
    rec = {"doc_id": "MOA_TEST", "title": "Test guide", "publisher": "Ministry of Agriculture", "year": "2014",
           "theme": "swc", "url": "https://example.org/g.pdf"}
    words = ("Soil bunds and stone bunds are constructed along the contour to reduce runoff and soil loss on "
             "cultivated land with moderate slopes; farmers maintain the bunds after each rainy season. ") * 6
    chunks = ig.guideline_chunks(rec, [(3, words), (4, "too short")], "en", min_quality=0.0)
    assert chunks and all(c["page"] == 3 for c in chunks)
    c = chunks[0]
    assert c["chunk_id"].startswith("GL_MOA_TEST_p003_") and c["tier"] == "guidelines" and c["era_code"] is None
    assert (c["doc_id"], c["year"], c["language"], c["theme"], c["source"]) == ("MOA_TEST", 2014, "en", "swc", "guidelines")
    assert c["citation"] == "MoA 2014, Test guide, p. 3"
