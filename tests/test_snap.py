"""Tests for backend.services.snap — nearest-stream snap.

Fixture design
--------------
Two river line segments written to a temporary FlatGeoBuf:
  river_a  kood="VEE-001" nimi="Suur Jõgi"  is_peajogi=True
           LineString from (500_000, 6_500_000) to (510_000, 6_500_000)
  river_b  kood="VEE-002" nimi="Väike Oja"  is_peajogi=False
           LineString from (520_000, 6_500_000) to (530_000, 6_500_000)

Test points:
  • (505_000, 6_500_100) — 100 m north of river_a midpoint → snaps to river_a
  • (525_000, 6_500_500) — 500 m north of river_b midpoint → snaps to river_b
  • (505_000, 6_510_000) — 10 km north of any river → outside search radius
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import LineString

from backend.services.snap import snap_to_stream


@pytest.fixture(scope="module")
def rivers_fgb(tmp_path_factory: pytest.TempPathFactory) -> Path:
    d = tmp_path_factory.mktemp("rivers")
    gdf = gpd.GeoDataFrame(
        {
            "kood": ["VEE-001", "VEE-002"],
            "nimi": ["Suur Jõgi", "Väike Oja"],
            "tyyp": ["jõgi", "oja"],
            "pikkus": [10_000.0, 10_000.0],
            "is_peajogi": [True, False],
        },
        geometry=[
            LineString([(500_000, 6_500_000), (510_000, 6_500_000)]),
            LineString([(520_000, 6_500_000), (530_000, 6_500_000)]),
        ],
        crs="EPSG:3301",
    )
    path = d / "rivers.fgb"
    gdf.to_file(path, driver="FlatGeobuf")
    return path


class TestSnapToStream:
    def test_snaps_to_correct_river(self, rivers_fgb: Path) -> None:
        """Point north of river_a should snap to river_a, not river_b."""
        (x_snap, y_snap), info, dist = snap_to_stream(505_000, 6_500_100, rivers_fgb)
        assert info.code == "VEE-001"

    def test_snaps_to_nearer_river(self, rivers_fgb: Path) -> None:
        """Point north of river_b should snap to river_b."""
        (x_snap, y_snap), info, dist = snap_to_stream(525_000, 6_500_500, rivers_fgb)
        assert info.code == "VEE-002"

    def test_snap_distance_is_nonnegative(self, rivers_fgb: Path) -> None:
        _, _, dist = snap_to_stream(505_000, 6_500_100, rivers_fgb)
        assert dist >= 0.0

    def test_snap_distance_is_approx_100m(self, rivers_fgb: Path) -> None:
        """Point is exactly 100 m north of river_a — snap distance ≈ 100 m."""
        _, _, dist = snap_to_stream(505_000, 6_500_100, rivers_fgb)
        assert dist == pytest.approx(100.0, abs=1.0)

    def test_snapped_point_on_river_line(self, rivers_fgb: Path) -> None:
        """Snapped y-coordinate should equal the river's y (both lie at y=6_500_000)."""
        (x_snap, y_snap), _, _ = snap_to_stream(505_000, 6_500_100, rivers_fgb)
        assert y_snap == pytest.approx(6_500_000.0, abs=1.0)

    def test_river_info_name(self, rivers_fgb: Path) -> None:
        _, info, _ = snap_to_stream(505_000, 6_500_100, rivers_fgb)
        assert info.name == "Suur Jõgi"

    def test_river_info_is_main(self, rivers_fgb: Path) -> None:
        _, info, _ = snap_to_stream(505_000, 6_500_100, rivers_fgb)
        assert info.is_main is True

    def test_non_main_river(self, rivers_fgb: Path) -> None:
        _, info, _ = snap_to_stream(525_000, 6_500_500, rivers_fgb)
        assert info.is_main is False

    def test_raises_value_error_when_nothing_in_radius(self, rivers_fgb: Path) -> None:
        """Point far from any river raises ValueError, not a silent wrong result."""
        with pytest.raises(ValueError, match="No stream"):
            snap_to_stream(505_000, 6_510_000, rivers_fgb, search_radius_m=100.0)

    def test_raises_file_not_found_for_missing_fgb(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            snap_to_stream(505_000, 6_500_100, tmp_path / "nonexistent.fgb")

    def test_default_search_radius_finds_river(self, rivers_fgb: Path) -> None:
        """Default 5 000 m radius should find river_a from 100 m away."""
        _, info, _ = snap_to_stream(505_000, 6_500_100, rivers_fgb)
        assert info.code == "VEE-001"
