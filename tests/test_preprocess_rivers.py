"""Phase 2 river index tests — build_river_index.

Tests the FlatGeoBuf river index that the Phase 3 snap step will query.

Key behaviour under test:
  - Vooluveekogud (all watercourse segments) merged with Vooluveekogumid
    (main river bodies = peajõed) via spatial join.
  - Each segment gets is_peajogi=True if it intersects a vooluveekogumid
    polygon, False otherwise.  This drives the thick/thin line rendering
    confirmed in the original design document (Google Doc).
  - Output is FlatGeoBuf (.fgb) with an embedded spatial index so Phase 3
    can issue fast bbox queries without loading the whole national dataset.
  - All geometry stays in EPSG:3301 (L-EST97).

Fixture design:
  Two river segments in EPSG:3301:
    river1: 500000–510000 E at 6 500 000 N  ← inside vooluveekogumid polygon
    river2: 520000–530000 E at 6 500 000 N  ← outside vooluveekogumid polygon
  One vooluveekogumid polygon covering river1 only.
  One extra vooluveekogumid polygon that overlaps river1 as well, to test
  that multiple-polygon matches do not create duplicate output rows.
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import LineString, Polygon

from scripts.preprocess import build_river_index

# ---------------------------------------------------------------------------
# Fixture geometry constants (all in EPSG:3301)
# ---------------------------------------------------------------------------

_RIVER1 = LineString([(500_000, 6_500_000), (510_000, 6_500_000)])  # peajõgi
_RIVER2 = LineString([(520_000, 6_500_000), (530_000, 6_500_000)])  # lisajõgi

# Polygon A covers river1 entirely
_POLY_A = Polygon([
    (498_000, 6_498_000), (512_000, 6_498_000),
    (512_000, 6_502_000), (498_000, 6_502_000),
])
# Polygon B also overlaps river1 (duplicate match test)
_POLY_B = Polygon([
    (504_000, 6_499_000), (511_000, 6_499_000),
    (511_000, 6_501_000), (504_000, 6_501_000),
])


# ---------------------------------------------------------------------------
# Shared fixtures (written to tmp_path, not committed)
# ---------------------------------------------------------------------------


@pytest.fixture()
def vooluveekogud(tmp_path: Path) -> Path:
    """Two river segments: one peajõgi (inside polygon), one lisajõgi."""
    gdf = gpd.GeoDataFrame(
        {
            "kood": ["VEE-001", "VEE-002"],
            "nimi": ["Suur Jõgi", "Väike Oja"],
            "tyyp": ["jõgi", "oja"],
            "pikkus": [10_000.0, 5_000.0],
        },
        geometry=[_RIVER1, _RIVER2],
        crs="EPSG:3301",
    )
    path = tmp_path / "vooluveekogud.gpkg"
    gdf.to_file(path, driver="GPKG")
    return path


@pytest.fixture()
def vooluveekogumid_single(tmp_path: Path) -> Path:
    """One polygon covering river1 only."""
    gdf = gpd.GeoDataFrame(
        {"kkr_kood": ["VEE-BODY-001"], "nimi": ["Suur Jõgi vesikogu"]},
        geometry=[_POLY_A],
        crs="EPSG:3301",
    )
    path = tmp_path / "vooluveekogumid.gpkg"
    gdf.to_file(path, driver="GPKG")
    return path


@pytest.fixture()
def vooluveekogumid_two_polys(tmp_path: Path) -> Path:
    """Two polygons both covering river1 — exercises deduplication."""
    gdf = gpd.GeoDataFrame(
        {
            "kkr_kood": ["VEE-BODY-001", "VEE-BODY-002"],
            "nimi": ["Vesikogu A", "Vesikogu B"],
        },
        geometry=[_POLY_A, _POLY_B],
        crs="EPSG:3301",
    )
    path = tmp_path / "vooluveekogumid_two.gpkg"
    gdf.to_file(path, driver="GPKG")
    return path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestBuildRiverIndex:
    def test_output_filename_is_fgb(
        self, tmp_path: Path, vooluveekogud: Path, vooluveekogumid_single: Path
    ) -> None:
        result = build_river_index(vooluveekogud, vooluveekogumid_single, tmp_path)
        assert result.suffix == ".fgb"

    def test_output_in_output_dir(
        self, tmp_path: Path, vooluveekogud: Path, vooluveekogumid_single: Path
    ) -> None:
        result = build_river_index(vooluveekogud, vooluveekogumid_single, tmp_path)
        assert result.parent == tmp_path

    def test_output_crs_is_lest97(
        self, tmp_path: Path, vooluveekogud: Path, vooluveekogumid_single: Path
    ) -> None:
        result = build_river_index(vooluveekogud, vooluveekogumid_single, tmp_path)
        gdf = gpd.read_file(result)
        assert gdf.crs.to_epsg() == 3301

    def test_is_peajogi_column_present(
        self, tmp_path: Path, vooluveekogud: Path, vooluveekogumid_single: Path
    ) -> None:
        result = build_river_index(vooluveekogud, vooluveekogumid_single, tmp_path)
        gdf = gpd.read_file(result)
        assert "is_peajogi" in gdf.columns

    def test_intersecting_river_marked_peajogi(
        self, tmp_path: Path, vooluveekogud: Path, vooluveekogumid_single: Path
    ) -> None:
        result = build_river_index(vooluveekogud, vooluveekogumid_single, tmp_path)
        gdf = gpd.read_file(result)
        river1_row = gdf[gdf["kood"] == "VEE-001"]
        assert len(river1_row) == 1
        assert bool(river1_row.iloc[0]["is_peajogi"]) is True

    def test_non_intersecting_river_marked_false(
        self, tmp_path: Path, vooluveekogud: Path, vooluveekogumid_single: Path
    ) -> None:
        result = build_river_index(vooluveekogud, vooluveekogumid_single, tmp_path)
        gdf = gpd.read_file(result)
        river2_row = gdf[gdf["kood"] == "VEE-002"]
        assert len(river2_row) == 1
        assert bool(river2_row.iloc[0]["is_peajogi"]) is False

    def test_preserves_vooluveekogud_attributes(
        self, tmp_path: Path, vooluveekogud: Path, vooluveekogumid_single: Path
    ) -> None:
        result = build_river_index(vooluveekogud, vooluveekogumid_single, tmp_path)
        gdf = gpd.read_file(result)
        for col in ("kood", "nimi", "tyyp", "pikkus"):
            assert col in gdf.columns, f"Column '{col}' missing from river index"

    def test_row_count_matches_vooluveekogud(
        self, tmp_path: Path, vooluveekogud: Path, vooluveekogumid_single: Path
    ) -> None:
        """Output must have one row per vooluveekogud segment — no fan-out."""
        original = gpd.read_file(vooluveekogud)
        result = build_river_index(vooluveekogud, vooluveekogumid_single, tmp_path)
        gdf = gpd.read_file(result)
        assert len(gdf) == len(original)

    def test_no_duplicate_rows_when_river_matches_two_polygons(
        self, tmp_path: Path, vooluveekogud: Path, vooluveekogumid_two_polys: Path
    ) -> None:
        """A river intersecting two vooluveekogumid polygons must appear once."""
        result = build_river_index(vooluveekogud, vooluveekogumid_two_polys, tmp_path)
        gdf = gpd.read_file(result)
        assert gdf["kood"].duplicated().sum() == 0

    def test_bbox_query_returns_river1_only(
        self, tmp_path: Path, vooluveekogud: Path, vooluveekogumid_single: Path
    ) -> None:
        """Spatial index (embedded in FlatGeoBuf) enables fast bbox queries."""
        result = build_river_index(vooluveekogud, vooluveekogumid_single, tmp_path)
        # bbox tightly around river1 (500k–510k), not reaching river2 (520k–530k)
        bbox = (498_000, 6_499_000, 512_000, 6_501_000)
        subset = gpd.read_file(result, bbox=bbox)
        assert len(subset) == 1
        assert subset.iloc[0]["kood"] == "VEE-001"

    def test_empty_vooluveekogumid_all_false(
        self, tmp_path: Path, vooluveekogud: Path
    ) -> None:
        """When vooluveekogumid is empty, all rivers get is_peajogi=False."""
        empty = gpd.GeoDataFrame(
            {"kkr_kood": [], "nimi": []},
            geometry=gpd.GeoSeries([], crs="EPSG:3301"),
        )
        vvk_path = tmp_path / "vooluveekogumid_empty.gpkg"
        empty.to_file(vvk_path, driver="GPKG")
        result = build_river_index(vooluveekogud, vvk_path, tmp_path)
        gdf = gpd.read_file(result)
        assert gdf["is_peajogi"].sum() == 0
