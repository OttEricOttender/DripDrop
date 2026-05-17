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
from scripts.preprocess import (
    _is_lest97,
    download_dataset,
    merge_kolvikud,
    read_manifest,
    reproject_to_lest97,
    write_manifest,
)

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


# ---------------------------------------------------------------------------
# 4. manifest round-trip (write_manifest / read_manifest)
# ---------------------------------------------------------------------------


class TestManifestRoundTrip:
    def test_write_then_read_preserves_content(self, tmp_path: Path) -> None:
        manifest = {
            "schema_version": 1,
            "generated_at": "2026-01-01T00:00:00+00:00",
            "datasets": [
                {
                    "name": "vooluveekogud",
                    "source_url": "https://register.keskkonnaportaal.ee/register",
                    "sha256": "abc123",
                    "retrieved_at": "2026-01-01T00:00:00+00:00",
                    "crs": "EPSG:3301",
                    "resolution_m": None,
                    "output_path": "/data/raw/vooluveekogud.shp",
                }
            ],
        }
        path = tmp_path / "datasets.lock.json"
        write_manifest(manifest, path)
        assert read_manifest(path) == manifest

    def test_write_creates_valid_json(self, tmp_path: Path) -> None:
        manifest = {"schema_version": 1, "datasets": []}
        path = tmp_path / "datasets.lock.json"
        write_manifest(manifest, path)
        parsed = json.loads(path.read_text(encoding="utf-8"))
        assert parsed["schema_version"] == 1

    def test_read_raises_file_not_found(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            read_manifest(tmp_path / "nonexistent.json")

    def test_utf8_estonian_chars_survive_roundtrip(self, tmp_path: Path) -> None:
        """Estonian field names must survive write → read unchanged."""
        manifest = {"schema_version": 1, "notes": ["maaparandussüsteemide mõjualad"]}
        path = tmp_path / "datasets.lock.json"
        write_manifest(manifest, path)
        assert read_manifest(path)["notes"][0] == "maaparandussüsteemide mõjualad"

    def test_file_is_indented_json(self, tmp_path: Path) -> None:
        """Output must be human-readable indented JSON (not one-liner)."""
        path = tmp_path / "datasets.lock.json"
        write_manifest({"schema_version": 1, "datasets": []}, path)
        raw = path.read_text(encoding="utf-8")
        assert "\n" in raw


# ---------------------------------------------------------------------------
# 5. _is_lest97 — compound CRS detection
# ---------------------------------------------------------------------------


class TestIsLest97:
    def test_simple_epsg3301_returns_true(self) -> None:
        assert _is_lest97(CRS.from_epsg(3301)) is True

    def test_wgs84_returns_false(self) -> None:
        assert _is_lest97(CRS.from_epsg(4326)) is False

    def test_none_returns_false(self) -> None:
        assert _is_lest97(None) is False

    def test_compound_lest97_returns_true(self) -> None:
        """Compound CRS with EPSG:3301 horizontal must return True.

        ETAK shapefiles embed a compound CRS (EPSG:3301 + EVRF2007 height).
        pyproj can construct one via the "EPSG:3301+5705" notation.
        """
        from pyproj import CRS as ProjCRS
        compound = ProjCRS.from_user_input("EPSG:3301+5705")
        assert _is_lest97(compound) is True

    def test_compound_wgs84_returns_false(self) -> None:
        """Compound CRS with WGS84 horizontal must return False."""
        from pyproj import CRS as ProjCRS
        compound = ProjCRS.from_user_input("EPSG:4326+5705")
        assert _is_lest97(compound) is False


# ---------------------------------------------------------------------------
# 6. merge_kolvikud
# ---------------------------------------------------------------------------


def _write_kolvikud_shp(path: Path, kood: int, kood_t: str, n: int = 2) -> None:
    """Write a synthetic ETAK kolvikud shapefile with *n* polygon features."""
    geoms = [
        box(500_000 + i * 1_000, 6_490_000, 501_000 + i * 1_000, 6_491_000)
        for i in range(n)
    ]
    gdf = gpd.GeoDataFrame(
        {"kood": [kood] * n, "kood_t": [kood_t] * n},
        geometry=geoms,
        crs="EPSG:3301",
    )
    gdf.to_file(path, driver="ESRI Shapefile")


@pytest.fixture()
def kolvikud_dir(tmp_path: Path) -> Path:
    """Synthetic kolvikud folder with two category shapefiles (305 and 306)."""
    k_dir = tmp_path / "ETAK_Eesti_SHP_kolvikud"
    k_dir.mkdir()
    _write_kolvikud_shp(k_dir / "E_305_puittaimestik_a.shp", 305, "puittaimestik", n=2)
    _write_kolvikud_shp(k_dir / "E_306_margala_a.shp", 306, "märgala", n=1)
    return k_dir


class TestMergeKolvikud:
    def test_output_is_fgb(self, kolvikud_dir: Path, tmp_path: Path) -> None:
        result = merge_kolvikud(kolvikud_dir, tmp_path / "out")
        assert result.suffix == ".fgb"

    def test_output_named_kolvikud(self, kolvikud_dir: Path, tmp_path: Path) -> None:
        result = merge_kolvikud(kolvikud_dir, tmp_path / "out")
        assert result.stem == "kolvikud"

    def test_output_exists(self, kolvikud_dir: Path, tmp_path: Path) -> None:
        result = merge_kolvikud(kolvikud_dir, tmp_path / "out")
        assert result.exists()

    def test_all_features_present(self, kolvikud_dir: Path, tmp_path: Path) -> None:
        """2 features from E_305 + 1 from E_306 = 3 total."""
        result = merge_kolvikud(kolvikud_dir, tmp_path / "out")
        gdf = gpd.read_file(result)
        assert len(gdf) == 3

    def test_kood_column_present(self, kolvikud_dir: Path, tmp_path: Path) -> None:
        result = merge_kolvikud(kolvikud_dir, tmp_path / "out")
        gdf = gpd.read_file(result)
        assert "kood" in gdf.columns

    def test_both_codes_in_output(self, kolvikud_dir: Path, tmp_path: Path) -> None:
        result = merge_kolvikud(kolvikud_dir, tmp_path / "out")
        gdf = gpd.read_file(result)
        codes = set(gdf["kood"].tolist())
        assert 305 in codes and 306 in codes

    def test_crs_is_lest97(self, kolvikud_dir: Path, tmp_path: Path) -> None:
        result = merge_kolvikud(kolvikud_dir, tmp_path / "out")
        gdf = gpd.read_file(result)
        assert gdf.crs.to_epsg() == 3301

    def test_creates_output_dir_if_missing(self, kolvikud_dir: Path, tmp_path: Path) -> None:
        new_dir = tmp_path / "nested" / "output"
        result = merge_kolvikud(kolvikud_dir, new_dir)
        assert result.exists()

    def test_raises_if_no_shapefiles_found(self, tmp_path: Path) -> None:
        empty_dir = tmp_path / "empty_kolvikud"
        empty_dir.mkdir()
        with pytest.raises(FileNotFoundError, match="E_3"):
            merge_kolvikud(empty_dir, tmp_path / "out")
