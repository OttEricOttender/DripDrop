"""Tests for POST /api/analyze — the Phase 3 orchestration endpoint.

Strategy
--------
All GIS services (snap, watershed, landcover, cartogram) are monkeypatched
so tests run without any preprocessed files on disk.  The worked-example
values from tests/test_hommik.py are used as service return values to verify
the pipeline end-to-end.

Worked example (from TestComputeWorkedExample in test_hommik.py):
  A_km2 = 100.0, p = 10 %, q_bar_k = 7.0, q95 = 2.0
  Landcover: A_ms=20, A_r=5, A_km=25, B=50, C=0, maaparandus=25,
             a_wet_mineral_plus_akm=25
  Expected: Q_veg_max ≈ 3.931 m³/s, Q_kev_max ≈ 7.374 m³/s
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from shapely.geometry import box

from backend.main import create_app
from backend.models.schemas import LandCoverBreakdown, RiverInfo
from backend.services.cartogram import CartogramSample

# ---------------------------------------------------------------------------
# Shared constants — worked example
# ---------------------------------------------------------------------------

_CATCHMENT_AREA_KM2 = 100.0
_CATCHMENT_POLY = box(500_000, 6_490_000, 510_000, 6_500_000)

_RIVER_INFO = RiverInfo(
    code="VEE-001",
    name="Suur Jõgi",
    river_type="jõgi",
    length_m=50_000.0,
    is_main=True,
)

_LANDCOVER = LandCoverBreakdown(
    A_ms=10.0,
    A_r=5.0,
    A_km=15.0,
    B=30.0,
    C=40.0,
    maaparandus=20.0,
    a_wet_mineral_plus_akm=20.0,
)

_Q_BAR_K = CartogramSample(value_l_per_s_km2=7.0, source="placeholder", raster_path=None)
_Q95 = CartogramSample(value_l_per_s_km2=2.0, source="placeholder", raster_path=None)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_client_with_rivers(tmp_path: Path) -> tuple[TestClient, Path]:
    """Create a TestClient for an app instance with a fake rivers.fgb on disk."""
    import geopandas as gpd
    from shapely.geometry import LineString

    pre = tmp_path / "preprocessed"
    pre.mkdir(parents=True)
    rivers_fgb = pre / "rivers.fgb"
    gdf = gpd.GeoDataFrame(
        {"kood": ["VEE-001"], "nimi": ["Suur Jõgi"], "tyyp": ["jõgi"],
         "pikkus": [50_000.0], "is_peajogi": [True]},
        geometry=[LineString([(500_000, 6_500_000), (510_000, 6_500_000)])],
        crs="EPSG:3301",
    )
    gdf.to_file(rivers_fgb, driver="FlatGeobuf")
    return TestClient(create_app()), pre


def _patch_all(pre: Path):
    """Return a stack of patches that stub out every GIS service call."""
    return [
        patch(
            "backend.api.routes.analyze.snap.snap_to_stream",
            return_value=((505_000.0, 6_500_000.0), _RIVER_INFO, 100.0),
        ),
        patch(
            "backend.api.routes.analyze.watershed.find_valgla",
            return_value=("VEE_A", _CATCHMENT_POLY),
        ),
        patch(
            "backend.api.routes.analyze.watershed.delineate_catchment",
            return_value=(_CATCHMENT_POLY, _CATCHMENT_AREA_KM2, 5),
        ),
        patch(
            "backend.api.routes.analyze.landcover.compute_landcover",
            return_value=(_LANDCOVER, ["test warning"]),
        ),
        patch(
            "backend.api.routes.analyze.cartogram.sample_q_bar_k",
            return_value=_Q_BAR_K,
        ),
        patch(
            "backend.api.routes.analyze.cartogram.sample_q95",
            return_value=_Q95,
        ),
        patch(
            "backend.api.routes.analyze._preprocessed_dir",
            return_value=pre,
        ),
    ]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAnalyzeEndpoint:
    def test_returns_200_with_wgs84_input(self, tmp_path: Path) -> None:
        client, pre = _make_client_with_rivers(tmp_path)
        patches = _patch_all(pre)
        with _apply_patches(patches):
            resp = client.post(
                "/api/analyze",
                json={"point_wgs84": {"lat": 59.0, "lon": 25.0}, "p_percent": 10.0},
            )
        assert resp.status_code == 200

    def test_returns_200_with_lest97_input(self, tmp_path: Path) -> None:
        client, pre = _make_client_with_rivers(tmp_path)
        patches = _patch_all(pre)
        with _apply_patches(patches):
            resp = client.post(
                "/api/analyze",
                json={"point_lest97": {"x": 505_000.0, "y": 6_500_000.0}},
            )
        assert resp.status_code == 200

    def test_q_kev_max_matches_worked_example(self, tmp_path: Path) -> None:
        client, pre = _make_client_with_rivers(tmp_path)
        patches = _patch_all(pre)
        with _apply_patches(patches):
            resp = client.post(
                "/api/analyze",
                json={"point_lest97": {"x": 505_000.0, "y": 6_500_000.0}},
            )
        data = resp.json()
        assert data["hommik"]["Q_kev_max_m3_per_s"] == pytest.approx(7.374, rel=1e-2)

    def test_q_veg_max_matches_worked_example(self, tmp_path: Path) -> None:
        client, pre = _make_client_with_rivers(tmp_path)
        patches = _patch_all(pre)
        with _apply_patches(patches):
            resp = client.post(
                "/api/analyze",
                json={"point_lest97": {"x": 505_000.0, "y": 6_500_000.0}},
            )
        data = resp.json()
        assert data["hommik"]["Q_veg_max_m3_per_s"] == pytest.approx(3.931, rel=1e-2)

    def test_response_has_run_id(self, tmp_path: Path) -> None:
        client, pre = _make_client_with_rivers(tmp_path)
        patches = _patch_all(pre)
        with _apply_patches(patches):
            resp = client.post(
                "/api/analyze",
                json={"point_lest97": {"x": 505_000.0, "y": 6_500_000.0}},
            )
        data = resp.json()
        assert "run_id" in data
        assert len(data["run_id"]) == 32  # uuid4().hex

    def test_response_has_warnings(self, tmp_path: Path) -> None:
        client, pre = _make_client_with_rivers(tmp_path)
        patches = _patch_all(pre)
        with _apply_patches(patches):
            resp = client.post(
                "/api/analyze",
                json={"point_lest97": {"x": 505_000.0, "y": 6_500_000.0}},
            )
        data = resp.json()
        assert isinstance(data["warnings"], list)

    def test_q_bar_k_source_is_placeholder(self, tmp_path: Path) -> None:
        client, pre = _make_client_with_rivers(tmp_path)
        patches = _patch_all(pre)
        with _apply_patches(patches):
            resp = client.post(
                "/api/analyze",
                json={"point_lest97": {"x": 505_000.0, "y": 6_500_000.0}},
            )
        data = resp.json()
        assert data["hommik"]["q_bar_k_source"] == "placeholder"

    def test_422_when_both_coordinate_types_provided(self, tmp_path: Path) -> None:
        client, pre = _make_client_with_rivers(tmp_path)
        resp = client.post(
            "/api/analyze",
            json={
                "point_wgs84": {"lat": 59.0, "lon": 25.0},
                "point_lest97": {"x": 505_000.0, "y": 6_500_000.0},
            },
        )
        assert resp.status_code == 422

    def test_422_when_no_coordinate_provided(self, tmp_path: Path) -> None:
        client, pre = _make_client_with_rivers(tmp_path)
        resp = client.post("/api/analyze", json={"p_percent": 10.0})
        assert resp.status_code == 422

    def test_503_when_rivers_fgb_missing(self, tmp_path: Path) -> None:
        """No rivers.fgb on disk → 503 before any GIS work is attempted."""
        pre = tmp_path / "empty_preprocessed"
        pre.mkdir()
        client = TestClient(create_app())
        with patch("backend.api.routes.analyze._preprocessed_dir", return_value=pre):
            resp = client.post(
                "/api/analyze",
                json={"point_lest97": {"x": 505_000.0, "y": 6_500_000.0}},
            )
        assert resp.status_code == 503

    def test_snap_distance_in_response(self, tmp_path: Path) -> None:
        client, pre = _make_client_with_rivers(tmp_path)
        patches = _patch_all(pre)
        with _apply_patches(patches):
            resp = client.post(
                "/api/analyze",
                json={"point_lest97": {"x": 505_000.0, "y": 6_500_000.0}},
            )
        data = resp.json()
        assert data["snap_distance_m"] == pytest.approx(100.0)

    def test_river_info_in_response(self, tmp_path: Path) -> None:
        client, pre = _make_client_with_rivers(tmp_path)
        patches = _patch_all(pre)
        with _apply_patches(patches):
            resp = client.post(
                "/api/analyze",
                json={"point_lest97": {"x": 505_000.0, "y": 6_500_000.0}},
            )
        data = resp.json()
        assert data["river"]["code"] == "VEE-001"
        assert data["river"]["name"] == "Suur Jõgi"

    def test_catchment_dem_resolution_default_5m(self, tmp_path: Path) -> None:
        client, pre = _make_client_with_rivers(tmp_path)
        patches = _patch_all(pre)
        with _apply_patches(patches):
            resp = client.post(
                "/api/analyze",
                json={"point_lest97": {"x": 505_000.0, "y": 6_500_000.0}},
            )
        data = resp.json()
        assert data["catchment"]["dem_resolution_m"] == 5

    def test_low_res_dem_adds_warning(self, tmp_path: Path) -> None:
        """A 25 m DEM (large-basin fallback) must produce a resolution warning."""
        client, pre = _make_client_with_rivers(tmp_path)
        low_res_patches = [
            patch(
                "backend.api.routes.analyze.watershed.delineate_catchment",
                return_value=(_CATCHMENT_POLY, _CATCHMENT_AREA_KM2, 25),
            ),
        ] + [p for p in _patch_all(pre) if p.attribute != "delineate_catchment"]
        with _apply_patches(low_res_patches):
            resp = client.post(
                "/api/analyze",
                json={"point_lest97": {"x": 505_000.0, "y": 6_500_000.0}},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["catchment"]["dem_resolution_m"] == 25
        assert any("25 m" in w for w in data["warnings"])


# ---------------------------------------------------------------------------
# Helper — apply a list of context managers in sequence
# ---------------------------------------------------------------------------

from contextlib import contextmanager, nullcontext as contextlib_nullcontext


@contextmanager
def _apply_patches(patch_list):
    """Enter all patches in *patch_list* and yield."""
    if not patch_list:
        yield
        return
    with patch_list[0]:
        with _apply_patches(patch_list[1:]):
            yield
