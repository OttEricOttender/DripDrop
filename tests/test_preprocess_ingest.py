"""Phase 2 ingest tests — sha256 verification, reprojection, download guard.

Tests the interface that scripts/preprocess.py exports for dataset ingestion:
  - sha256_file        (re-exported from backend.utils.hashing)
  - reproject_to_lest97
  - download_dataset

All spatial assertions use EPSG code comparisons (``crs.to_epsg() == 3301``)
rather than WKT string matching, to be robust across pyproj versions.

Fixture construction:
  Raster fixtures are created in-memory with rasterio and written to tmp_path.
  Vector fixtures are created with GeoPandas and written to tmp_path.
  No committed binary fixtures are needed for these tests.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pytest
import rasterio
from rasterio.crs import CRS
from rasterio.transform import from_origin
from shapely.geometry import box

from backend.utils.hashing import sha256_file
from scripts.preprocess import download_dataset, read_manifest, reproject_to_lest97, write_manifest

# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------

LEST97 = CRS.from_epsg(3301)
WGS84 = CRS.from_epsg(4326)


def _write_raster(path: Path, crs: CRS) -> None:
    """Write a tiny 10×10 float32 raster with a known CRS to *path*."""
    if crs.to_epsg() == 4326:
        # WGS84: origin over central Estonia, 0.001° pixel
        transform = from_origin(24.5, 59.5, 0.001, 0.001)
    else:
        # L-EST97: origin in central Estonia, 5 m pixel
        transform = from_origin(550_000, 6_490_000, 5.0, 5.0)
    data = np.arange(100, dtype=np.float32).reshape(10, 10) + 1.0
    with rasterio.open(
        path, "w",
        driver="GTiff", height=10, width=10, count=1,
        dtype="float32", crs=crs, transform=transform, nodata=np.float32(-9999),
    ) as dst:
        dst.write(data, 1)


def _write_vector(path: Path, crs: CRS) -> None:
    """Write a single-polygon GeoPackage with a known CRS to *path*."""
    if crs.to_epsg() == 4326:
        geom = box(24.0, 58.5, 26.0, 60.0)  # rough bounding box of Estonia
    else:
        geom = box(350_000, 6_370_000, 750_000, 6_640_000)  # Estonia in L-EST97
    gdf = gpd.GeoDataFrame({"id": [1], "name": ["test"]}, geometry=[geom], crs=crs)
    suffix = path.suffix.lower()
    driver = "GPKG" if suffix == ".gpkg" else "GeoJSON"
    gdf.to_file(path, driver=driver)


# ---------------------------------------------------------------------------
# 1. sha256_file (re-exported from backend.utils.hashing)
# ---------------------------------------------------------------------------


class TestSha256File:
    def test_known_content(self, tmp_path: Path) -> None:
        f = tmp_path / "known.bin"
        f.write_bytes(b"HydroCalc")
        expected = hashlib.sha256(b"HydroCalc").hexdigest()
        assert sha256_file(f) == expected

    def test_empty_file(self, tmp_path: Path) -> None:
        f = tmp_path / "empty.bin"
        f.write_bytes(b"")
        expected = hashlib.sha256(b"").hexdigest()
        assert sha256_file(f) == expected

    def test_returns_64_hex_chars(self, tmp_path: Path) -> None:
        f = tmp_path / "data.bin"
        f.write_bytes(b"\x00" * 1024)
        result = sha256_file(f)
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)

    def test_different_content_different_hash(self, tmp_path: Path) -> None:
        a = tmp_path / "a.bin"
        b = tmp_path / "b.bin"
        a.write_bytes(b"alpha")
        b.write_bytes(b"beta")
        assert sha256_file(a) != sha256_file(b)


# ---------------------------------------------------------------------------
# 2. reproject_to_lest97
# ---------------------------------------------------------------------------


class TestReprojectRaster:
    def test_lest97_raster_returned_unchanged(self, tmp_path: Path, fixtures_dir: Path) -> None:
        """A raster already in EPSG:3301 must be returned as-is (no copy made)."""
        src = fixtures_dir / "synthetic_dem_100x100.tif"
        out_dir = tmp_path / "reproj"
        out_dir.mkdir()
        result = reproject_to_lest97(src, out_dir)
        assert result == src

    def test_wgs84_raster_reprojected(self, tmp_path: Path) -> None:
        src = tmp_path / "dem_wgs84.tif"
        out_dir = tmp_path / "reproj"
        out_dir.mkdir()
        _write_raster(src, WGS84)
        result = reproject_to_lest97(src, out_dir)
        assert result != src
        with rasterio.open(result) as dst:
            assert dst.crs.to_epsg() == 3301

    def test_output_path_naming_raster(self, tmp_path: Path) -> None:
        src = tmp_path / "dem_wgs84.tif"
        out_dir = tmp_path / "reproj"
        out_dir.mkdir()
        _write_raster(src, WGS84)
        result = reproject_to_lest97(src, out_dir)
        assert result.name == "dem_wgs84_3301.tif"

    def test_output_in_output_dir(self, tmp_path: Path) -> None:
        src = tmp_path / "dem_wgs84.tif"
        out_dir = tmp_path / "reproj"
        out_dir.mkdir()
        _write_raster(src, WGS84)
        result = reproject_to_lest97(src, out_dir)
        assert result.parent == out_dir

    def test_reprojected_raster_is_readable(self, tmp_path: Path) -> None:
        src = tmp_path / "dem_wgs84.tif"
        out_dir = tmp_path / "reproj"
        out_dir.mkdir()
        _write_raster(src, WGS84)
        result = reproject_to_lest97(src, out_dir)
        with rasterio.open(result) as dst:
            arr = dst.read(1)
            nodata = dst.nodata
        # calculate_default_transform adjusts pixel count to preserve coverage;
        # assert the output is non-empty and all valid cells are finite.
        assert arr.ndim == 2
        assert arr.size > 0
        valid = arr[arr != nodata] if nodata is not None else arr
        assert np.isfinite(valid).all()


class TestReprojectVector:
    def test_lest97_vector_returned_unchanged(self, tmp_path: Path) -> None:
        src = tmp_path / "rivers_3301.gpkg"
        out_dir = tmp_path / "reproj"
        out_dir.mkdir()
        _write_vector(src, LEST97)
        result = reproject_to_lest97(src, out_dir)
        assert result == src

    def test_wgs84_vector_reprojected(self, tmp_path: Path) -> None:
        src = tmp_path / "rivers_wgs84.gpkg"
        out_dir = tmp_path / "reproj"
        out_dir.mkdir()
        _write_vector(src, WGS84)
        result = reproject_to_lest97(src, out_dir)
        gdf = gpd.read_file(result)
        assert gdf.crs.to_epsg() == 3301

    def test_output_path_naming_vector(self, tmp_path: Path) -> None:
        src = tmp_path / "rivers_wgs84.gpkg"
        out_dir = tmp_path / "reproj"
        out_dir.mkdir()
        _write_vector(src, WGS84)
        result = reproject_to_lest97(src, out_dir)
        assert result.name == "rivers_wgs84_3301.gpkg"

    def test_reprojected_vector_geometry_valid(self, tmp_path: Path) -> None:
        src = tmp_path / "rivers_wgs84.gpkg"
        out_dir = tmp_path / "reproj"
        out_dir.mkdir()
        _write_vector(src, WGS84)
        result = reproject_to_lest97(src, out_dir)
        gdf = gpd.read_file(result)
        assert gdf.geometry.is_valid.all()
        # Reprojected coordinates should be in the L-EST97 range for Estonia
        bounds = gdf.total_bounds  # (minx, miny, maxx, maxy)
        assert 200_000 < bounds[0] < 800_000, "x out of L-EST97 range for Estonia"
        assert 6_300_000 < bounds[1] < 6_700_000, "y out of L-EST97 range for Estonia"


# ---------------------------------------------------------------------------
# 3. download_dataset
# ---------------------------------------------------------------------------


def _make_raw_file(data_dir: Path, name: str, content: bytes = b"fake dataset") -> Path:
    """Place a fake raw file where download_dataset expects it."""
    from scripts.preprocess import DATASETS
    raw_dir = data_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / DATASETS[name]["filename"]
    path.write_bytes(content)
    return path


class TestDownloadDataset:
    def test_raises_file_not_found_when_missing(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError, match="vooluveekogud"):
            download_dataset("vooluveekogud", tmp_path)

    def test_unknown_name_raises_key_error(self, tmp_path: Path) -> None:
        with pytest.raises(KeyError, match="no_such_dataset"):
            download_dataset("no_such_dataset", tmp_path)

    def test_returns_path_when_file_exists_no_manifest(self, tmp_path: Path) -> None:
        _make_raw_file(tmp_path, "vooluveekogud")
        result = download_dataset("vooluveekogud", tmp_path)
        assert result.exists()
        assert result.name.endswith(".shp")

    def test_pins_sha256_on_first_run(self, tmp_path: Path) -> None:
        """First call records the sha256 in datasets.lock.json."""
        content = b"official estonian river data"
        _make_raw_file(tmp_path, "vooluveekogud", content)
        manifest_path = tmp_path / "datasets.lock.json"
        download_dataset("vooluveekogud", tmp_path, manifest_path=manifest_path)
        manifest = read_manifest(manifest_path)
        entries = {e["name"]: e for e in manifest["datasets"]}
        assert "vooluveekogud" in entries
        expected_hash = hashlib.sha256(content).hexdigest()
        assert entries["vooluveekogud"]["sha256"] == expected_hash

    def test_passes_silently_when_hash_matches(self, tmp_path: Path) -> None:
        content = b"official estonian river data"
        raw_path = _make_raw_file(tmp_path, "vooluveekogud", content)
        manifest_path = tmp_path / "datasets.lock.json"
        # First call pins hash
        download_dataset("vooluveekogud", tmp_path, manifest_path=manifest_path)
        # Second call with same file — must pass without raising
        result = download_dataset("vooluveekogud", tmp_path, manifest_path=manifest_path)
        assert result == raw_path

    def test_raises_on_sha256_mismatch(self, tmp_path: Path) -> None:
        """If the file on disk does not match the pinned hash, raise ValueError."""
        content_original = b"original bytes"
        content_tampered = b"tampered bytes"
        manifest_path = tmp_path / "datasets.lock.json"

        # Pin hash of original content
        _make_raw_file(tmp_path, "maaparandus", content_original)
        download_dataset("maaparandus", tmp_path, manifest_path=manifest_path)

        # Replace file with tampered content
        from scripts.preprocess import DATASETS
        raw_path = tmp_path / "raw" / DATASETS["maaparandus"]["filename"]
        raw_path.write_bytes(content_tampered)

        with pytest.raises(ValueError, match="SHA-256 mismatch"):
            download_dataset("maaparandus", tmp_path, manifest_path=manifest_path)

    def test_error_message_includes_source_url(self, tmp_path: Path) -> None:
        """FileNotFoundError must mention where to download the dataset from."""
        with pytest.raises(FileNotFoundError, match="register.keskkonnaportaal"):
            download_dataset("vooluveekogud", tmp_path)
