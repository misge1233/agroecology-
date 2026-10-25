"""Unit tests for the WOCAT record schema and normalizer (Phase P6a).

No network: the only inputs are the hand-built fixtures in ``fixtures/`` and
dicts written inline. Needs pydantic v2 (``rag/requirements.txt``).

Run from the repo root:
    python -m pytest rag/ingest/wocat/test_wocat.py -q
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

WOCAT_DIR = Path(__file__).resolve().parent
REPO_ROOT = WOCAT_DIR.parents[2]

from rag.ingest.wocat import normalize_wocat as nw  # noqa: E402
from rag.ingest.wocat.schema import (  # noqa: E402
    WocatApproach,
    WocatTechnology,
    _degradation_code,
    _measure_code,
    parse_record,
)

FIXTURE_DIR = WOCAT_DIR / "fixtures"


# ------------------------------------------------------------------ fixtures
def test_every_fixture_parses_and_keeps_its_provenance():
    paths = sorted(FIXTURE_DIR.glob("*.json"))
    assert len(paths) >= 2, "expected the hand-built WOCAT fixtures"
    for path in paths:
        record = parse_record(json.loads(path.read_text(encoding="utf-8")))
        assert record.wocat_id
        assert record.title
        assert record.provenance == "wocat_fixture"
        assert record.licence


def test_real_fixtures_carry_the_cc_licence_url_and_compiler():
    for name in ("technology_6644.json", "approach_6732.json"):
        record = parse_record(json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8")))
        assert record.synthetic is False
        assert record.licence.startswith("CC BY-NC-SA")
        assert record.url and record.url.startswith("https://wocat.net/")
        assert record.compiler
        assert record.country == "Ethiopia"


def test_synthetic_fixture_is_flagged_and_claims_no_wocat_licence():
    record = parse_record(
        json.loads((FIXTURE_DIR / "technology_synthetic_0001.json").read_text(encoding="utf-8"))
    )
    assert record.synthetic is True
    assert "not WOCAT data" in record.licence
    assert record.url is None


def test_technology_6644_normalizes_to_the_questionnaire_vocabulary():
    record = parse_record(
        json.loads((FIXTURE_DIR / "technology_6644.json").read_text(encoding="utf-8"))
    )
    assert isinstance(record, WocatTechnology)
    assert record.measures == ["A2", "A3", "A6", "A7", "M2"]
    assert record.degradation == ["Bc", "Bl", "Bq", "Bs", "Ca", "Cn", "Pc", "Ps", "Wt"]
    assert "integrated soil fertility management" in record.slm_groups
    assert record.water_supply == "rainfed"
    assert record.land_use == ["Ca"]
    assert record.rainfall_mm == 1947
    # live-database band spellings become questionnaire labels
    assert record.context["rainfall_band"] == ["1,501-2,000 mm"]
    assert record.context["altitude_zone"] == ["1,501-2,000 m a.s.l."]
    assert record.context["slope_class"] == ["gentle (3-5%)", "moderate (6-10%)"]
    assert record.adoption.share_of_land_users == "10-50%"
    assert record.adoption.share_spontaneous == "90-100%"
    assert record.cost_benefit.maintenance_long_term == "very positive"
    # "below ground C" (site) -> "below-ground C" (questionnaire)
    assert record.impacts["soil organic matter/ below-ground C"] == "positive"
    assert record.impacts["soil loss"] == "slightly positive"
    assert len(record.impacts) == 39
    assert record.linked_approaches == ["6732"]
    assert len(record.activities) == 4
    assert record.costs.currency == "ETB"


def test_approach_6732_links_back_to_the_technology():
    record = parse_record(
        json.loads((FIXTURE_DIR / "approach_6732.json").read_text(encoding="utf-8"))
    )
    assert isinstance(record, WocatApproach)
    assert record.record_type == "approach"
    assert record.linked_technologies == ["6644"]
    assert record.year_initiated == 2015


# -------------------------------------------------------------- normalizing
def test_unknown_codes_are_dropped_not_invented(caplog):
    record = WocatTechnology.model_validate({
        "wocat_id": "X1",
        "title": "Bad codes",
        "measures": ["A2", "Z9", "A 3.3: Full tillage (< 30% soil cover)"],
        "degradation": ["Wt", "QQ"],
        "slm_groups": ["agroforestry", "not a group"],
        "context": {"agroclimatic_zone": ["sub-humid", "tropical"],
                    "not_a_kind": ["x"]},
        "impacts": {"crop production": "positive", "unicorn density": "positive",
                    "soil loss": "spectacular"},
    })
    assert record.measures == ["A2", "A3"]
    assert record.degradation == ["Wt"]
    assert record.slm_groups == ["agroforestry"]
    assert record.context == {"agroclimatic_zone": ["sub-humid"]}
    assert record.impacts == {"crop production": "positive"}


def test_measure_and_degradation_code_parsing():
    assert _measure_code("A 3.3: Full tillage (< 30% soil cover)") == "A3"
    assert _measure_code("A6: Residue management") == "A6"
    assert _measure_code("S10") == "S10"
    assert _measure_code("Z9") is None
    assert _degradation_code("Wt: loss of topsoil/ surface erosion") == "Wt"
    assert _degradation_code("WT") == "Wt"
    assert _degradation_code("ZZ") is None


def test_scalar_values_are_accepted_where_a_list_is_expected():
    record = WocatTechnology.model_validate({
        "wocat_id": "X2", "title": "Scalars", "measures": "A1",
        "slm_groups": "agroforestry", "strengths": "one strength",
    })
    assert record.measures == ["A1"]
    assert record.slm_groups == ["agroforestry"]
    assert record.strengths == ["one strength"]


def test_defaults_are_empty_not_missing():
    record = WocatTechnology.model_validate({"wocat_id": "X3", "title": "Bare"})
    assert record.measures == [] and record.impacts == {} and record.context == {}
    assert record.licence  # a licence is always asserted
    assert record.costs.currency is None
    assert record.adoption.share_of_land_users is None


def test_missing_required_field_raises():
    with pytest.raises(Exception):
        WocatTechnology.model_validate({"title": "no id"})


# ----------------------------------------------------------------- adapters
def test_pass_through_adapter_round_trips_the_fixtures():
    raw = nw.load_raw(FIXTURE_DIR)
    technologies, approaches, errors = nw.normalize(raw, nw.PassThroughAdapter())
    assert errors == []
    assert len(technologies) == 2 and len(approaches) == 1
    assert {t.wocat_id for t in technologies} == {"6644", "SYNTH-0001"}


def test_pass_through_adapter_skips_records_without_an_id():
    technologies, approaches, errors = nw.normalize(
        [{"title": "nameless"}], nw.PassThroughAdapter()
    )
    assert (technologies, approaches, errors) == ([], [], [])


def test_key_probe_adapter_finds_alternative_key_spellings():
    adapted = nw.KeyProbeAdapter().adapt({
        "ID": 7201,
        "Name": "Stone bunds",
        "Countries": "Ethiopia",
        "slm_measures": ["S2"],
        "on_site_impacts": {"soil loss": "very positive"},
        "permalink": "https://wocat.net/en/database/technologies/7201/",
    })
    assert adapted is not None
    record = parse_record(adapted)
    assert record.wocat_id == "7201"
    assert record.title == "Stone bunds"
    assert record.country == "Ethiopia"
    assert record.provenance == "wocat_export"
    assert record.measures == ["S2"]
    assert record.impacts == {"soil loss": "very positive"}


def test_key_probe_adapter_reports_a_record_with_no_id():
    assert nw.KeyProbeAdapter().adapt({"whatever": 1}) is None


# ------------------------------------------------------------- load/inspect
def test_load_raw_reads_json_jsonl_and_csv(tmp_path):
    (tmp_path / "a.json").write_text(json.dumps({"wocat_id": "1"}), encoding="utf-8")
    (tmp_path / "b.jsonl").write_text(
        json.dumps({"wocat_id": "2"}) + "\n" + json.dumps({"wocat_id": "3"}) + "\n",
        encoding="utf-8",
    )
    (tmp_path / "c.csv").write_text("wocat_id,title\n4,Four\n", encoding="utf-8")
    (tmp_path / "d.txt").write_text("ignored", encoding="utf-8")
    records = nw.load_raw(tmp_path)
    assert {str(r["wocat_id"]) for r in records} == {"1", "2", "3", "4"}


def test_load_raw_unwraps_a_results_envelope(tmp_path):
    path = tmp_path / "export.json"
    path.write_text(json.dumps({"count": 2, "results": [{"wocat_id": "a"},
                                                        {"wocat_id": "b"}]}),
                    encoding="utf-8")
    assert len(nw.load_raw(path)) == 2


def test_inspect_describes_the_real_key_shape():
    report = nw.inspect([
        {"id": 1, "title": "a", "country": ""},
        {"id": 2, "title": "b", "extra": [1, 2]},
    ])
    assert report["n_records"] == 2
    assert report["keys"]["id"]["present"] == 2
    assert report["keys"]["country"]["non_empty"] == 0
    assert report["keys"]["extra"]["types"] == {"list": 1}
    assert len(report["sample"]) == 1


def test_write_jsonl_is_sorted_and_stable(tmp_path):
    records = [
        parse_record({"wocat_id": "b", "title": "B"}),
        parse_record({"wocat_id": "a", "title": "A"}),
    ]
    first = nw.write_jsonl(records, tmp_path / "out.jsonl")
    payload = [json.loads(line) for line in first.read_text(encoding="utf-8").splitlines()]
    assert [r["wocat_id"] for r in payload] == ["a", "b"]
    before = first.read_bytes()
    nw.write_jsonl(list(reversed(records)), tmp_path / "out.jsonl")
    assert first.read_bytes() == before


def test_cli_writes_both_outputs(tmp_path):
    rc = nw.main(["--input", str(FIXTURE_DIR), "--out-dir", str(tmp_path)])
    assert rc == 0
    technologies = (tmp_path / "technologies.jsonl").read_text(encoding="utf-8").splitlines()
    approaches = (tmp_path / "approaches.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(technologies) == 2 and len(approaches) == 1


def test_cli_inspect_mode_prints_and_writes_nothing(tmp_path, capsys):
    rc = nw.main(["--input", str(FIXTURE_DIR), "--inspect", "--out-dir", str(tmp_path)])
    assert rc == 0
    report = json.loads(capsys.readouterr().out)
    assert report["n_records"] == 3
    assert not list(tmp_path.iterdir())
