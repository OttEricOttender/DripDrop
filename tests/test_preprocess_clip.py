"""Phase 2 clip + flow-grid tests — clip_dem and process_valgla.

clip_dem
--------
Clips the national DTM to a single valgla polygon using rasterio masked
windows (only the bounding-box window is loaded, so memory is bounded even
against the 50 GB Estonian DTM).

process_valgla
--------------
Reads the clipped DEM, runs the full pysheds conditioning chain
(condition_dem → compute_flowdir → compute_flowacc), and writes the results
as GeoTIFFs.  This is the hot path of the preprocessing loop.

Fixture design
--------------
All tests use the committed synthetic_dem_100x100.tif (550000–550500 E,
6489500–6490000 N, 5 m cells, EPSG:3301) as the source DEM.

Clip polygon:
    box(550050, 6489600, 550450, 6489950)
    Covers roughly columns 10–90, rows 10–80 (≈80 × 70 interior cells).
    Entirely inside the DEM so there are no edge-of-raster nodata artefacts
    from the clip itself.

KKR_CODE = "VEE_TEST_001" — the key used to name output files.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import rasterio
from shapely.geometry import box

from scripts.preprocess import DIRMAP, DEM_NODATA, clip_dem, process_valgla

# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------

# Central portion of the synthetic DEM — avoids edge cells of the source raster.
# x: 550050–550450 (cols 10–90), y: 6489600–6489950 (rows 10–80)
_CLIP_BOX = box(550_050, 6_489_600, 550_450, 6_489_950)
KKR_CODE = "VEE_TEST_001"


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def dem_src(fixtures_dir: Path) -> Path:
    """The committed 100×100 synthetic DEM in EPSG:3301."""
    p = fixtures_dir / "synthetic_dem_100x100.tif"
    if not p.exists():
        pytest.skip("synthetic_dem_100x100.tif not found — run make_synthetic_dem.py")
    return p


@pytest.fixture()
def dem_clip_dir(tmp_path: Path) -> Path:
    d = tmp_path / "dem"
    d.mkdir()
    return d


@pytest.fixture()
def clipped_dem(dem_src: Path, dem_clip_dir: Path) -> Path:
    """Pre-clipped DEM used by process_valgla tests."""
    return clip_dem(_CLIP_BOX, dem_src, KKR_CODE, dem_clip_dir)


# ---------------------------------------------------------------------------
# clip_dem tests
# ---------------------------------------------------------------------------


class TestClipDem:
    def test_output_exists(self, dem_src: Path, dem_clip_dir: Path) -> None:
        result = clip_dem(_CLIP_BOX, dem_src, KKR_CODE, dem_clip_dir)
        assert result.exists()

    def test_output_path_uses_kkr_code(self, dem_src: Path, dem_clip_dir: Path) -> None:
        result = clip_dem(_CLIP_BOX, dem_src, KKR_CODE, dem_clip_dir)
        assert result.stem == KKR_CODE

    def test_output_in_output_dir(self, dem_src: Path, dem_clip_dir: Path) -> None:
        result = clip_dem(_CLIP_BOX, dem_src, KKR_CODE, dem_clip_dir)
        assert result.parent == dem_clip_dir

    def test_output_crs_is_lest97(self, dem_src: Path, dem_clip_dir: Path) -> None:
        result = clip_dem(_CLIP_BOX, dem_src, KKR_CODE, dem_clip_dir)
        with rasterio.open(result) as src:
            assert src.crs.to_epsg() == 3301

    def test_output_nodata_is_dem_nodata(self, dem_src: Path, dem_clip_dir: Path) -> None:
        result = clip_dem(_CLIP_BOX, dem_src, KKR_CODE, dem_clip_dir)
        with rasterio.open(result) as src:
            assert src.nodata == pytest.approx(float(DEM_NODATA))

    def test_clipped_smaller_than_source(self, dem_src: Path, dem_clip_dir: Path) -> None:
        """Clip must reduce the raster extent."""
        result = clip_dem(_CLIP_BOX, dem_src, KKR_CODE, dem_clip_dir)
        with rasterio.open(dem_src) as src:
            src_pixels = src.width * src.height
        with rasterio.open(result) as dst:
            dst_pixels = dst.width * dst.height
        assert dst_pixels < src_pixels

    def test_clip_dtype_is_float32(self, dem_src: Path, dem_clip_dir: Path) -> None:
        """DEM pixels must stay float32 for pysheds compatibility."""
        result = clip_dem(_CLIP_BOX, dem_src, KKR_CODE, dem_clip_dir)
        with rasterio.open(result) as src:
            assert src.dtypes[0] == "float32"

    def test_valid_cells_have_finite_elevation(self, dem_src: Path, dem_clip_dir: Path) -> None:
        result = clip_dem(_CLIP_BOX, dem_src, KKR_CODE, dem_clip_dir)
        with rasterio.open(result) as src:
            arr = src.read(1)
            nodata = src.nodata
        valid = arr[arr != nodata]
        assert len(valid) > 0
        assert np.isfinite(valid).all()

    def test_idempotent_same_sha256(self, dem_src: Path, tmp_path: Path) -> None:
        """Calling clip_dem twice on the same inputs produces identical output."""
        from backend.utils.hashing import sha256_file
        d1 = tmp_path / "run1"
        d2 = tmp_path / "run2"
        d1.mkdir()
        d2.mkdir()
        p1 = clip_dem(_CLIP_BOX, dem_src, KKR_CODE, d1)
        p2 = clip_dem(_CLIP_BOX, dem_src, KKR_CODE, d2)
        assert sha256_file(p1) == sha256_file(p2)


# ---------------------------------------------------------------------------
# process_valgla tests
# ---------------------------------------------------------------------------


class TestProcessValgla:
    def test_returns_two_paths(self, clipped_dem: Path, tmp_path: Path) -> None:
        result = process_valgla(clipped_dem, KKR_CODE, tmp_path)
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_flowdir_path_exists(self, clipped_dem: Path, tmp_path: Path) -> None:
        flowdir_path, _ = process_valgla(clipped_dem, KKR_CODE, tmp_path)
        assert flowdir_path.exists()

    def test_flowacc_path_exists(self, clipped_dem: Path, tmp_path: Path) -> None:
        _, flowacc_path = process_valgla(clipped_dem, KKR_CODE, tmp_path)
        assert flowacc_path.exists()

    def test_flowdir_filename_uses_kkr_code(self, clipped_dem: Path, tmp_path: Path) -> None:
        flowdir_path, _ = process_valgla(clipped_dem, KKR_CODE, tmp_path)
        assert flowdir_path.stem == KKR_CODE

    def test_flowacc_filename_uses_kkr_code(self, clipped_dem: Path, tmp_path: Path) -> None:
        _, flowacc_path = process_valgla(clipped_dem, KKR_CODE, tmp_path)
        assert flowacc_path.stem == KKR_CODE

    def test_flowdir_in_flowdir_subdir(self, clipped_dem: Path, tmp_path: Path) -> None:
        flowdir_path, _ = process_valgla(clipped_dem, KKR_CODE, tmp_path)
        assert flowdir_path.parent.name == "flowdir"

    def test_flowacc_in_flowacc_subdir(self, clipped_dem: Path, tmp_path: Path) -> None:
        _, flowacc_path = process_valgla(clipped_dem, KKR_CODE, tmp_path)
        assert flowacc_path.parent.name == "flowacc"

    def test_flowdir_crs_is_lest97(self, clipped_dem: Path, tmp_path: Path) -> None:
        flowdir_path, _ = process_valgla(clipped_dem, KKR_CODE, tmp_path)
        with rasterio.open(flowdir_path) as src:
            assert src.crs.to_epsg() == 3301

    def test_flowacc_crs_is_lest97(self, clipped_dem: Path, tmp_path: Path) -> None:
        _, flowacc_path = process_valgla(clipped_dem, KKR_CODE, tmp_path)
        with rasterio.open(flowacc_path) as src:
            assert src.crs.to_epsg() == 3301

    def test_flowdir_interior_cells_valid_d8(self, clipped_dem: Path, tmp_path: Path) -> None:
        """All interior cells of the flow direction grid must be in DIRMAP."""
        flowdir_path, _ = process_valgla(clipped_dem, KKR_CODE, tmp_path)
        with rasterio.open(flowdir_path) as src:
            arr = src.read(1).astype(np.int64)
        interior = arr[1:-1, 1:-1]
        valid = set(DIRMAP)
        bad = set(interior.ravel().tolist()) - valid
        assert not bad, f"Invalid D8 values in interior: {bad}"

    def test_flowacc_values_nonnegative(self, clipped_dem: Path, tmp_path: Path) -> None:
        _, flowacc_path = process_valgla(clipped_dem, KKR_CODE, tmp_path)
        with rasterio.open(flowacc_path) as src:
            arr = src.read(1)
            nodata = src.nodata
        valid = arr[arr != nodata] if nodata is not None else arr
        assert float(valid.min()) >= 0.0

    def test_flowdir_transform_matches_clipped_dem(
        self, clipped_dem: Path, tmp_path: Path
    ) -> None:
        """Flow direction raster must be co-registered with the clipped DEM."""
        flowdir_path, _ = process_valgla(clipped_dem, KKR_CODE, tmp_path)
        with rasterio.open(clipped_dem) as src_dem:
            dem_transform = src_dem.transform
        with rasterio.open(flowdir_path) as src_fdir:
            fdir_transform = src_fdir.transform
        assert dem_transform == pytest.approx(fdir_transform, abs=1e-6)
