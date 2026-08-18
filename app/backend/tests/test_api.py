"""Backend tests for the lat/long CSA recommender contract."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app
from app.services import recommender_service as svc

DEMO = {
    "lat": 8.38,
    "lon": 39.37,
    "practice_family": "Erosion control and water management",
    "indicator": "soil loss",
    "crop_type": None,
    "top_n": 3,
}


@pytest.fixture(scope="module")
def client():
    app = create_app()
    with TestClient(app) as c:  # triggers lifespan warmup (loads model + rasters)
        yield c


# --------------------------------------------------------------------- health
def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["model_loaded"] is True
    assert "version" in body


# ------------------------------------------------------------------- metadata
def test_metadata_shape(client):
    r = client.get("/metadata")
    assert r.status_code == 200
    body = r.json()
    assert len(body["practice_families"]) == 5
    assert "Erosion control and water management" in body["practice_families"]
    assert len(body["indicators"]) == 7
    keys = [i["key"] for i in body["indicators"]]
    assert "yield" in keys and "soil loss" in keys and "runoff" in keys
    by_fam = body["indicators_by_family"]
    assert len(by_fam) == 5
    livestock = by_fam["Livestock production and management"]
    assert "yield" not in livestock
    assert "water use efficiency" not in livestock
    assert "biomass yield" in livestock
    assert len(body["practices_by_family"]) == 5
    crop_practices = body["practices_by_family"]["Crop production and management"]
    assert "Improved Fallow" in crop_practices or len(crop_practices) >= 10
    for ind in body["indicators"]:
        assert ind["direction"] in ("increase", "reduce")
    assert body["indicators"][-1]["key"] == "runoff"  # order preserved
    assert len(body["crop_types"]) > 10
    assert body["bounds"]["lat"] == [3.3, 14.9]
    assert body["bounds"]["lon"] == [32.9, 48.2]
    assert body["model"]["name"]
    assert body["model"]["cv_r2"] is not None


def test_models_list(client):
    r = client.get("/models")
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 1
    assert items[0]["key"] == "csa_agroecology"
    assert "CSA_practices" in items[0]["features"]


# ------------------------------------------------------------------ recommend
def test_recommend_happy_path(client):
    r = client.post("/recommend", json=DEMO)
    assert r.status_code == 200
    body = r.json()

    # Two-tier shape.
    assert body["query"]["indicator"] == "soil loss"
    assert body["query"]["goal_direction"] == "reduce"
    assert set(body.keys()) == {"query", "recommendations", "details"}

    # Clean list respects top_n and carries only practice + effect.
    assert len(body["recommendations"]) == 3
    for rec in body["recommendations"]:
        assert set(rec.keys()) == {"practice", "effect"}
        assert "soil loss" in rec["effect"]

    # Details block for the "why" view.
    d = body["details"]
    assert d["confidence"] in ("high", "medium", "low")
    assert len(d["ranked"]) == 3
    assert "aez_belt" in d["context"]
    # Evidence-grounded: the top pick has at least one field observation.
    assert d["ranked"][0]["n_evidence"] >= 1


def test_recommend_known_point_sanity(client):
    """lat 8.38, lon 39.37 + Erosion control + soil loss -> mulch/water-harvesting."""
    r = client.post("/recommend", json=DEMO)
    assert r.status_code == 200
    practices = " ".join(x["practice"].lower() for x in r.json()["recommendations"])
    assert "mulch" in practices or "water harvest" in practices


def test_recommend_top_n_respected(client):
    r = client.post("/recommend", json={**DEMO, "top_n": 2})
    assert r.status_code == 200
    body = r.json()
    assert len(body["recommendations"]) == 2
    assert len(body["details"]["ranked"]) == 2


def test_recommend_out_of_bounds(client):
    r = client.post("/recommend", json={**DEMO, "lat": 25.0})
    assert r.status_code == 422
    assert "error" in r.json()


def test_recommend_invalid_enum(client):
    r = client.post("/recommend", json={**DEMO, "indicator": "magic beans"})
    assert r.status_code == 422


def test_recommend_practices_stay_in_practice_family(client):
    """Every recommendation must be from the selected challenge (practice_family) pool."""
    from app.services import recommender_service as svc

    cases = [
        ("Crop production and management", "yield"),
        ("Livestock production and management", "biomass yield"),
        ("Erosion control and water management", "soil loss"),
        ("Integrated soil fertility management", "SOM content"),
        ("Agro-forestry and forest management", "runoff"),
    ]
    for family, indicator in cases:
        allowed = set(svc.practices_by_family()[family])
        r = client.post(
            "/recommend",
            json={**DEMO, "practice_family": family, "indicator": indicator, "top_n": 3},
        )
        assert r.status_code == 200, (family, indicator, r.text)
        for rec in r.json()["recommendations"]:
            assert rec["practice"] in allowed
        scope = r.json()["details"].get("ranking_scope", "")
        assert family in scope


def test_recommend_rejects_livestock_crop_yield(client):
    """Livestock + yield ranks crop irrigation bundles — blocked in UI/API."""
    r = client.post(
        "/recommend",
        json={
            **DEMO,
            "practice_family": "Livestock production and management",
            "indicator": "yield",
        },
    )
    assert r.status_code == 422
    assert "not supported" in r.json()["error"]["message"].lower()


def test_recommend_optional_crop(client):
    r = client.post(
        "/recommend",
        json={**DEMO, "practice_family": "Crop production and management",
              "indicator": "yield", "crop_type": "Maize"},
    )
    assert r.status_code == 200
    assert r.json()["query"]["crop_type"] == "Maize"


# ------------------------------------------------------------ chat (offline)
def test_chat_offline_end_to_end(client, monkeypatch):
    """With no OPENAI_API_KEY, the rule-based advisor still recommends end to end."""
    monkeypatch.setattr(get_settings(), "openai_api_key", "")
    r = client.post(
        "/chat",
        json={
            "message": "My farm is at 8.38, 39.37 and I want to reduce erosion.",
            "history": [],
            "stream": False,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["reply"]
    assert body["recommendation"] is not None
    assert body["recommendation"]["query"]["indicator"] == "soil loss"
    assert len(body["recommendation"]["recommendations"]) >= 1


def test_chat_place_name_soil_loss_debre_birhan(client, monkeypatch):
    """NL with place name must geocode + score evidence — not invent practices."""
    monkeypatch.setattr(get_settings(), "openai_api_key", "")
    r = client.post(
        "/chat",
        json={
            "message": (
                "I want to reduce soil loss on my sloping field near Debre Birhan"
            ),
            "history": [],
            "stream": False,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body.get("error") in (None, "")
    rec = body["recommendation"]
    assert rec is not None
    q = rec["query"]
    assert q["indicator"] == "soil loss"
    assert q["practice_family"] == "Erosion control and water management"
    assert abs(q["lat"] - 9.6795) < 0.05
    assert abs(q["lon"] - 39.5326) < 0.05
    assert len(rec["recommendations"]) >= 1
    # Narrative must mention a scored practice, not free-hallucinated advice only.
    top = rec["recommendations"][0]["practice"]
    assert top.lower() in (body["reply"] or "").lower()
    slots = body.get("slots") or {}
    assert slots.get("is_complete") is True
    assert "contour farming" not in (body["reply"] or "").lower() or top.lower() in (
        body["reply"] or ""
    ).lower()


def test_chat_water_use_efficiency_hawassa(client, monkeypatch):
    """Hyphenated UI phrasing 'water-use efficiency' must score in one turn."""
    monkeypatch.setattr(get_settings(), "openai_api_key", "")
    r = client.post(
        "/chat",
        json={
            "message": (
                "Near Hawassa I have limited water — which water management "
                "practices improve water-use efficiency?"
            ),
            "history": [],
            "stream": False,
        },
    )
    assert r.status_code == 200
    body = r.json()
    rec = body["recommendation"]
    assert rec is not None
    assert rec["query"]["indicator"] == "water use efficiency"
    assert rec["query"]["practice_family"] == "Erosion control and water management"


def test_chat_incomplete_does_not_hallucinate_practices(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "openai_api_key", "")
    r = client.post(
        "/chat",
        json={
            "message": "I want to reduce soil loss on my sloping field",
            "history": [],
            "stream": False,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["recommendation"] is None
    reply = (body["reply"] or "").lower()
    assert "location" in reply
    assert "contour farming" not in reply
    assert "terrace" not in reply


def test_chat_thanks_does_not_re_recommend(client, monkeypatch):
    """Social acknowledgements must reply warmly and never re-call the tool."""
    monkeypatch.setattr(get_settings(), "openai_api_key", "")
    first = client.post(
        "/chat",
        json={
            "message": "My farm is at 8.38, 39.37 and I want to reduce erosion.",
            "history": [],
            "stream": False,
        },
    )
    assert first.status_code == 200
    prior = first.json()["recommendation"]
    assert prior is not None

    thanks = client.post(
        "/chat",
        json={
            "message": "thanks",
            "history": [
                {
                    "role": "user",
                    "content": "My farm is at 8.38, 39.37 and I want to reduce erosion.",
                },
                {"role": "assistant", "content": first.json()["reply"]},
            ],
            "last_recommendation": prior,
            "stream": False,
        },
    )
    assert thanks.status_code == 200
    body = thanks.json()
    assert body["recommendation"] is None
    reply = (body["reply"] or "").lower()
    assert "function=" not in reply
    assert "welcome" in reply or "glad" in reply


def test_strip_leaked_tool_markup():
    from app.services.chat_service import strip_leaked_tool_markup

    leaked = (
        '(function=recommend>{"lat": 9.7036, "lon": 39.5837, '
        '"practice_family": "Crop production and management", '
        '"indicator": "yield", "top_n": 3}</function>"'
    )
    assert strip_leaked_tool_markup(leaked) == ""
    assert "mulch" in strip_leaked_tool_markup("I'd recommend mulch." + leaked)


def test_chat_offline_stream(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "openai_api_key", "")
    with client.stream(
        "POST",
        "/chat",
        json={"message": "8.38, 39.37 reduce erosion", "history": [], "stream": True},
    ) as r:
        assert r.status_code == 200
        assert "text/event-stream" in r.headers["content-type"]
        payload = "".join(r.iter_text())
    assert "recommendation" in payload
    assert "done" in payload


# --------------------------------------------------------- direct engine call
def test_engine_wrapper_direct():
    out = svc.recommend(**{k: DEMO[k] for k in
                           ("lat", "lon", "practice_family", "indicator")}, top_n=3)
    assert out["query"]["indicator"] == "soil loss"
    assert len(out["recommendations"]) == 3
    assert out["details"]["ranked"][0]["n_evidence"] >= 1
