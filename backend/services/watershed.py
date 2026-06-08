"""Catchment delineation service.

Two functions:
  find_valgla   — locate which official valgla polygon contains a point
  delineate_catchment — run pysheds D8 catchment from the flow grids
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import geopandas as gpd
import rasterio
import rasterio.features
from pysheds.grid import Grid
from shapely.geometry import Point, shape as shapely_shape

from backend.gis.constants import DIRMAP, FLOW_ACC_THRESHOLD


def find_valgla(
    x: float,
    y: float,
    valglad_fgb: Path,
) -> tuple[str, Any]:
    """Find the official valgla (watershed polygon) that contains (x, y).

    Parameters
    ----------
    x, y : float
        Easting and northing in EPSG:3301.
    valglad_fgb : Path
        FlatGeoBuf produced by ``scripts/preprocess.py`` Step 3c.  Must have
        a ``kkr_code`` column (normalised by the preprocessing step).

    Returns
    -------
    kkr_code : str
        The KKR identifier of the containing valgla.
    polygon : shapely Polygon
        The polygon geometry of the valgla.

    Raises
    ------
    ValueError
        If (x, y) is not contained in any valgla polygon.
    FileNotFoundError
        If *valglad_fgb* does not exist.
    """
    if not valglad_fgb.exists():
        raise FileNotFoundError(f"valglad.fgb not found: {valglad_fgb}")

    point = Point(x, y)
    # FlatGeoBuf bbox query — 1 m buffer ensures the point lands inside a cell
    bbox = (x - 1.0, y - 1.0, x + 1.0, y + 1.0)
    candidates = gpd.read_file(valglad_fgb, bbox=bbox)

    for _, row in candidates.iterrows():
        if row.geometry.contains(point):
            kkr_code = str(row.get("kkr_code", row.name))
            return kkr_code, row.geometry

    raise ValueError(
        f"Point ({x:.1f}, {y:.1f}) is not within any valgla polygon. "
        f"Ensure the point is inside Estonia and that preprocessing is complete."
    )


def delineate_catchment(
    x_snapped: float,
    y_snapped: float,
    kkr_code: str,
    preprocessed_dir: Path,
) -> tuple[Any, float, int]:
    """Delineate the catchment area upstream of a snapped pour point.

    Loads the per-valgla flow direction and flow accumulation rasters produced
    by ``process_valgla()`` and runs the pysheds D8 catchment algorithm.

    Parameters
    ----------
    x_snapped, y_snapped : float
        Pour-point coordinates in EPSG:3301.  Should be on or very close to a
        stream cell (i.e. the output of ``snap_to_stream``).
    kkr_code : str
        KKR identifier used to locate the correct raster tiles.
    preprocessed_dir : Path
        Root of the preprocessed data directory (contains ``flowdir/`` and
        ``flowacc/`` subdirectories).

    Returns
    -------
    catchment_polygon : shapely Polygon
        The delineated catchment boundary in EPSG:3301.
    area_km2 : float
        Catchment area in km².
    dem_resolution_m : int
        Pixel size of the flow grids in metres.  Normally 5; >5 means the basin
        was auto-downsampled during preprocessing (e.g. Narva at 25 m).

    Raises
    ------
    FileNotFoundError
        If the flow direction or accumulation rasters for *kkr_code* do not exist.
    ValueError
        If catchment delineation produces no valid polygon.
    """
    flowdir_path = preprocessed_dir / "flowdir" / f"{kkr_code}.tif"
    flowacc_path = preprocessed_dir / "flowacc" / f"{kkr_code}.tif"

    if not flowdir_path.exists():
        raise FileNotFoundError(
            f"Flow direction raster not found: {flowdir_path}. "
            f"Run scripts/preprocess.py to generate the per-valgla flow grids."
        )
    if not flowacc_path.exists():
        raise FileNotFoundError(
            f"Flow accumulation raster not found: {flowacc_path}. "
            f"Run scripts/preprocess.py to generate the per-valgla flow grids."
        )

    with rasterio.open(flowdir_path) as _meta:
        dem_resolution_m = int(round(abs(_meta.transform.a)))

    grid = Grid.from_raster(str(flowdir_path))
    fdir = grid.read_raster(str(flowdir_path))
    flowacc = grid.read_raster(str(flowacc_path))

    # Snap pour point to nearest stream cell (accumulation ≥ threshold)
    stream_mask = flowacc >= FLOW_ACC_THRESHOLD
    # snap_to_mask takes xy as shape (N, 2); returns shape (N, 2)
    xy = np.array([[x_snapped, y_snapped]])
    xy_snapped = grid.snap_to_mask(stream_mask, xy)
    x_pour, y_pour = float(xy_snapped[0, 0]), float(xy_snapped[0, 1])

    # D8 catchment delineation
    catch = grid.catchment(x_pour, y_pour, fdir, dirmap=DIRMAP)

    # Vectorize the boolean catchment mask to a shapely Polygon
    catch_arr = np.asarray(catch).astype(np.uint8)
    geoms = [
        shapely_shape(geom)
        for geom, val in rasterio.features.shapes(catch_arr, transform=catch.affine)
        if int(val) == 1
    ]
    if not geoms:
        raise ValueError(
            f"Catchment delineation produced no polygon for KKR code '{kkr_code}'. "
            f"The pour point ({x_snapped:.1f}, {y_snapped:.1f}) may be outside "
            f"the valgla's flow grid extent."
        )

    # Take the largest polygon (occasional isolated noise pixels can appear)
    catchment_polygon = max(geoms, key=lambda g: g.area)
    area_km2 = catchment_polygon.area / 1e6

    return catchment_polygon, area_km2, dem_resolution_m
