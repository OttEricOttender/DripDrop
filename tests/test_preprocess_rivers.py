"""Phase 2 river index tests — build_river_index.

Tests the FlatGeoBuf river index that the Phase 3 snap step will query.

Key behaviour under test:
  - Vooluveekogud (all watercourse segments) merged with Vooluveekogumid
    (main river bodies = peajõed) via attribute join on `kood`.
  - Each segment gets is_peajogi=True if its kood appears in vooluveekogumid,
    False otherwise.  This drives the thick/thin line rendering confirmed in
    the original design document (Google Doc).
  - Output is FlatGeoBuf (.fgb) with an embedded spatial index so Phase 3
    can issue fast bbox queries without loading the whole national dataset.
  - All geometry stays in EPSG:3301 (L-EST97).

Fixture design:
  Two river segments in EPSG:3301:
    river1: 500000–510000 E at 6 500 000 N  kood=VEE-001 (in vooluveekogumid)
    river2: 520000–530000 E at 6 500 000 N  kood=VEE-002 (not in vooluveekogumid)
  vooluveekogumid fixtures carry kood=VEE-001 to match river1 via attribute join.
  A two-segment variant exercises that duplicate body entries don't fan out rows.
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import LineString

from scripts.preprocess import build_river_index

# ---------------------------------------------------------------------------
# Fixture geometry constants (all in EPSG:3301)
# ---------------------------------------------------------------------------

_RIVER1 = LineString([(500_000, 6_500_000), (510_000, 6_500_000)])  # peajõgi
_RIVER2 = LineString([(520_000, 6_500_000), (530_000, 6_500_000)])  # lisajõgi

# Body segment A represents the same watercourse as RIVER1 (kood match)
_BODY_A = LineString([(500_000, 6_500_000), (510_000, 6_500_000)])
# Body segment B is an extra body entry for RIVER1 (same kood) — dedup test
_BODY_B = LineString([(504_000, 6_500_000), (510_000, 6_500_000)])


# ---------------------------------------------------------------------------
# Shared fixtures (written to tmp_path, not committed)
# ---------------------------------------------------------------------------


@pytest.fixture()
def vooluveekogud(tmp_path: Path) -> Path:
    """Two river segments (already renamed from kr_kood): one peajõgi, one lisajõgi.

    Uses the real kr_kood format (VEE<numeric>) so the is_peajogi join
    can strip the 'VEE' prefix and compare against body kood numerics.
    """
    gdf = gpd.GeoDataFrame(
        {
            "kood": ["VEE1000001", "VEE1000002"],
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
    """One body segment matching river1 via numeric kood (1000001_1 ↔ VEE1000001)."""
    gdf = gpd.GeoDataFrame(
        {"kood": ["1000001_1"], "nimi": ["Suur Jõgi vesikogu"]},
        geometry=[_BODY_A],
        crs="EPSG:3301",
    )
    path = tmp_path / "vooluveekogumid.gpkg"
    gdf.to_file(path, driver="GPKG")
    return path


@pytest.fixture()
def vooluveekogumid_two_polys(tmp_path: Path) -> Path:
    """Two body segments both with numeric kood 1000001 — exercises deduplication."""
    gdf = gpd.GeoDataFrame(
        {
            "kood": ["1000001_1", "1000001_2"],
            "nimi": ["Vesikogu A", "Vesikogu B"],
        },
        geometry=[_BODY_A, _BODY_B],
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

    def test_matching_kood_river_marked_peajogi(
        self, tmp_path: Path, vooluveekogud: Path, vooluveekogumid_single: Path
    ) -> None:
        result = build_river_index(vooluveekogud, vooluveekogumid_single, tmp_path)
        gdf = gpd.read_file(result)
        river1_row = gdf[gdf["kood"] == "VEE1000001"]
        assert len(river1_row) == 1
        assert bool(river1_row.iloc[0]["is_peajogi"]) is True

    def test_non_matching_kood_river_marked_false(
        self, tmp_path: Path, vooluveekogud: Path, vooluveekogumid_single: Path
    ) -> None:
        result = build_river_index(vooluveekogud, vooluveekogumid_single, tmp_path)
        gdf = gpd.read_file(result)
        river2_row = gdf[gdf["kood"] == "VEE1000002"]
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

    def test_no_duplicate_rows_when_river_matches_two_body_segments(
        self, tmp_path: Path, vooluveekogud: Path, vooluveekogumid_two_polys: Path
    ) -> None:
        """A river whose kood appears twice in vooluveekogumid must appear once."""
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
        assert subset.iloc[0]["kood"] == "VEE1000001"

    def test_empty_vooluveekogumid_all_false(
        self, tmp_path: Path, vooluveekogud: Path
    ) -> None:
        """When vooluveekogumid is empty, all rivers get is_peajogi=False."""
        empty = gpd.GeoDataFrame(
            {"kood": [], "nimi": []},
            geometry=gpd.GeoSeries([], crs="EPSG:3301"),
        )
        vvk_path = tmp_path / "vooluveekogumid_empty.gpkg"
        empty.to_file(vvk_path, driver="GPKG")
        result = build_river_index(vooluveekogud, vvk_path, tmp_path)
        gdf = gpd.read_file(result)
        assert gdf["is_peajogi"].sum() == 0
