"""Tests for ``pipelines.common.country_config``."""
from __future__ import annotations

import pytest

from pipelines.common import country_config as cc


def base(**over):
    d = {"code": "TT", "name": "Testland", "status": "draft",
         "bbox": {"lon_min": 30.0, "lon_max": 40.0, "lat_min": 0.0, "lat_max": 10.0},
         "exposure": {"min_rows": 30, "min_studies": 5, "min_docs": 3}}
    d.update(over)
    return d


def test_repo_countries_load():
    assert {"ET", "KE"} <= set(cc.list_countries())
    et = cc.load_country("ET", check_files=False)
    assert et.active and et.exposure == cc.Exposure(30, 5, 3)
    assert et.bbox.contains(9.0, 38.7) and not et.bbox.contains(0.0, 38.7)
    assert et.languages == ("en", "am", "om") and et.evidence_sources == ("ERA", "CSA", "HAB")
    assert et.overlays["omo_gibe"]["status"] == "planned"
    ke = cc.load_country("ke")
    assert ke.status == "draft" and ke.evidence_sources == ()


def test_et_files_exist_when_lookups_present():
    if not (cc.REPO_ROOT / "geodata" / "layers" / "aez_belt.tif").exists():
        pytest.skip("raster stack not present")
    assert cc.load_country("ET").active


@pytest.mark.parametrize("data, msg", [
    (base(code="tt"), "alpha-2"),
    (base(status="live"), "status"),
    (base(bbox={"lon_min": 40, "lon_max": 30, "lat_min": 0, "lat_max": 10}), "longitudes"),
    (base(bbox={"lon_min": 30, "lon_max": 40, "lat_min": 10, "lat_max": 0}), "latitudes"),
    (base(bbox={"lon_min": 30, "lon_max": 40, "lat_min": 0}), "lat_max"),
    (base(exposure={"min_rows": 0}), ">= 1"),
    (base(status="active", languages=["en"], evidence_sources=["X"]), "unset paths"),
    (base(status="active"), "languages"),
])
def test_invalid_configs(data, msg):
    with pytest.raises(cc.CountryConfigError, match=msg):
        cc.parse_country(data)


def test_code_must_match_file_name():
    with pytest.raises(cc.CountryConfigError, match="file name"):
        cc.parse_country(base(), expected_code="UU")


def test_active_country_checks_files(tmp_path):
    paths = {"grid": "g.json", "aez": {"anchor_raster": "a.tif", "lookup": "l.csv", "attributes": "x.csv"}}
    data = base(status="active", languages=["en"], evidence_sources=["ERA"], **paths)
    with pytest.raises(cc.CountryConfigError, match="files missing"):
        cc.parse_country(data, root=tmp_path)
    for f in ("g.json", "a.tif", "l.csv", "x.csv"):
        (tmp_path / f).write_text("x")
    assert cc.parse_country(data, root=tmp_path).active
    assert cc.parse_country(dict(data, grid="missing.json"), root=tmp_path, check_files=False).active


def test_missing_file_is_clear(tmp_path):
    with pytest.raises(cc.CountryConfigError, match="no country configuration"):
        cc.load_country("ZZ", countries_dir=tmp_path)
