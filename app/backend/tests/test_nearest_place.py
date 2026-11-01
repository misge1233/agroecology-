"""U9 (D10): the town a pin is in or near (offline gazetteer)."""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers.geocode import router
from app.services.geocode import nearest_place



def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_a_pin_in_town_gets_its_name():
    name, km = nearest_place(9.68, 39.53)
    assert name == "Debre Birhan" and km < 1


def test_far_from_any_town_gets_no_name():
    assert nearest_place(5.0, 46.5) is None


def test_endpoint_reports_name_and_distance():
    r = _client().get("/geocode/nearest", params={"lat": 9.03, "lon": 38.74})
    assert r.status_code == 200
    body = r.json()
    assert body["found"] is True and body["name"] == "Addis Ababa" and body["distance_km"] < 1
    assert _client().get("/geocode/nearest", params={"lat": 5.0, "lon": 46.5}).json()["found"] is False
