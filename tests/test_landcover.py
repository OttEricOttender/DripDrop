"""Tests for backend.services.landcover — compute_landcover.

Fixture design
--------------
A synthetic catchment polygon in EPSG:3301:
  box(500_000, 6_490_000, 510_000, 6_500_000)  → area = 10 km × 10 km = 100 km²

Kolvikud polygons tiling the catchment (non-overlapping):
  kood 305 (B)  box(500_000, 6_490_000, 505_000, 6_500_000) → 50 km² = 50 %
  kood 306      box(505_000, 6_490_000, 510_000, 6_500_000) → 50 km² = 50 %

msr_vork polygon covering the eastern half of the kood-306 area:
  box(507_500, 6_490_000, 510_000, 6_500_000) → 25 km² = 25 % of catchment
                                               → 50 % of the 306 area

Expected breakdown (all % of 100 km² catchment):
  B          = 50 %
  C          = 0 %
  A_km       = 25 %   (306 ∩ msr_vork)
  A_ms       = 20 %   (80 % of 25 km² non-drained wetland)
  A_r        = 5 %    (20 % of 25 km² non-drained wetland)
  maaparandus = 25 %  (25 km² msr_vork / 100 km²)
  a_wet_mineral_plus_akm = 25 % (= A_km)
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import box

from backend.services.landcover import compute_landcover

# ---------------------------------------------------------------------------
# Geometry constants
# ---------------------------------------------------------------------------

_CATCHMENT = box(500_000, 6_490_000, 510_000, 6_500_000)  # 100 km²
_CATCHMENT_KM2 = 100.0

_KOLVIK_B = box(500_000, 6_490_000, 505_000, 6_500_000)   # 50 km², kood 305
_KOLVIK_WET = box(505_000, 6_490_000, 510_000, 6_500_000)  # 50 km², kood 306

_MSR_EAST = box(507_500, 6_490_000, 510_000, 6_500_000)    # 25 km² ∩ kood-306


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def kolvikud_fgb(tmp_path_factory: pytest.TempPathFactory) -> Path:
    d = tmp_path_factory.mktemp("kolvikud")
    gdf = gpd.GeoDataFrame(
        {"kood": [305, 306], "kood_t": ["puittaimestik", "märgala"]},
        geometry=[_KOLVIK_B, _KOLVIK_WET],
        crs="EPSG:3301",
    )
    path = d / "kolvikud.fgb"
    gdf.to_file(path, driver="FlatGeobuf")
    return path


@pytest.fixture(scope="module")
def msr_vork_fgb(tmp_path_factory: pytest.TempPathFactory) -> Path:
    d = tmp_path_factory.mktemp("msr")
    gdf = gpd.GeoDataFrame(
        {"ms_kood": ["MSR-001"]},
        geometry=[_MSR_EAST],
        crs="EPSG:3301",
    )
    path = d / "msr_vork.fgb"
    gdf.to_file(path, driver="FlatGeobuf")
    return path


@pytest.fixture(scope="module")
def empty_msr_fgb(tmp_path_factory: pytest.TempPathFactory) -> Path:
    d = tmp_path_factory.mktemp("empty_msr")
    gdf = gpd.GeoDataFrame({"ms_kood": []}, geometry=gpd.GeoSeries([], crs="EPSG:3301"))
    path = d / "msr_vork_empty.fgb"
    gdf.to_file(path, driver="FlatGeobuf")
    return path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestComputeLandcover:
    def test_B_is_50_percent(self, kolvikud_fgb: Path, msr_vork_fgb: Path) -> None:
        breakdown, _ = compute_landcover(_CATCHMENT, _CATCHMENT_KM2, kolvikud_fgb, msr_vork_fgb)
        assert breakdown.B == pytest.approx(50.0, abs=1.0)

    def test_C_is_zero(self, kolvikud_fgb: Path, msr_vork_fgb: Path) -> None:
        breakdown, _ = compute_landcover(_CATCHMENT, _CATCHMENT_KM2, kolvikud_fgb, msr_vork_fgb)
        assert breakdown.C == pytest.approx(0.0, abs=0.5)

    def test_A_km_is_25_percent(self, kolvikud_fgb: Path, msr_vork_fgb: Path) -> None:
        breakdown, _ = compute_landcover(_CATCHMENT, _CATCHMENT_KM2, kolvikud_fgb, msr_vork_fgb)
        assert breakdown.A_km == pytest.approx(25.0, abs=1.0)

    def test_A_ms_is_80pct_of_non_drained(self, kolvikud_fgb: Path, msr_vork_fgb: Path) -> None:
        """Non-drained wetland = 25 km² (50-25); A_ms = 80% × 25 = 20 km² = 20%."""
        breakdown, _ = compute_landcover(_CATCHMENT, _CATCHMENT_KM2, kolvikud_fgb, msr_vork_fgb)
        assert breakdown.A_ms == pytest.approx(20.0, abs=1.0)

    def test_A_r_is_20pct_of_non_drained(self, kolvikud_fgb: Path, msr_vork_fgb: Path) -> None:
        """A_r = 20% × 25 = 5 km² = 5%."""
        breakdown, _ = compute_landcover(_CATCHMENT, _CATCHMENT_KM2, kolvikud_fgb, msr_vork_fgb)
        assert breakdown.A_r == pytest.approx(5.0, abs=1.0)

    def test_maaparandus_is_25_percent(self, kolvikud_fgb: Path, msr_vork_fgb: Path) -> None:
        breakdown, _ = compute_landcover(_CATCHMENT, _CATCHMENT_KM2, kolvikud_fgb, msr_vork_fgb)
        assert breakdown.maaparandus == pytest.approx(25.0, abs=1.0)

    def test_a_wet_mineral_plus_akm_equals_A_km(
        self, kolvikud_fgb: Path, msr_vork_fgb: Path
    ) -> None:
        breakdown, _ = compute_landcover(_CATCHMENT, _CATCHMENT_KM2, kolvikud_fgb, msr_vork_fgb)
        assert breakdown.a_wet_mineral_plus_akm == pytest.approx(breakdown.A_km, abs=0.01)

    def test_returns_warnings_list(self, kolvikud_fgb: Path, msr_vork_fgb: Path) -> None:
        _, warnings = compute_landcover(_CATCHMENT, _CATCHMENT_KM2, kolvikud_fgb, msr_vork_fgb)
        assert isinstance(warnings, list)
        assert len(warnings) > 0

    def test_maaparandus_warning_present(self, kolvikud_fgb: Path, msr_vork_fgb: Path) -> None:
        _, warnings = compute_landcover(_CATCHMENT, _CATCHMENT_KM2, kolvikud_fgb, msr_vork_fgb)
        assert any("maaparandus" in w.lower() for w in warnings)

    def test_no_msr_vork_all_wetland_is_non_drained(
        self, kolvikud_fgb: Path, empty_msr_fgb: Path
    ) -> None:
        """When msr_vork is empty, all 306 area goes to A_ms + A_r."""
        breakdown, _ = compute_landcover(_CATCHMENT, _CATCHMENT_KM2, kolvikud_fgb, empty_msr_fgb)
        assert breakdown.A_km == pytest.approx(0.0, abs=0.5)
        assert breakdown.A_ms == pytest.approx(40.0, abs=1.0)  # 80% × 50 km²
        assert breakdown.A_r == pytest.approx(10.0, abs=1.0)   # 20% × 50 km²

    def test_missing_msr_vork_fgb_uses_zero(
        self, kolvikud_fgb: Path, tmp_path: Path
    ) -> None:
        """Missing msr_vork.fgb should not raise — just zero maaparandus."""
        missing = tmp_path / "no_msr.fgb"
        breakdown, _ = compute_landcover(_CATCHMENT, _CATCHMENT_KM2, kolvikud_fgb, missing)
        assert breakdown.maaparandus == pytest.approx(0.0, abs=0.5)
        assert breakdown.A_km == pytest.approx(0.0, abs=0.5)

    def test_all_values_in_0_to_100(self, kolvikud_fgb: Path, msr_vork_fgb: Path) -> None:
        breakdown, _ = compute_landcover(_CATCHMENT, _CATCHMENT_KM2, kolvikud_fgb, msr_vork_fgb)
        for field, val in breakdown.model_dump().items():
            assert 0.0 <= val <= 100.0, f"{field}={val} out of [0, 100]"

    def test_c_codes_map_to_C(self, tmp_path: Path, msr_vork_fgb: Path) -> None:
        """ETAK codes 301–304 must all accumulate into C."""
        gdf = gpd.GeoDataFrame(
            {"kood": [301, 302, 303, 304]},
            geometry=[
                box(500_000, 6_490_000, 502_000, 6_492_500),
                box(502_000, 6_490_000, 504_000, 6_492_500),
                box(504_000, 6_490_000, 506_000, 6_492_500),
                box(506_000, 6_490_000, 508_000, 6_492_500),
            ],
            crs="EPSG:3301",
        )
        path = tmp_path / "kolvikud_c.fgb"
        gdf.to_file(path, driver="FlatGeobuf")
        breakdown, _ = compute_landcover(_CATCHMENT, _CATCHMENT_KM2, path, msr_vork_fgb)
        assert breakdown.C > 0.0
        assert breakdown.B == pytest.approx(0.0, abs=0.5)
