"""Generate tests/fixtures/synthetic_dem_100x100.tif — the canonical Phase 2 test fixture.

Run from the repo root:
    python tests/fixtures/make_synthetic_dem.py

The file is committed to the repo so tests never need to re-generate it.
Re-run this script only if the fixture design changes, then re-commit the .tif.

Design
------
100 × 100 cells, 5 m resolution, EPSG:3301, float32, nodata = -9999.

Elevation:
    elev[i, j] = max(0.0, 100.0 - 2.0*i + abs(j - 50) * 0.3)

This produces a V-shaped valley running south:
  - Row 0 (north edge): ridge ~130 m at col 0, ~115 m at col 50 (valley axis)
  - Row 99 (south edge): 0 m clipped
  - Valley axis (col 50) drains south toward outlet cell (99, 50)
  - Accumulation monotonically increases along col 50 from north to south

Synthetic pit:
    Cell (20, 50) is set 2 m below both its N and S neighbours so
    fill_pits has a detectable target.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import rasterio
from rasterio.crs import CRS
from rasterio.transform import from_origin

ROWS, COLS = 100, 100
CELL_SIZE = 5.0          # metres — matches Estonian DTM resolution
NODATA = np.float32(-9999.0)
# A valid Estonian coordinate in L-EST97 (central Estonia, farmland area)
ORIGIN_X = 550_000.0    # easting of top-left corner
ORIGIN_Y = 6_490_000.0  # northing of top-left corner
PIT_ROW, PIT_COL = 20, 50

OUT = Path(__file__).parent / "synthetic_dem_100x100.tif"


def make_dem() -> np.ndarray:
    i, j = np.mgrid[0:ROWS, 0:COLS]
    elev = (100.0 - 2.0 * i + np.abs(j - 50) * 0.3).astype(np.float32)
    elev = np.clip(elev, 0.0, None)
    # Inject one single-cell pit so fill_pits has a detectable target.
    # Surrounding neighbours along the valley axis are elev[19,50] and elev[21,50].
    # Set the pit 2 m below both.
    neighbour_min = min(float(elev[PIT_ROW - 1, PIT_COL]),
                        float(elev[PIT_ROW + 1, PIT_COL]))
    elev[PIT_ROW, PIT_COL] = np.float32(neighbour_min - 2.0)
    return elev


def write(path: Path, elev: np.ndarray) -> None:
    transform = from_origin(ORIGIN_X, ORIGIN_Y, CELL_SIZE, CELL_SIZE)
    with rasterio.open(
        path, "w",
        driver="GTiff",
        height=ROWS, width=COLS,
        count=1,
        dtype="float32",
        crs=CRS.from_epsg(3301),
        transform=transform,
        nodata=NODATA,
        compress="deflate",
    ) as dst:
        dst.write(elev, 1)
    print(f"Written {path} ({path.stat().st_size / 1024:.1f} KB)")


if __name__ == "__main__":
    elev = make_dem()
    write(OUT, elev)
    print(f"pit cell ({PIT_ROW},{PIT_COL}) elevation: {elev[PIT_ROW, PIT_COL]:.2f} m")
    print(f"outlet cell (99,50) elevation: {elev[99, 50]:.2f} m")
