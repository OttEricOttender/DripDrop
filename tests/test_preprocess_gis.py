"""Phase 2 GIS preprocessing tests — synthetic DEM fixture.

These tests define the public interface of ``scripts/preprocess.py`` and are
written *before* the implementation so the implementation has a clear target.
Running the suite before preprocess.py exists will produce ``ImportError`` on
the import block — that is the expected starting state.

Fixture design (see tests/fixtures/make_synthetic_dem.py for details):
  100 × 100 cells, 5 m resolution, EPSG:3301, float32, nodata = -9999.
  Elevation:  elev[i, j] = max(0, 100 - 2·i + |j - 50| · 0.3)
  Valley axis at col 50 drains south; outlet cell is (99, 50).
  One artificial pit at (20, 50): elevation set 2 m below both neighbours.

Testing conventions (same as test_hommik.py):
  - Each function under test has at least one atomic test.
  - Numeric assertions use pytest.approx or explicit tolerances.
  - No I/O other than reading the committed fixture and tmp_path writes.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Interface we expect scripts/preprocess.py to export.
# All tests in this module will fail with ImportError until Phase 2 lands.
# ---------------------------------------------------------------------------
from scripts.preprocess import (
    DIRMAP,
    compute_flowacc,
    compute_flowdir,
    condition_dem,
    load_dem,
    read_manifest,
    write_manifest,
)

# ---------------------------------------------------------------------------
# Constants mirroring the fixture design (must match make_synthetic_dem.py)
# ---------------------------------------------------------------------------
PIT_ROW, PIT_COL = 20, 50
OUTLET_ROW, OUTLET_COL = 99, 50
TOTAL_CELLS = 100 * 100
NODATA = np.float32(-9999.0)


# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def dem_path(fixtures_dir: Path) -> Path:
    p = fixtures_dir / "synthetic_dem_100x100.tif"
    if not p.exists():
        pytest.skip("synthetic_dem_100x100.tif not found — run make_synthetic_dem.py")
    return p


# ---------------------------------------------------------------------------
# 1. Fixture readability
# ---------------------------------------------------------------------------


class TestDemFixture:
    def test_shape(self, dem_path: Path) -> None:
        import rasterio
        with rasterio.open(dem_path) as src:
            assert (src.height, src.width) == (100, 100)

    def test_crs_is_lest97(self, dem_path: Path) -> None:
        import rasterio
        with rasterio.open(dem_path) as src:
            assert src.crs.to_epsg() == 3301

    def test_nodata_is_float32_sentinel(self, dem_path: Path) -> None:
        import rasterio
        with rasterio.open(dem_path) as src:
            assert src.nodata == pytest.approx(-9999.0)

    def test_pit_cell_is_below_neighbours(self, dem_path: Path) -> None:
        """Confirm the synthetic pit is present before conditioning."""
        import rasterio
        with rasterio.open(dem_path) as src:
            arr = src.read(1)
        pit = float(arr[PIT_ROW, PIT_COL])
        north = float(arr[PIT_ROW - 1, PIT_COL])
        south = float(arr[PIT_ROW + 1, PIT_COL])
        assert pit < north
        assert pit < south


# ---------------------------------------------------------------------------
# 2. load_dem
# ---------------------------------------------------------------------------


class TestLoadDem:
    def test_returns_grid_and_raster(self, dem_path: Path) -> None:
        from pysheds.grid import Grid
        from pysheds.sview import Raster
        grid, dem = load_dem(dem_path)
        assert isinstance(grid, Grid)
        assert isinstance(dem, Raster)

    def test_raster_shape(self, dem_path: Path) -> None:
        _, dem = load_dem(dem_path)
        assert dem.shape == (100, 100)

    def test_raster_nodata(self, dem_path: Path) -> None:
        _, dem = load_dem(dem_path)
        assert dem.nodata == pytest.approx(-9999.0)


# ---------------------------------------------------------------------------
# 3. condition_dem — fill_pits + fill_depressions + resolve_flats
# ---------------------------------------------------------------------------


class TestConditionDem:
    def test_returns_raster(self, dem_path: Path) -> None:
        from pysheds.sview import Raster
        grid, dem = load_dem(dem_path)
        conditioned = condition_dem(grid, dem)
        assert isinstance(conditioned, Raster)

    def test_fill_pits_removes_synthetic_pit(self, dem_path: Path) -> None:
        """After conditioning, the injected pit cell must be raised."""
        grid, dem = load_dem(dem_path)
        original_pit = float(dem[PIT_ROW, PIT_COL])   # 56.0 m
        conditioned = condition_dem(grid, dem)
        conditioned_pit = float(conditioned[PIT_ROW, PIT_COL])
        # fill_pits raises a single-cell pit to the level of its lowest neighbour
        assert conditioned_pit > original_pit

    def test_conditioned_shape_unchanged(self, dem_path: Path) -> None:
        grid, dem = load_dem(dem_path)
        conditioned = condition_dem(grid, dem)
        assert conditioned.shape == dem.shape

    def test_no_nodata_in_valid_area(self, dem_path: Path) -> None:
        """Conditioning must not introduce nodata cells where there were none."""
        grid, dem = load_dem(dem_path)
        conditioned = condition_dem(grid, dem)
        arr = np.asarray(conditioned)
        assert np.all(arr != NODATA)


# ---------------------------------------------------------------------------
# 4. compute_flowdir — D8 flow direction
# ---------------------------------------------------------------------------


class TestComputeFlowdir:
    def test_returns_raster(self, dem_path: Path) -> None:
        from pysheds.sview import Raster
        grid, dem = load_dem(dem_path)
        conditioned = condition_dem(grid, dem)
        fdir = compute_flowdir(grid, conditioned)
        assert isinstance(fdir, Raster)

    def test_all_interior_cells_have_valid_d8_direction(self, dem_path: Path) -> None:
        """Every interior cell must carry a value from DIRMAP (no orphaned cells)."""
        grid, dem = load_dem(dem_path)
        conditioned = condition_dem(grid, dem)
        fdir = compute_flowdir(grid, conditioned)
        arr = np.asarray(fdir, dtype=np.int32)
        # Edge cells may drain off-grid (value 0); interior cells must be in DIRMAP.
        interior = arr[1:-1, 1:-1]
        valid = set(DIRMAP)
        unique_vals = set(interior.ravel().tolist())
        assert unique_vals.issubset(valid), (
            f"Unexpected flow direction values in interior: {unique_vals - valid}"
        )

    def test_dirmap_has_eight_directions(self) -> None:
        """Sanity: DIRMAP exported from preprocess matches the D8 convention."""
        assert len(DIRMAP) == 8
        # Powers of 2 from the D8 encoding used throughout the codebase
        assert set(DIRMAP) == {1, 2, 4, 8, 16, 32, 64, 128}


# ---------------------------------------------------------------------------
# 5. compute_flowacc — flow accumulation
# ---------------------------------------------------------------------------


class TestComputeFlowacc:
    def test_returns_raster(self, dem_path: Path) -> None:
        from pysheds.sview import Raster
        grid, dem = load_dem(dem_path)
        conditioned = condition_dem(grid, dem)
        fdir = compute_flowdir(grid, conditioned)
        acc = compute_flowacc(grid, fdir)
        assert isinstance(acc, Raster)

    def test_accumulation_nonnegative(self, dem_path: Path) -> None:
        grid, dem = load_dem(dem_path)
        conditioned = condition_dem(grid, dem)
        fdir = compute_flowdir(grid, conditioned)
        acc = compute_flowacc(grid, fdir)
        assert float(np.asarray(acc).min()) >= 0.0

    def test_outlet_has_high_accumulation(self, dem_path: Path) -> None:
        """Outlet cell (99,50) drains most of the 100×100 catchment."""
        grid, dem = load_dem(dem_path)
        conditioned = condition_dem(grid, dem)
        fdir = compute_flowdir(grid, conditioned)
        acc = compute_flowacc(grid, fdir)
        outlet_acc = float(np.asarray(acc)[OUTLET_ROW, OUTLET_COL])
        # At least half the grid's cells drain through the outlet
        assert outlet_acc > TOTAL_CELLS * 0.5

    def test_accumulation_increases_downstream_along_valley(self, dem_path: Path) -> None:
        """Flow accumulation must increase monotonically along the valley axis (col 50)."""
        grid, dem = load_dem(dem_path)
        conditioned = condition_dem(grid, dem)
        fdir = compute_flowdir(grid, conditioned)
        acc = compute_flowacc(grid, fdir)
        arr = np.asarray(acc)
        north = float(arr[50, 50])
        mid = float(arr[70, 50])
        south = float(arr[90, 50])
        assert north < mid < south, (
            f"Expected acc[50,50] < acc[70,50] < acc[90,50]; got {north:.0f} < {mid:.0f} < {south:.0f}"
        )


# ---------------------------------------------------------------------------
# 6. Manifest round-trip — write_manifest / read_manifest
# ---------------------------------------------------------------------------


class TestManifestRoundtrip:
    def _sample_entry(self) -> dict:
        return {
            "name": "synthetic_test_dataset",
            "source_url": "https://example.com/synthetic.tif",
            "sha256": "a" * 64,
            "retrieved_at": "2026-05-15T00:00:00Z",
            "crs": "EPSG:3301",
            "resolution_m": 5.0,
            "output_path": "data/preprocessed/dem/test.tif",
        }

    def _sample_manifest(self) -> dict:
        return {
            "schema_version": 1,
            "manifest_version": "0.2.0-phase2-test",
            "generated_at": "2026-05-15T00:00:00Z",
            "formula_revision": "TY-protsess-2024-v1",
            "notes": ["test manifest"],
            "datasets": [self._sample_entry()],
            "placeholders": {
                "q_bar_k": {
                    "in_use": True,
                    "value_l_per_s_km2": 7.0,
                }
            },
        }

    def test_roundtrip_preserves_all_fields(self, tmp_path: Path) -> None:
        manifest = self._sample_manifest()
        out = tmp_path / "datasets.lock.json"
        write_manifest(manifest, out)
        loaded = read_manifest(out)
        assert loaded == manifest

    def test_written_file_is_valid_json(self, tmp_path: Path) -> None:
        out = tmp_path / "datasets.lock.json"
        write_manifest(self._sample_manifest(), out)
        with open(out) as f:
            parsed = json.load(f)
        assert parsed["schema_version"] == 1

    def test_written_file_is_indented(self, tmp_path: Path) -> None:
        """Manifest must be human-readable (indented), not a single line."""
        out = tmp_path / "datasets.lock.json"
        write_manifest(self._sample_manifest(), out)
        text = out.read_text()
        assert "\n" in text

    def test_dataset_entry_fields_present(self, tmp_path: Path) -> None:
        required = {"name", "source_url", "sha256", "retrieved_at",
                    "crs", "resolution_m", "output_path"}
        out = tmp_path / "datasets.lock.json"
        write_manifest(self._sample_manifest(), out)
        loaded = read_manifest(out)
        entry_keys = set(loaded["datasets"][0].keys())
        assert required.issubset(entry_keys)
