"""Nearest-stream snap service.

Finds the closest point on the river network to a user-supplied coordinate
by querying the preprocessed rivers.fgb FlatGeoBuf with a spatial bbox and
returning the nearest point on the nearest geometry.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import geopandas as gpd
from shapely.geometry import Point
from shapely.ops import nearest_points

from backend.models.schemas import RiverInfo


@lru_cache(maxsize=4)
def _total_lengths_m(rivers_fgb: Path) -> dict[str, float]:
    """Return a {kood: total_length_m} dict for every river in rivers_fgb.

    Computed from geometry (EPSG:3301 metres), not from pikk_arv, because
    pikk_arv in the Keskkonnaportaali source has been observed in km for some
    rivers (e.g. Pärnu jõgi ≈ 144.8 instead of 144 800 m).  Loaded once and
    cached per unique file path; restart the server after rebuilding rivers.fgb.
    """
    gdf = gpd.read_file(rivers_fgb)
    return (
        gdf.groupby("kood")["geometry"]
        .apply(lambda segs: float(segs.length.sum()))
        .to_dict()
    )


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

    # Always use geometry-derived total length (metres) — ignores pikk_arv which
    # has unreliable units in the source dataset (km for some rivers, 0 for others).
    river_code = str(_get("kood") or nearest_row.name)
    lengths = _total_lengths_m(rivers_fgb)
    total_length_m = lengths.get(river_code) or nearest_row.geometry.length

    river_info = RiverInfo(
        code=river_code,
        name=str(_get("nimi") or ""),
        river_type=_get("tyyp"),
        length_m=total_length_m,
        is_main=bool(_get("is_peajogi") or False),
    )

    return snapped_xy, river_info, snap_distance_m
