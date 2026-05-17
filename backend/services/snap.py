"""Nearest-stream snap service.

Finds the closest point on the river network to a user-supplied coordinate
by querying the preprocessed rivers.fgb FlatGeoBuf with a spatial bbox and
returning the nearest point on the nearest geometry.
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
from shapely.geometry import Point
from shapely.ops import nearest_points

from backend.models.schemas import RiverInfo


def snap_to_stream(
    x: float,
    y: float,
    rivers_fgb: Path,
    search_radius_m: float = 5000.0,
) -> tuple[tuple[float, float], RiverInfo, float]:
    """Snap (x, y) in EPSG:3301 to the nearest point on the river network.

    Parameters
    ----------
    x, y : float
        Easting and northing in L-EST97 (EPSG:3301).
    rivers_fgb : Path
        FlatGeoBuf produced by ``build_river_index()`` (contains ``kood``,
        ``nimi``, ``tyyp``, ``pikkus``, ``is_peajogi`` columns).
    search_radius_m : float
        Half-width of the bbox search window in metres.  If no river geometry
        falls within this radius, ValueError is raised.

    Returns
    -------
    snapped_xy : tuple[float, float]
        (x, y) of the snapped point in EPSG:3301.
    river_info : RiverInfo
    snap_distance_m : float
        Euclidean distance from the input point to the snapped point (metres).

    Raises
    ------
    ValueError
        If no river geometry is found within *search_radius_m*.
    FileNotFoundError
        If *rivers_fgb* does not exist.
    """
    if not rivers_fgb.exists():
        raise FileNotFoundError(f"rivers.fgb not found: {rivers_fgb}")

    bbox = (x - search_radius_m, y - search_radius_m,
            x + search_radius_m, y + search_radius_m)
    candidates = gpd.read_file(rivers_fgb, bbox=bbox)

    if candidates.empty:
        raise ValueError(
            f"No stream found within {search_radius_m:.0f} m of ({x:.1f}, {y:.1f}). "
            f"Check that the point is inside Estonia and the river index is populated."
        )

    input_point = Point(x, y)
    # Find the row whose geometry is closest to the input point
    distances = candidates.geometry.distance(input_point)
    nearest_idx = distances.idxmin()
    nearest_row = candidates.loc[nearest_idx]

    # Exact nearest point on the nearest geometry
    snapped_geom, _ = nearest_points(nearest_row.geometry, input_point)
    snapped_xy = (snapped_geom.x, snapped_geom.y)
    snap_distance_m = input_point.distance(snapped_geom)

    def _get(col: str):
        val = nearest_row.get(col)
        return None if val is None or (hasattr(val, '__class__') and str(val) == 'nan') else val

    river_info = RiverInfo(
        code=str(_get("kood") or nearest_row.name),
        name=str(_get("nimi") or ""),
        river_type=_get("tyyp"),
        length_m=_get("pikkus"),
        is_main=bool(_get("is_peajogi") or False),
    )

    return snapped_xy, river_info, snap_distance_m
