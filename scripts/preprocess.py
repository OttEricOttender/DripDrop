"""Offline GIS preprocessing pipeline for HydroCalc (Phase 2).

Run once per host to produce the per-valgla DEM clips and flow grids that the
FastAPI runtime reads at query time (Phase 3).  The script is idempotent: each
step skips if its output already exists and its sha256 matches the manifest.
Pass ``--force`` to rebuild everything.

Usage
-----
    python scripts/preprocess.py [--force] [--data-dir PATH]

Pipeline steps
--------------
1. download_dataset       — fetch + verify sha256 against datasets.lock.json
2. reproject_to_lest97    — convert every input to EPSG:3301
3. build_river_index      — FlatGeoBuf + R-tree for fast bbox queries
4. clip_dem               — per-valgla DEM clip (rasterio masked window)
5. process_valgla         — condition + flowdir + flowacc (pysheds) per clip
6. vectorize_streams      — extract stream network from flowacc
7. emit_manifest          — write datasets.lock.json with sha256 of every output

Steps 1–3 operate once on the national datasets.
Steps 4–6 loop over every official valgla polygon (keyed by KKR code).
Step 7 writes the manifest after all loops complete.

Inviolable constraints (from CLAUDE.md)
----------------------------------------
* ALL spatial work is in EPSG:3301 (L-EST97).  No other CRS is used inside
  this script.  Inputs that arrive in a different CRS are reprojected
  immediately in reproject_to_lest97() and the original files are left
  untouched.
* Only official Estonian datasets are used (Maa-amet geoportaal,
  Keskkonnaportaali register).  See DATASETS below for source URLs.
* numpy.random is never seeded globally.  If pysheds needs a seed, set it
  locally inside the calling function and document why.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
import rasterio.features
import rasterio.warp
from pysheds.grid import Grid
from pysheds.sview import Raster
from rasterio.crs import CRS
from rasterio.enums import Resampling
from rasterio.transform import from_origin

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# D8 flow direction encoding used throughout the codebase (must match
# delineate.py and the pysheds default).  Clockwise from E:
# E=1, SE=2, S=4, SW=8, W=16, NW=32, N=64, NE=128
DIRMAP: tuple[int, ...] = (64, 128, 1, 2, 4, 8, 16, 32)

# EPSG:3301 (L-EST97) — the only CRS used internally (inviolable rule #2).
LEST97 = CRS.from_epsg(3301)

# Nodata sentinel for all DEM rasters (must be float32 for pysheds 0.4).
DEM_NODATA = np.float32(-9999.0)

# Official Estonian dataset registry.  Source URLs are confirmed from the
# original project brief (docs/decisions.md) and the design document at
# https://docs.google.com/document/d/1B9gXAdswT313_XtYV5t-ObUsj-CzwUuRyM8Yqh88_5g
DATASETS: dict[str, dict[str, str]] = {
    "vooluveekogud": {
        # All watercourses (rivers, streams) — used for nearest-watercourse snap
        "source": "https://register.keskkonnaportaal.ee/register",
        "portal_path": "Vesi > Veekogud > Vooluveekogud",
        "filename": "vooluveekogud.shp",
    },
    "vooluveekogumid": {
        # Watercourse bodies = peajõed (main rivers) — thicker line weight in UI
        # Distinct from vooluveekogud: these are the named main-river bodies,
        # not every individual stream segment.
        "source": "https://register.keskkonnaportaal.ee/register",
        "portal_path": "Vesi > Veekogumid > Vooluveekogumid",
        "filename": "vooluveekogumid.shp",
    },
    "seisuveekogud": {
        # Lakes and sea areas — displayed on the base map
        "source": "https://register.keskkonnaportaal.ee/register",
        "portal_path": "Vesi > Veekogud > Järved, Merealad",
        "filename": "seisuveekogud.shp",
    },
    "valglad": {
        # Official watershed polygons — clip extents for per-valgla DEM tiles
        "source": "https://register.keskkonnaportaal.ee/register",
        "portal_path": "Vesi > Vesikonnad ja valgalad > Vooluveekogude valglad",
        "filename": "valglad.shp",
    },
    "dtm_5m": {
        # National 5 m DTM — the single authoritative elevation source
        "source": "https://geoportaal.maaamet.ee/est/Ruumiandmed/Korgusandmed/Laadi-korgusandmed-alla-p614.html",
        "portal_path": "Maapinna kõrgusmudelid > Kogu Eesti DTM eraldusvõimega 5m (GeoTIFF)",
        "filename": "DTM_5m_eesti.tif",
    },
    "kolvikud": {
        # ETAK land-use parcels — provides A_ms, A_r, A_km, B, C for Hommik
        "source": "https://geoportaal.maaamet.ee/est/Ruumiandmed/Eesti-topograafia-andmekogu/Laadi-ETAK-andmed-alla-p609.html",
        "portal_path": "Kõlvikud (SHP)",
        "filename": "kolvikud.shp",
    },
    "maaparandus": {
        # Land-improvement system influence zones
        "source": "https://geoportaal.maaamet.ee/est/Ruumiandmed/Kitsenduste-andmed/Kitsenduste-andmete-allalaadimine-p624.html",
        "portal_path": "Maaparandussüsteemide mõjualad (SHP)",
        "filename": "maaparandus.shp",
    },
    "q95": {
        # Joon 4.1 cartogram — q_95% annual minimum flow modulus
        # Provided by user as TopoToR_JOON41.tif
        "source": "user-provided",
        "portal_path": "keskmine_aasta_minimaalne_äravool/TopoToR_JOON41.tif",
        "filename": "q95.tif",
    },
}


# ---------------------------------------------------------------------------
# Step 5 helpers — DEM conditioning and flow computation
# (pure functions; tested by tests/test_preprocess_gis.py)
# ---------------------------------------------------------------------------


def load_dem(dem_path: Path) -> tuple[Grid, Raster]:
    """Load a DEM GeoTIFF into a pysheds Grid and Raster.

    The file must be in EPSG:3301 with a float32 nodata value (DEM_NODATA).
    If the raster contains a different nodata value, pysheds may silently use
    the wrong cells — ensure reproject_to_lest97() has been run first.

    Returns
    -------
    grid : pysheds.grid.Grid
        Spatial grid object used for all subsequent pysheds operations.
    dem : pysheds.sview.Raster
        Elevation raster backed by the grid's coordinate system.
    """
    grid = Grid.from_raster(str(dem_path))
    dem = grid.read_raster(str(dem_path))
    return grid, dem


def condition_dem(grid: Grid, dem: Raster) -> Raster:
    """Condition a DEM for flow routing: fill pits → fill depressions → resolve flats.

    Applies the same three-step conditioning chain as the legacy
    scripts/delineate.py, in the same order, so runtime behaviour is
    identical to what the original team validated.

    Parameters
    ----------
    grid : Grid
        The pysheds grid the dem belongs to.
    dem : Raster
        Raw elevation raster (may contain pits, depressions, and flats).

    Returns
    -------
    Raster
        Fully conditioned DEM ready for flowdir().
    """
    pit_filled = grid.fill_pits(dem)
    flooded = grid.fill_depressions(pit_filled)
    inflated = grid.resolve_flats(flooded)
    return inflated


def compute_flowdir(grid: Grid, conditioned: Raster) -> Raster:
    """Compute D8 flow direction from a conditioned DEM.

    Uses the module-level DIRMAP (64,128,1,2,4,8,16,32) which matches
    delineate.py.  Every interior cell of a fully conditioned, flat-free DEM
    should have a value drawn from DIRMAP; edge cells may be 0 (off-grid).

    Parameters
    ----------
    grid : Grid
    conditioned : Raster
        Output of condition_dem().

    Returns
    -------
    Raster
        D8 flow direction raster.
    """
    return grid.flowdir(conditioned, dirmap=DIRMAP)


def compute_flowacc(grid: Grid, fdir: Raster) -> Raster:
    """Compute D8 flow accumulation from a flow direction raster.

    Each cell's value is the number of upstream cells (including itself) that
    drain into it.  The outlet cell of a fully connected catchment will have
    the highest value.

    Parameters
    ----------
    grid : Grid
    fdir : Raster
        Output of compute_flowdir().

    Returns
    -------
    Raster
        Flow accumulation raster (cell count, dtype float64).
    """
    return grid.accumulation(fdir, dirmap=DIRMAP)


# ---------------------------------------------------------------------------
# Step 7 — Manifest I/O
# (pure I/O; tested by tests/test_preprocess_gis.py)
# ---------------------------------------------------------------------------


def write_manifest(manifest: dict[str, Any], path: Path) -> None:
    """Write the dataset manifest to *path* as indented JSON (UTF-8).

    The manifest schema follows datasets.lock.json (schema_version=1).
    Callers must supply the fully assembled dict; this function performs
    no validation beyond JSON serialisability.

    Parameters
    ----------
    manifest : dict
        Complete manifest including ``schema_version``, ``datasets``, etc.
    path : Path
        Destination file.  Parent directories must already exist.
    """
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")


def read_manifest(path: Path) -> dict[str, Any]:
    """Read and return the dataset manifest from *path*.

    Parameters
    ----------
    path : Path
        Path to a datasets.lock.json file written by write_manifest().

    Returns
    -------
    dict
        Parsed manifest.

    Raises
    ------
    FileNotFoundError
        If *path* does not exist.
    json.JSONDecodeError
        If the file is not valid JSON.
    """
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Step 4+5 combined — per-valgla clip + conditioning + flow grids
# ---------------------------------------------------------------------------


def clip_dem(
    valgla_geom: Any,
    dem_path: Path,
    kkr_code: str,
    output_dir: Path,
) -> Path:
    """Clip the national DTM to a single valgla polygon and write a COG.

    Uses rasterio masked windows so only the bounding box of the valgla
    polygon is read into memory — the full 50 GB DTM is never loaded whole.
    The output is a Cloud-Optimised GeoTIFF (COG) compatible with pysheds.

    Parameters
    ----------
    valgla_geom : shapely geometry
        The valgla polygon in EPSG:3301.
    dem_path : Path
        Path to the national DTM (DTM_5m_eesti.tif) in EPSG:3301.
    kkr_code : str
        KKR identifier used to name the output file (e.g. ``"VEE_1234"``).
    output_dir : Path
        Directory for clipped DEMs (``data/preprocessed/dem/``).

    Returns
    -------
    Path
        Path to the written ``<kkr_code>.tif``.
    """
    raise NotImplementedError("Phase 2 Step 4 — implemented after Step 3 lands")


def process_valgla(
    dem_clip_path: Path,
    kkr_code: str,
    output_dir: Path,
) -> tuple[Path, Path]:
    """Condition the clipped DEM and write flow-dir + flow-acc rasters.

    This is the per-valgla entry point for Step 5.  It calls the pure
    functions condition_dem / compute_flowdir / compute_flowacc and writes
    the results to disk as GeoTIFFs in EPSG:3301.

    Parameters
    ----------
    dem_clip_path : Path
        Output of clip_dem() for this valgla.
    kkr_code : str
        KKR identifier used to name the output files.
    output_dir : Path
        Base directory; flowdir and flowacc subdirs are created as needed.

    Returns
    -------
    flowdir_path : Path
    flowacc_path : Path
    """
    raise NotImplementedError("Phase 2 Step 5 disk-write — implemented after clip_dem lands")


# ---------------------------------------------------------------------------
# Step 6 — stream vectorisation
# ---------------------------------------------------------------------------


def vectorize_streams(
    flowacc_path: Path,
    kkr_code: str,
    threshold: int,
    output_dir: Path,
) -> Path:
    """Extract the stream network from a flow-accumulation raster.

    Cells with accumulation >= *threshold* are treated as stream cells.
    The resulting polylines are written as a FlatGeoBuf file for fast
    bbox queries at runtime (Phase 3 snap step).

    Parameters
    ----------
    flowacc_path : Path
        Output of process_valgla().
    kkr_code : str
    threshold : int
        Minimum upstream cell count to qualify as a stream cell.
        Typical value: 500 (= 500 × 25 m² = 12 500 m² ~ 0.01 km²).
    output_dir : Path

    Returns
    -------
    Path
        Path to the written ``<kkr_code>_streams.fgb``.
    """
    raise NotImplementedError("Phase 2 Step 6 — implemented after process_valgla lands")


# ---------------------------------------------------------------------------
# Step 3 — river index
# ---------------------------------------------------------------------------


def build_river_index(
    vooluveekogud_path: Path,
    vooluveekogumid_path: Path,
    output_dir: Path,
) -> Path:
    """Build a FlatGeoBuf river index with a ``is_peajogi`` flag.

    Merges Vooluveekogud (all watercourses) with Vooluveekogumid (main
    river bodies = peajõed) so the runtime can render main rivers with a
    thicker line weight (confirmed in the original design document).

    Parameters
    ----------
    vooluveekogud_path : Path
        Reprojected vooluveekogud.shp in EPSG:3301.
    vooluveekogumid_path : Path
        Reprojected vooluveekogumid.shp in EPSG:3301.
    output_dir : Path

    Returns
    -------
    Path
        Path to the written ``rivers.fgb``.
    """
    raise NotImplementedError("Phase 2 Step 3 — implemented after reproject_to_lest97 lands")


# ---------------------------------------------------------------------------
# Step 2 — CRS normalisation
# ---------------------------------------------------------------------------


def reproject_to_lest97(src_path: Path, output_dir: Path) -> Path:
    """Reproject a raster or vector file to EPSG:3301 if it isn't already.

    Skips reprojection if the source CRS is already EPSG:3301.  The output
    filename is ``<stem>_3301<suffix>`` placed in *output_dir*.

    Parameters
    ----------
    src_path : Path
    output_dir : Path

    Returns
    -------
    Path
        Path to the reprojected file (may equal *src_path* if no conversion
        was needed).
    """
    raise NotImplementedError("Phase 2 Step 2 — implemented after download_dataset lands")


# ---------------------------------------------------------------------------
# Step 1 — dataset download + sha256 verification
# ---------------------------------------------------------------------------


def download_dataset(name: str, data_dir: Path) -> Path:
    """Fetch an official Estonian dataset and verify its sha256.

    The download URL and expected filename come from the DATASETS registry
    above.  Most datasets are behind the Maa-amet / Keskkonnaportaali web
    portals and cannot be fetched with a single HTTP request — this function
    will raise NotImplementedError with a message explaining what to download
    manually until programmatic download is confirmed possible.

    Parameters
    ----------
    name : str
        Key from the DATASETS dict (e.g. ``"vooluveekogud"``).
    data_dir : Path
        Directory where raw downloads are stored (``data/raw/``).

    Returns
    -------
    Path
        Path to the downloaded file.
    """
    raise NotImplementedError(
        f"Dataset '{name}' must be downloaded manually from "
        f"{DATASETS[name]['source']} ({DATASETS[name]['portal_path']}) "
        f"and placed at {data_dir / DATASETS[name]['filename']}"
    )


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> None:
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="HydroCalc offline GIS preprocessor")
    parser.add_argument("--force", action="store_true", help="Rebuild even if outputs exist")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data"),
        help="Root data directory (default: data/)",
    )
    args = parser.parse_args()

    data_dir: Path = args.data_dir
    raw_dir = data_dir / "raw"
    preprocessed_dir = data_dir / "preprocessed"
    manifest_path = data_dir / "datasets.lock.json"

    logger.info("HydroCalc preprocessor — data dir: %s", data_dir)
    logger.info(
        "Steps 1–3 (download / reproject / river index) require manual "
        "dataset downloads from Maa-amet and Keskkonnaportaali. "
        "See DATASETS in this file for source URLs."
    )

    # Steps 4–6 loop over valglad — not yet implemented; see NotImplementedError stubs above.
    logger.info("Pipeline stub complete. Implement steps 1–6 in subsequent Phase 2 commits.")


if __name__ == "__main__":
    main()
