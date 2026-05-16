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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import rasterio
import rasterio.features
import rasterio.warp
from pysheds.grid import Grid
from pysheds.sview import Raster
from rasterio.crs import CRS
from rasterio.enums import Resampling
from rasterio.transform import from_origin

from backend.utils.hashing import sha256_file

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

    Uses rasterio's masked-window read so only the bounding box of the valgla
    polygon is loaded — the full 50 GB Estonian DTM is never in memory whole.
    This bounds RAM usage to the largest valgla (Pärnu ~6 700 km²) even on
    modest machines.

    The output is written as a deflate-compressed GeoTIFF in EPSG:3301.
    Cells outside the polygon boundary are set to DEM_NODATA (-9999 float32)
    so pysheds treats them as no-data and does not route flow across them.

    Parameters
    ----------
    valgla_geom : shapely geometry
        The valgla polygon in EPSG:3301.
    dem_path : Path
        Path to the national DTM (DTM_5m_eesti.tif) in EPSG:3301.
    kkr_code : str
        KKR identifier used to name the output file (e.g. ``"VEE_1234"``).
    output_dir : Path
        Destination directory; must already exist.

    Returns
    -------
    Path
        Path to the written ``<kkr_code>.tif``.
    """
    from rasterio.mask import mask as rasterio_mask
    from shapely.geometry import mapping

    with rasterio.open(dem_path) as src:
        clipped, transform = rasterio_mask(
            src,
            [mapping(valgla_geom)],
            crop=True,
            nodata=float(DEM_NODATA),
            all_touched=False,
        )
        # Ensure float32 so pysheds 0.4 can load the nodata without dtype conflicts
        clipped = clipped.astype(np.float32)
        meta = src.meta.copy()
        meta.update(
            height=clipped.shape[1],
            width=clipped.shape[2],
            transform=transform,
            nodata=float(DEM_NODATA),
            dtype="float32",
            compress="deflate",
            crs=LEST97,
        )

    out_path = output_dir / f"{kkr_code}.tif"
    with rasterio.open(out_path, "w", **meta) as dst:
        dst.write(clipped)

    logger.info(
        "Clipped DEM for %s: %d×%d px → %s",
        kkr_code, clipped.shape[2], clipped.shape[1], out_path,
    )
    return out_path


def process_valgla(
    dem_clip_path: Path,
    kkr_code: str,
    output_dir: Path,
) -> tuple[Path, Path]:
    """Condition the clipped DEM and write flow-dir + flow-acc rasters.

    Runs the pysheds conditioning chain (fill_pits → fill_depressions →
    resolve_flats → flowdir → accumulation) on the per-valgla DEM clip and
    writes both outputs to disk in EPSG:3301.  Subdirectories
    ``output_dir/flowdir/`` and ``output_dir/flowacc/`` are created if
    they don't exist.

    Parameters
    ----------
    dem_clip_path : Path
        Output of clip_dem() for this valgla.
    kkr_code : str
        KKR identifier used to name the output files.
    output_dir : Path
        Base directory.

    Returns
    -------
    flowdir_path : Path
    flowacc_path : Path
    """
    flowdir_dir = output_dir / "flowdir"
    flowacc_dir = output_dir / "flowacc"
    flowdir_dir.mkdir(parents=True, exist_ok=True)
    flowacc_dir.mkdir(parents=True, exist_ok=True)

    grid, dem = load_dem(dem_clip_path)
    conditioned = condition_dem(grid, dem)
    fdir = compute_flowdir(grid, conditioned)
    acc = compute_flowacc(grid, fdir)

    flowdir_path = flowdir_dir / f"{kkr_code}.tif"
    flowacc_path = flowacc_dir / f"{kkr_code}.tif"

    _write_pysheds_raster(fdir, flowdir_path)
    _write_pysheds_raster(acc, flowacc_path)

    logger.info(
        "process_valgla %s: flowdir → %s, flowacc → %s",
        kkr_code, flowdir_path, flowacc_path,
    )
    return flowdir_path, flowacc_path


def _write_pysheds_raster(raster: Raster, path: Path) -> None:
    """Write a pysheds Raster to a deflate-compressed GeoTIFF in EPSG:3301.

    Always stamps LEST97 as the CRS regardless of what the Raster carries,
    because all preprocessing work is in EPSG:3301 (inviolable rule #2).
    """
    arr = np.asarray(raster)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=arr.shape[0],
        width=arr.shape[1],
        count=1,
        dtype=str(arr.dtype),
        crs=LEST97,
        transform=raster.affine,
        nodata=raster.nodata,
        compress="deflate",
    ) as dst:
        dst.write(arr, 1)


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

    Reads Vooluveekogud (all watercourse segments) and Vooluveekogumid (the
    main river body polygons = peajõed).  A spatial join marks each segment
    ``is_peajogi=True`` if it intersects a vooluveekogumid polygon.  This
    drives the thick/thin line rendering confirmed in the original design
    document (Google Doc).

    The output is written as FlatGeoBuf, which embeds a spatial index at
    write time.  Phase 3 can issue fast bbox queries without loading the full
    national dataset into memory.

    Parameters
    ----------
    vooluveekogud_path : Path
        All watercourse segments in EPSG:3301 (output of reproject_to_lest97).
    vooluveekogumid_path : Path
        Main river body polygons in EPSG:3301 (output of reproject_to_lest97).
    output_dir : Path
        Destination directory; must already exist.

    Returns
    -------
    Path
        Path to the written ``rivers.fgb``.
    """
    rivers = gpd.read_file(vooluveekogud_path)
    bodies = gpd.read_file(vooluveekogumid_path)

    if rivers.crs is None or rivers.crs.to_epsg() != 3301:
        raise ValueError(
            f"vooluveekogud must be in EPSG:3301; got {rivers.crs}. "
            "Run reproject_to_lest97() first."
        )

    if len(bodies) == 0:
        # No vooluveekogumid polygons → every segment is a lisajõgi
        rivers = rivers.copy()
        rivers["is_peajogi"] = False
    else:
        # Spatial join: find which river segments intersect a body polygon.
        # predicate='intersects' handles both point-on-boundary and overlap cases.
        # how='left' keeps all river segments even if they match nothing.
        joined = gpd.sjoin(rivers, bodies[["geometry"]], how="left", predicate="intersects")

        # sjoin may produce multiple rows per river segment when a segment
        # intersects more than one polygon.  Take the first match per segment.
        matched_indices = set(
            joined.dropna(subset=["index_right"]).index.tolist()
        )
        rivers = rivers.copy()
        rivers["is_peajogi"] = rivers.index.isin(matched_indices)

    out_path = output_dir / "rivers.fgb"
    rivers.to_file(out_path, driver="FlatGeobuf")
    logger.info(
        "River index written: %d segments (%d peajõed) → %s",
        len(rivers),
        rivers["is_peajogi"].sum(),
        out_path,
    )
    return out_path


# ---------------------------------------------------------------------------
# Step 2 — CRS normalisation
# ---------------------------------------------------------------------------

_RASTER_SUFFIXES = {".tif", ".tiff", ".img", ".vrt"}
_VECTOR_SUFFIXES = {".shp", ".gpkg", ".geojson", ".fgb"}


def reproject_to_lest97(src_path: Path, output_dir: Path) -> Path:
    """Reproject a raster or vector file to EPSG:3301 if it isn't already.

    Detects raster vs vector by file extension.  If the source CRS is already
    EPSG:3301, returns *src_path* unchanged (no copy made, no disk I/O).
    Otherwise writes ``<stem>_3301<suffix>`` into *output_dir* and returns
    that path.

    All reprojected files are written in EPSG:3301 (L-EST97) per the
    inviolable CRS rule.  The source file is never modified.

    Parameters
    ----------
    src_path : Path
    output_dir : Path
        Destination directory; must already exist.

    Returns
    -------
    Path
        Reprojected file path, or *src_path* if already EPSG:3301.
    """
    suffix = src_path.suffix.lower()
    if suffix in _RASTER_SUFFIXES:
        return _reproject_raster(src_path, output_dir)
    if suffix in _VECTOR_SUFFIXES:
        return _reproject_vector(src_path, output_dir)
    raise ValueError(
        f"Unrecognised file type '{suffix}' — add it to _RASTER_SUFFIXES or _VECTOR_SUFFIXES"
    )


def _reproject_raster(src_path: Path, output_dir: Path) -> Path:
    with rasterio.open(src_path) as src:
        if src.crs and src.crs.to_epsg() == 3301:
            logger.debug("reproject_to_lest97: %s is already EPSG:3301, skipping", src_path.name)
            return src_path

        dst_transform, dst_width, dst_height = rasterio.warp.calculate_default_transform(
            src.crs, LEST97, src.width, src.height, *src.bounds
        )
        dst_meta = src.meta.copy()
        dst_meta.update(
            crs=LEST97,
            transform=dst_transform,
            width=dst_width,
            height=dst_height,
            nodata=DEM_NODATA,
            compress="deflate",
        )
        out_path = output_dir / f"{src_path.stem}_3301{src_path.suffix}"
        with rasterio.open(out_path, "w", **dst_meta) as dst:
            for band in range(1, src.count + 1):
                rasterio.warp.reproject(
                    source=rasterio.band(src, band),
                    destination=rasterio.band(dst, band),
                    src_transform=src.transform,
                    src_crs=src.crs,
                    dst_transform=dst_transform,
                    dst_crs=LEST97,
                    resampling=Resampling.bilinear,
                )
    logger.info("Reprojected raster %s → %s", src_path.name, out_path.name)
    return out_path


def _reproject_vector(src_path: Path, output_dir: Path) -> Path:
    gdf = gpd.read_file(src_path)
    if gdf.crs and gdf.crs.to_epsg() == 3301:
        logger.debug("reproject_to_lest97: %s is already EPSG:3301, skipping", src_path.name)
        return src_path

    gdf_3301 = gdf.to_crs(epsg=3301)
    out_path = output_dir / f"{src_path.stem}_3301{src_path.suffix}"
    suffix = src_path.suffix.lower()
    driver = "GPKG" if suffix == ".gpkg" else ("GeoJSON" if suffix == ".geojson" else "ESRI Shapefile")
    gdf_3301.to_file(out_path, driver=driver)
    logger.info("Reprojected vector %s → %s", src_path.name, out_path.name)
    return out_path


# ---------------------------------------------------------------------------
# Step 1 — dataset download + sha256 verification
# ---------------------------------------------------------------------------

_MANIFEST_TEMPLATE: dict[str, Any] = {
    "schema_version": 1,
    "manifest_version": "0.2.0-phase2",
    "generated_at": None,
    "formula_revision": "TY-protsess-2024-v1",
    "notes": [
        "Populated by scripts/preprocess.py.",
        "Every entry carries source URL, sha256, retrieval timestamp, and CRS",
        "so any calculation can be replayed years later from the same bytes.",
    ],
    "datasets": [],
    "placeholders": {
        "q_bar_k": {
            "in_use": True,
            "value_l_per_s_km2": 7.0,
            "reason": (
                "Cartogram raster not yet provided. All outputs that depend on "
                "q_bar_k are flagged 'placeholder' until the raster is uploaded."
            ),
        }
    },
}


def download_dataset(
    name: str,
    data_dir: Path,
    manifest_path: Path | None = None,
) -> Path:
    """Verify (and optionally pin) the sha256 of a manually downloaded dataset.

    The Maa-amet and Keskkonnaportaali portals do not offer direct-download
    URLs — files must be downloaded through their web interfaces and placed
    in ``data_dir/raw/`` before running this pipeline.  This function:

    1. Checks that the expected file exists; raises ``FileNotFoundError``
       with explicit download instructions if it doesn't.
    2. Computes the file's SHA-256.
    3. If no hash is pinned in *manifest_path* yet, records it and returns.
    4. If a hash is already pinned, verifies the file matches it.  Raises
       ``ValueError`` if there is a mismatch (bit-rot or unintended update).

    Parameters
    ----------
    name : str
        Key from the DATASETS registry (e.g. ``"vooluveekogud"``).
    data_dir : Path
        Root data directory.  Raw files are expected at ``data_dir/raw/``.
    manifest_path : Path | None
        Path to ``datasets.lock.json``.  Defaults to ``data_dir/datasets.lock.json``.

    Returns
    -------
    Path
        Path to the verified file.

    Raises
    ------
    KeyError
        If *name* is not in the DATASETS registry.
    FileNotFoundError
        If the expected file does not exist (with download instructions).
    ValueError
        If the file's sha256 does not match the pinned hash.
    """
    if name not in DATASETS:
        raise KeyError(
            f"Unknown dataset '{name}'. Known datasets: {sorted(DATASETS)}"
        )

    info = DATASETS[name]
    raw_dir = data_dir / "raw"
    file_path = raw_dir / info["filename"]

    if not file_path.exists():
        raise FileNotFoundError(
            f"Dataset '{name}' not found at {file_path}.\n"
            f"  Download from: {info['source']}\n"
            f"  Portal path:   {info['portal_path']}\n"
            f"  Save to:       {file_path}"
        )

    checksum = sha256_file(file_path)

    if manifest_path is None:
        manifest_path = data_dir / "datasets.lock.json"

    if manifest_path.exists():
        manifest = read_manifest(manifest_path)
    else:
        import copy
        manifest = copy.deepcopy(_MANIFEST_TEMPLATE)

    entries: dict[str, Any] = {e["name"]: e for e in manifest.get("datasets", [])}

    if name in entries:
        pinned = entries[name]["sha256"]
        if pinned != checksum:
            raise ValueError(
                f"SHA-256 mismatch for '{name}':\n"
                f"  pinned: {pinned}\n"
                f"  got:    {checksum}\n"
                f"The file at {file_path} does not match the pinned hash.\n"
                f"If you intentionally updated the dataset, remove its entry from\n"
                f"{manifest_path} and re-run to re-pin the new hash."
            )
        logger.debug("sha256 OK for '%s'", name)
    else:
        entry: dict[str, Any] = {
            "name": name,
            "source_url": info["source"],
            "sha256": checksum,
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "crs": "unknown",        # updated to EPSG:3301 after reproject_to_lest97
            "resolution_m": None,    # populated for rasters
            "output_path": str(file_path),
        }
        manifest.setdefault("datasets", []).append(entry)
        write_manifest(manifest, manifest_path)
        logger.info("Pinned sha256 for '%s': %s", name, checksum)

    return file_path


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
