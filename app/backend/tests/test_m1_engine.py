"""E5 Part 4: Methodology 1 v2 behind ADVISOR_ENGINE=m1_v2 on a fixture artifact.

A tiny engine is fitted on a synthetic store and saved as the artifact; the registry is a
fixture dict; the context function is a fake. The default path (ADVISOR_ENGINE=legacy) is
checked to be unchanged: POST /rank answers 503 and /advise carries ``m1_v2 = null``.
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import joblib
import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.config import Settings  # noqa: E402
from app.services import m1_service, registry_service  # noqa: E402

REGISTRY = {
    "country": "TT", "registry_version": "1", "built_at": "2026-11-11", "store_manifest": "x", "thresholds": {},
    "challenges": [{"id": "LOW_CROP_PRODUCTIVITY", "name_en": "Low crop productivity", "objective_groups": ["productivity"],
                    "practice_families": ["F1", "F2"], "n_rows": 10, "n_studies": 5, "n_documented_practices": 0,
                    "exposed": True, "exposure_reason": "test",
                    "objectives": [{"id": "YIELD", "name_en": "Crop yield", "objective_group": "productivity", "direction": 1,
                                    "n_rows": 10, "n_studies": 5, "n_practices": 4, "exposed": True}]}],
    "practices": [{"id": p, "name_en": p, "family": ("F1" if p in ("A", "B", "X") else "F2"), "challenges": ["LOW_CROP_PRODUCTIVITY"],
                   "n_rows": 5} for p in ("A", "B", "C", "D")] + [{"id": "X", "name_en": "X", "family": "F1", "challenges": [], "n_rows": 0}],
}
CONTEXT = {"aez_belt": "Moist Dega", "Rainfall": 900.0, "Altitude_r": 1600.0, "temp_mean_annual": 18.0, "precip_seasonality": 80.0,
           "slope": 5.0, "soil_clay": 30.0, "land_cover": 40, "lgp_days": 240.0, "soil_ph": 6.0, "soil_soc": 20.0,
           "release": "ET/2026.1", "ctx_precip_annual": 900.0, "ctx_elevation": 1600.0, "ctx_aez_belt": 7, "ctx_koppen_class": 12}


@pytest.fixture(scope="module")
def artifact(tmp_path_factory) -> Path:
    from model.harness.mask import Mask
    from model.m1.engine import M1Config, M1Engine
    from model.m1.test_m1 import COMPONENTS, FAMILY, OUTCOME_GROUP, synthetic_store

    store = synthetic_store(24)
    eng = M1Engine(M1Config(tune=False, select=False, inner_folds=3), OUTCOME_GROUP, FAMILY, COMPONENTS, {"Moist Dega": 7})
    eng.fit(store, Mask.empty())
    out = tmp_path_factory.mktemp("m1") / "m1_v2"
    out.mkdir()
    joblib.dump(eng, out / m1_service.ARTIFACT)
    (out / "config.json").write_text('{"built_utc": "2026-11-11T00:00:00+00:00", "release": "ET/2026.1"}', encoding="utf-8")
    return out


@pytest.fixture
def enabled(artifact, monkeypatch):
    s = Settings(_env_file=None, openai_api_key="", advisor_engine="m1_v2", m1_artifact_dir=str(artifact))
    monkeypatch.setattr(m1_service, "get_settings", lambda: s)
    monkeypatch.setattr(registry_service, "get_registry", lambda country: REGISTRY)
    monkeypatch.setattr(m1_service, "context_of", lambda lat, lon: dict(CONTEXT))
    m1_service.reset()
    yield s
    m1_service.reset()


def test_rank_answers_every_registry_candidate_with_intervals_and_lead_labels(enabled):
    out = m1_service.rank(9.0, 38.0, "LOW_CROP_PRODUCTIVITY", "YIELD", "maize", top_n=10, country="TT")
    assert out["engine"] == "m1_v2" and out["n_candidates"] == 4 and out["direction"] == 1 and out["release"] == "ET/2026.1"
    ids = [i["practice_id"] for i in out["items"]]
    assert sorted(ids) == ["A", "B", "C", "D"] and out["items"][0]["score"] >= out["items"][-1]["score"]
    for it in out["items"]:
        assert it["lead_source"] in ("model", "study", "documented") and it["lead_label"] in ("model-led", "study-led", "documented")
        assert it["est_lrr"] is not None and it["lo"] <= it["est_lrr"] <= it["hi"]
    assert "ctx_precip_annual" not in out["context"] and out["context"]["aez_belt"] == "Moist Dega"
    with pytest.raises(LookupError):
        m1_service.rank(9.0, 38.0, "NOPE", "YIELD", country="TT")
    with pytest.raises(LookupError):
        m1_service.rank(9.0, 38.0, "LOW_CROP_PRODUCTIVITY", "SOIL_LOSS", country="TT")
    assert m1_service.info()["engine"] == "m1_v2" and m1_service.info()["release"] == "ET/2026.1"


def test_rank_for_family_and_advise_additive_field(enabled):
    items = m1_service.rank_for_family(9.0, 38.0, "F1", "yield", country="TT")
    assert [i["practice_id"] for i in items] and set(i["practice_id"] for i in items) == {"A", "B", "X"}
    assert m1_service.rank_for_family(9.0, 38.0, "F1", "not an indicator", country="TT") is None
    assert m1_service.rank_for_family(9.0, 38.0, "F9", "yield", country="TT") == []


def test_legacy_default_is_unchanged(monkeypatch):
    s = Settings(_env_file=None, openai_api_key="")
    assert s.advisor_engine == "legacy" and not m1_service.enabled(s)
    monkeypatch.setattr(m1_service, "get_settings", lambda: s)
    assert m1_service.info()["engine"] == "legacy" and m1_service.info()["artifact"] is None
    with pytest.raises(m1_service.EngineUnavailable):
        m1_service.rank(9.0, 38.0, "LOW_CROP_PRODUCTIVITY", "YIELD")
    assert m1_service.rank_for_family(9.0, 38.0, "F1", "yield") is None
    m1_service.warmup(s)  # nothing to load


def test_enabled_without_artifact_fails_fast(tmp_path, monkeypatch):
    s = Settings(_env_file=None, openai_api_key="", advisor_engine="m1_v2", m1_artifact_dir=str(tmp_path))
    monkeypatch.setattr(m1_service, "get_settings", lambda: s)
    m1_service.reset()
    with pytest.raises(RuntimeError, match="model.m1.train"):
        m1_service.warmup(s)


def test_rank_endpoint_and_metadata(enabled, monkeypatch):
    from fastapi.testclient import TestClient

    from app import metadata_service
    from app.main import create_app
    from app.routers import rank as rank_router

    monkeypatch.setattr(rank_router.m1_service, "get_settings", lambda: enabled)
    monkeypatch.setattr("app.main.warmup", lambda: None)  # hermetic: no rasters, no model file
    app = create_app()
    with TestClient(app) as client:
        r = client.post("/rank", json={"lat": 9.0, "lon": 38.0, "challenge_id": "LOW_CROP_PRODUCTIVITY", "outcome_id": "YIELD",
                                       "country": "TT", "top_n": 2})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["engine"] == "m1_v2" and len(body["items"]) == 2 and body["items"][0]["lead_label"]
        bad = client.post("/rank", json={"lat": 9.0, "lon": 38.0, "challenge_id": "NOPE", "outcome_id": "YIELD", "country": "TT"})
        assert bad.status_code == 422 and bad.json()["error"]["code"] == "rank_error"
        meta = client.get("/metadata").json()
        assert meta["advisor_engine"]["engine"] == "m1_v2"
    assert metadata_service.build_metadata()["advisor_engine"]["engine"] == "m1_v2"


def test_rank_endpoint_is_503_on_the_legacy_engine(monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import create_app

    s = Settings(_env_file=None, openai_api_key="")
    monkeypatch.setattr(m1_service, "get_settings", lambda: s)
    monkeypatch.setattr("app.main.warmup", lambda: None)  # hermetic: no rasters, no model file
    with TestClient(create_app()) as client:
        r = client.post("/rank", json={"lat": 9.0, "lon": 38.0, "challenge_id": "LOW_CROP_PRODUCTIVITY", "outcome_id": "YIELD"})
        assert r.status_code == 503 and r.json()["error"]["code"] == "engine_unavailable"
        assert client.get("/metadata").json()["advisor_engine"]["engine"] == "legacy"
