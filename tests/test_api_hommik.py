"""Integration test for POST /api/hommik/calculate.

Exercises the FastAPI route on top of the pure Hommik calculator.
The handler also validates that land-cover percentages sum to ~100,
which we cover here.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


WORKED_EXAMPLE_PAYLOAD = {
    "A_km2": 100.0,
    "p_percent": 10.0,
    "q_bar_k_l_per_s_km2": 7.0,
    "q95_l_per_s_km2": 2.0,
    "landcover": {
        "A_ms": 10.0,
        "A_r": 5.0,
        "A_km": 15.0,
        "B": 30.0,
        "C": 40.0,
        "maaparandus": 20.0,
        "a_wet_mineral_plus_akm": 20.0,
    },
}


def test_calculate_endpoint_returns_worked_example(client: TestClient) -> None:
    response = client.post("/api/hommik/calculate", json=WORKED_EXAMPLE_PAYLOAD)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["q_bar_l_per_s_km2"] == pytest.approx(7.0)
    assert body["Q_veg_max_m3_per_s"] == pytest.approx(3.931, rel=1e-3)
    assert body["Q_kev_max_m3_per_s"] == pytest.approx(7.374, rel=1e-3)
    assert body["q_bar_k_source"] == "placeholder"
    assert body["formula_revision"]  # non-empty


def test_calculate_rejects_bad_landcover_sum(client: TestClient) -> None:
    bad = {**WORKED_EXAMPLE_PAYLOAD, "landcover": {**WORKED_EXAMPLE_PAYLOAD["landcover"]}}
    bad["landcover"]["C"] = 10.0  # total now 50, not ~100
    response = client.post("/api/hommik/calculate", json=bad)
    assert response.status_code == 422
    assert "sum to" in response.json()["detail"]


def test_cartogram_status_endpoint(client: TestClient) -> None:
    response = client.get("/api/hommik/cartogram-status")
    assert response.status_code == 200
    body = response.json()
    assert body["q_bar_k"]["source"] == "placeholder"
    assert body["q_bar_k"]["placeholder_value_l_per_s_km2"] == pytest.approx(7.0)
