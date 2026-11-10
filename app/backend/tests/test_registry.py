"""GET /registry (Phase E1, brief D2): served from a fixture registry, no raster stack needed."""
from __future__ import annotations

import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.services import registry_service

FIXTURE = Path(__file__).parent / "fixtures" / "registry_TT.json"


@pytest.fixture
def client(tmp_path, monkeypatch):
    evidence = tmp_path / "evidence"
    countries = tmp_path / "countries"
    evidence.mkdir()
    countries.mkdir()
    shutil.copy(FIXTURE, evidence / "registry_TT.json")
    (countries / "TT.yaml").write_text("code: TT\nstatus: active\n", encoding="utf-8")
    (countries / "UU.yaml").write_text("code: UU\nstatus: draft\n", encoding="utf-8")  # configured, not built
    monkeypatch.setattr(
        registry_service, "get_settings",
        lambda: SimpleNamespace(resolved_evidence_dir=evidence, resolved_countries_dir=countries),
    )
    registry_service.clear_cache()
    yield TestClient(create_app())  # no `with`: the lifespan (engine warm-up) is not run
    registry_service.clear_cache()


def test_registry_serves_fixture(client):
    r = client.get("/registry", params={"country": "tt"})
    assert r.status_code == 200
    body = r.json()
    assert body["country"] == "TT"
    assert body["thresholds"] == {"min_rows": 30, "min_studies": 5, "min_docs": 3}
    ids = [c["id"] for c in body["challenges"]]
    assert ids == ["SOIL_EROSION", "GULLY_EROSION"]
    erosion = body["challenges"][0]
    assert erosion["exposed"] is True and erosion["objectives"][0]["direction"] == -1
    gully = body["challenges"][1]
    assert gully["exposed"] is False and gully["documented_only"] is True
    assert body["practices"][0]["id"] == "PHYSICAL_SWC_MEASURES"


def test_registry_unknown_country_is_404(client):
    r = client.get("/registry", params={"country": "ZZ"})
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "unknown_country"


def test_registry_not_built_is_503(client):
    r = client.get("/registry", params={"country": "UU"})
    assert r.status_code == 503
    err = r.json()["error"]
    assert err["code"] == "registry_unavailable"
    assert "build_registry.py --country UU" in err["message"]


def test_registry_bad_code_is_422(client):
    assert client.get("/registry", params={"country": "ETH"}).status_code == 422
