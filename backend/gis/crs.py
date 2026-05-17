"""Single source of truth for coordinate transforms.

The rule across the codebase: everything internal is EPSG:3301. Anything
crossing the HTTP boundary in EPSG:4326 goes through one of the two
``to_lest97`` / ``to_wgs84`` helpers in this module. No other file
constructs a ``pyproj.Transformer``.

This deliberate funnel prevents the class of bug where one module
silently uses a different proj string from another and area calculations
drift by a few percent.
"""

from __future__ import annotations

from functools import lru_cache

from pyproj import Transformer

# Canonical CRS identifiers — referenced throughout the codebase.
LEST97 = "EPSG:3301"
WGS84 = "EPSG:4326"


@lru_cache(maxsize=2)
def _transformer(src: str, dst: str) -> Transformer:
    """Cached transformer (pyproj recommends reusing Transformer instances)."""
    return Transformer.from_crs(src, dst, always_xy=True)


def to_lest97(lon: float, lat: float) -> tuple[float, float]:
    """WGS84 (lon, lat) → L-EST97 (x, y) in metres."""
    x, y = _transformer(WGS84, LEST97).transform(lon, lat)
    return x, y


def to_wgs84(x: float, y: float) -> tuple[float, float]:
    """L-EST97 (x, y) → WGS84 (lon, lat)."""
    lon, lat = _transformer(LEST97, WGS84).transform(x, y)
    return lon, lat


def to_wgs84_geojson(geometry: object) -> dict:
    """Convert a Shapely geometry in L-EST97 to a GeoJSON dict in WGS84."""
    import shapely.ops
    from shapely.geometry import mapping
    t = _transformer(LEST97, WGS84)
    geom_wgs84 = shapely.ops.transform(t.transform, geometry)
    return dict(mapping(geom_wgs84))
