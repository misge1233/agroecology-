"""Catalogue parser on a 2-entry docx built in the test (irregular labels on purpose)."""
from __future__ import annotations

import pytest

docx = pytest.importorskip("docx")

from pipelines.evidence import parse_catalogue as pc  # noqa: E402


def make_docx(path):
    d = docx.Document()
    d.add_paragraph("Evidence-based Agroecology+ Solutions Catalogue")
    d.add_paragraph("1. Agroecology solution name: Bench Terrace")
    d.add_paragraph("Category: Soil and water conservation, Agroforestry")
    d.add_paragraph("Target Farming System: Crop-livestock mixed")
    d.add_paragraph("Suitable land use type and agroecology: degraded cultivated land")
    d.add_paragraph("Weyna Dega and Dega")                         # continuation of the previous field
    d.add_paragraph("Current Scaling Stage: Widely scaled")
    d.add_paragraph("Scale to be used: plot, farm or landscape")
    d.add_paragraph("Solution at a glance (Short description: Level steps on sloping land.")
    d.add_paragraph("Key problems to be addressed: Soil erosion, soil fertility depletion and moisture stress")
    d.add_paragraph("Key agroecology principles that apply: diversity, synergy, recycling")
    d.add_paragraph("Key benefits/evidence: Productivity, Erosion control; Income")
    d.add_paragraph("Evidence base: on-farm trial, cost-benefit analysis")
    d.add_paragraph("Limitations: high labour cost")
    d.add_paragraph("Bench terrace in Gumer woreda, photo credit by Dereje")
    t = d.add_table(rows=1, cols=1)
    t.cell(0, 0).text = "Stone bench terrace at Haramaya, photo credit by Yatu"
    d.add_paragraph("Live check-dam")                               # auto-numbered title, no number in the text
    d.add_paragraph("Category: Soil and water conservation")
    d.add_paragraph("Key problems to be addressed: gully erosion, feed shortage")
    d.add_paragraph("Limitations: needs protection from grazing. Evidence base: field demonstrations")
    d.add_paragraph("References")
    d.add_paragraph("Hurni, H. (2016). Soil and water conservation in Ethiopia.")
    d.save(str(path))
    return path


def test_parse_two_entries(tmp_path):
    entries = pc.parse(make_docx(tmp_path / "cat.docx"))
    pc.check(entries, expected=2)
    a, b = entries
    assert (a.catalogue_id, a.number, a.name) == ("CAT_01", 1, "Bench Terrace")
    assert a.category == "Soil and water conservation, Agroforestry"
    assert a.suitable_land_use_and_agroecology == "degraded cultivated land Weyna Dega and Dega"
    assert a.description == "Level steps on sloping land."
    assert a.key_problems == ["soil erosion", "soil fertility depletion", "soil moisture stress"]
    assert a.principles == ["diversity", "synergy", "recycling"]
    assert a.benefits == ["Productivity", "Erosion control", "Income"]
    assert a.evidence_base == ["on-farm trial", "cost-benefit analysis"]
    assert a.limitations == "high labour cost"
    assert len(a.photo_captions) == 2 and "Haramaya" in a.photo_captions[1]
    assert (b.catalogue_id, b.name) == ("CAT_02", "Live check-dam")
    assert b.key_problems == ["gully erosion", "feed shortage"]
    assert b.limitations == "needs protection from grazing."              # inline label split
    assert b.evidence_base == ["field demonstrations"]


def test_check_rejects_wrong_count(tmp_path):
    entries = pc.parse(make_docx(tmp_path / "cat.docx"))
    with pytest.raises(AssertionError, match="expected 30"):
        pc.check(entries)


def test_write_outputs(tmp_path):
    entries = pc.parse(make_docx(tmp_path / "cat.docx"))
    pc.write(entries, tmp_path / "c.json", tmp_path / "c.csv")
    assert (tmp_path / "c.json").read_text(encoding="utf-8").count("catalogue_id") == 2
    assert "key_problems" in (tmp_path / "c.csv").read_text(encoding="utf-8").splitlines()[0]


@pytest.mark.parametrize("raw, terms", [
    ("Soil erosion, nutrient losses, moisture stress", ["soil erosion", "soil nutrient depletion", "soil moisture stress"]),
    ("Gully erosion and landslide.", ["gully erosion", "landslide"]),
    ("Good potential to improve degraded and steep hillsides - mostly for area closure", ["degraded hillsides"]),
])
def test_normalise_problems(raw, terms):
    assert pc.normalise_problems(raw) == terms
