"""Tests for backend.services.watershed — find_valgla + delineate_catchment.

Fixture design
--------------
find_valgla tests use a synthetic valglad.fgb with two polygons:
  valgla_a  kkr_code="VEE_A"  box(490_000, 6_490_000, 510_000, 6_510_000)
  valgla_b  kkr_code="VEE_B"  box(510_000, 6_490_000, 530_000, 6_510_000)

delineate_catchment tests use:
  - the committed synthetic_dem_100x100.tif clipped to _CLIP_BOX
    (same fixture as test_preprocess_clip.py)
  - process_valgla() to produce flowdir/flowacc rasters in tmp_path
  - a point near the centroid of the clipped DEM
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import box, Point

from backend.services.watershed import find_valgla, delineate_catchment

# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------

_BOX_A = box(490_000, 6_490_000, 510_000, 6_510_000)
_BOX_B = box(510_000, 6_490_000, 530_000, 6_510_000)
# Centre of box A
_POINT_IN_A = (500_000.0, 6_500_000.0)
# Centre of box B
_POINT_IN_B = (520_000.0, 6_500_000.0)
# Point outside both polygons
_POINT_OUTSIDE = (560_000.0, 6_500_000.0)

# Clip polygon identical to test_preprocess_clip.py
_CLIP_BOX = box(550_050, 6_489_600, 550_450, 6_489_950)
KKR_CODE = "VEE_TEST_001"


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def valglad_fgb(tmp_path_factory: pytest.TempPathFactory) -> Path:
    d = tmp_path_factory.mktemp("valglad")
    gdf = gpd.GeoDataFrame(
        {"kkr_code": ["VEE_A", "VEE_B"], "nimi": ["Valgla A", "Valgla B"]},
        geometry=[_BOX_A, _BOX_B],
        crs="EPSG:3301",
    )
    path = d / "valglad.fgb"
    gdf.to_file(path, driver="FlatGeobuf")
    return path


@pytest.fixture(scope="module")
def flow_grids(tmp_path_factory: pytest.TempPathFactory, fixtures_dir: Path):
    """Pre-built flowdir/flowacc rasters for VEE_TEST_001 in a preprocessed_dir."""
    from scripts.preprocess import clip_dem, process_valgla

    dem_src = fixtures_dir / "synthetic_dem_100x100.tif"
    if not dem_src.exists():
        pytest.skip("synthetic_dem_100x100.tif not found")

    pre = tmp_path_factory.mktemp("preprocessed")
    dem_dir = pre / "dem"
    dem_dir.mkdir()
    clipped = clip_dem(_CLIP_BOX, dem_src, KKR_CODE, dem_dir)
    process_valgla(clipped, KKR_CODE, pre)
    return pre  # contains flowdir/ and flowacc/ subdirs


# ---------------------------------------------------------------------------
# find_valgla tests
# ---------------------------------------------------------------------------


class TestFindValgla:
    def test_returns_correct_kkr_code_for_box_a(self, valglad_fgb: Path) -> None:
        kkr_code, _ = find_valgla(*_POINT_IN_A, valglad_fgb)
        assert kkr_code == "VEE_A"

    def test_returns_correct_kkr_code_for_box_b(self, valglad_fgb: Path) -> None:
        kkr_code, _ = find_valgla(*_POINT_IN_B, valglad_fgb)
        assert kkr_code == "VEE_B"

    def test_returns_polygon(self, valglad_fgb: Path) -> None:
        _, poly = find_valgla(*_POINT_IN_A, valglad_fgb)
        assert poly is not None
        assert poly.is_valid

    def test_polygon_contains_point(self, valglad_fgb: Path) -> None:
        _, poly = find_valgla(*_POINT_IN_A, valglad_fgb)
        assert poly.contains(Point(*_POINT_IN_A))

    def test_raises_value_error_outside_all_polygons(self, valglad_fgb: Path) -> None:
        with pytest.raises(ValueError, match="not within any valgla"):
            find_valgla(*_POINT_OUTSIDE, valglad_fgb)

    def test_raises_file_not_found_for_missing_fgb(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            find_valgla(*_POINT_IN_A, tmp_path / "nonexistent.fgb")


# ---------------------------------------------------------------------------
# delineate_catchment tests
# ---------------------------------------------------------------------------


class TestDelineateCatchment:
    def test_returns_polygon_and_area(self, flow_grids: Path) -> None:
        # Point near the centre of the clipped DEM
        x_c = (550_050 + 550_450) / 2
        y_c = (6_489_600 + 6_489_950) / 2
        poly, area_km2, _ = delineate_catchment(x_c, y_c, KKR_CODE, flow_grids)
        assert poly is not None
        assert area_km2 > 0.0

    def test_catchment_area_is_finite(self, flow_grids: Path) -> None:
        x_c = (550_050 + 550_450) / 2
        y_c = (6_489_600 + 6_489_950) / 2
        _, area_km2, _ = delineate_catchment(x_c, y_c, KKR_CODE, flow_grids)
        import math
        assert math.isfinite(area_km2)

    def test_catchment_area_plausible(self, flow_grids: Path) -> None:
        """The 80×70 cell clipped DEM is 400×350 m → max area ≈ 0.14 km²."""
        x_c = (550_050 + 550_450) / 2
        y_c = (6_489_600 + 6_489_950) / 2
        _, area_km2, _ = delineate_catchment(x_c, y_c, KKR_CODE, flow_grids)
        assert area_km2 <= 0.2, f"Area {area_km2:.4f} km² exceeds DEM extent"

    def test_raises_file_not_found_for_missing_flowdir(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError, match="flowdir"):
            delineate_catchment(550_250.0, 6_489_775.0, "NO_SUCH_CODE", tmp_path)

    def test_raises_file_not_found_for_missing_flowacc(
        self, flow_grids: Path, tmp_path: Path
    ) -> None:
        """Provide flowdir but not flowacc → FileNotFoundError."""
        pre = tmp_path / "partial"
        (pre / "flowdir").mkdir(parents=True)
        import shutil
        shutil.copy(
            flow_grids / "flowdir" / f"{KKR_CODE}.tif",
            pre / "flowdir" / f"{KKR_CODE}.tif",
        )
        # flowacc/ does not exist
        with pytest.raises(FileNotFoundError, match="flowacc"):
            delineate_catchment(550_250.0, 6_489_775.0, KKR_CODE, pre)
