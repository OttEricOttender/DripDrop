"""POST /api/analyze — full GIS-to-Hommik pipeline endpoint.

Orchestrates the complete analysis chain:
  1. Coordinate resolution (WGS84 → L-EST97)
  2. Nearest-stream snap
  3. Valgla lookup
  4. Catchment delineation
  5. Land-cover breakdown
  6. Cartogram sampling (q̄_k and q_95%)
  7. Karl Hommik calculation
  8. Provenance assembly

No business logic lives here; each step delegates to a service module.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status

from backend.config import Settings, get_settings
from backend.gis import crs
from backend.models.schemas import (
    AnalysisRequest,
    AnalysisResult,
    CatchmentInfo,
    CoordinateLEST97,
    DatasetVersion,
    HommikInputs,
)
from backend.services import cartogram, hommik, snap, watershed, landcover

router = APIRouter(prefix="/api", tags=["analyze"])


def _preprocessed_dir(cfg: Settings) -> Path:
    return cfg.preprocessed_dir


@router.post("/analyze", response_model=AnalysisResult)
async def analyze(
    req: AnalysisRequest,
    cfg: Settings = Depends(get_settings),
) -> AnalysisResult:
    """Run the full hydrological analysis for a map point.

    Either ``point_wgs84`` or ``point_lest97`` must be provided (not both).
    Returns Karl Hommik spring and autumn peak flows with full provenance.
    """
    # --- 0. Resolve coordinates -------------------------------------------
    if req.point_wgs84 is not None and req.point_lest97 is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Provide exactly one of point_wgs84 or point_lest97, not both.",
        )
    if req.point_wgs84 is None and req.point_lest97 is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Provide one of point_wgs84 or point_lest97.",
        )

    if req.point_wgs84 is not None:
        x, y = crs.to_lest97(req.point_wgs84.lon, req.point_wgs84.lat)
    else:
        x, y = req.point_lest97.x, req.point_lest97.y  # type: ignore[union-attr]

    pre = _preprocessed_dir(cfg)

    # --- 1. Verify preprocessed data is available -------------------------
    rivers_fgb = pre / "rivers.fgb"
    if not rivers_fgb.exists():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                f"Preprocessed river index not found at {rivers_fgb}. "
                "Run scripts/preprocess.py to build the GIS artefacts."
            ),
        )

    warnings: list[str] = []

    # --- 2. Snap to nearest stream ----------------------------------------
    try:
        (x_snap, y_snap), river_info, snap_dist = snap.snap_to_stream(
            x, y, rivers_fgb, search_radius_m=cfg.snap_search_radius_m
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )

    # --- 3. Find valgla ---------------------------------------------------
    valglad_fgb = pre / "valglad.fgb"
    try:
        kkr_code, _ = watershed.find_valgla(x_snap, y_snap, valglad_fgb)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )

    # --- 4. Delineate catchment ------------------------------------------
    try:
        catchment_poly, area_km2 = watershed.delineate_catchment(
            x_snap, y_snap, kkr_code, pre
        )
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )

    catchment_info = CatchmentInfo(code=kkr_code, area_km2=area_km2)

    # --- 5. Land-cover breakdown -----------------------------------------
    kolvikud_fgb = pre / "kolvikud.fgb"
    msr_vork_fgb = pre / "msr_vork.fgb"
    landcover_breakdown, lc_warnings = landcover.compute_landcover(
        catchment_poly, area_km2, kolvikud_fgb, msr_vork_fgb
    )
    warnings.extend(lc_warnings)

    # --- 6. Cartogram sampling -------------------------------------------
    q_bar_k_sample = cartogram.sample_q_bar_k(x_snap, y_snap)
    q95_sample = cartogram.sample_q95(x_snap, y_snap)

    if q_bar_k_sample.source == "placeholder":
        warnings.append(
            f"q̄_k = {q_bar_k_sample.value_l_per_s_km2} l/(s·km²) is a placeholder "
            f"(national average). Results are NOT legally defensible until the "
            f"q̄_k cartogram raster is provided via HYDROCALC_Q_BAR_K_RASTER_PATH."
        )
    if q95_sample.source == "placeholder":
        warnings.append(
            f"q_95% = {q95_sample.value_l_per_s_km2} l/(s·km²) is a placeholder. "
            f"Set HYDROCALC_Q95_RASTER_PATH to TopoToR_JOON41.tif for site-specific values."
        )

    # --- 7. Karl Hommik calculation --------------------------------------
    hommik_inputs = HommikInputs(
        A_km2=area_km2,
        p_percent=req.p_percent,
        q_bar_k_l_per_s_km2=q_bar_k_sample.value_l_per_s_km2,
        q95_l_per_s_km2=q95_sample.value_l_per_s_km2,
        landcover=landcover_breakdown,
    )
    hommik_result = hommik.compute(
        hommik_inputs,
        formula_revision=cfg.hommik_formula_revision,
        q_bar_k_source=q_bar_k_sample.source,
    )

    # --- 8. Provenance ---------------------------------------------------
    dataset_versions: list[DatasetVersion] = []
    manifest_path = cfg.datasets_manifest
    if manifest_path.exists():
        try:
            from scripts.preprocess import read_manifest
            manifest = read_manifest(manifest_path)
            for entry in manifest.get("datasets", []):
                try:
                    dataset_versions.append(DatasetVersion(
                        name=entry["name"],
                        source_url=entry.get("source_url", "unknown"),
                        sha256=entry["sha256"],
                        retrieved_at=datetime.fromisoformat(entry["retrieved_at"]),
                        crs=entry.get("crs", "unknown"),
                    ))
                except (KeyError, ValueError):
                    pass
        except Exception:
            pass

    return AnalysisResult(
        run_id=uuid.uuid4().hex,
        timestamp=datetime.now(timezone.utc),
        input_point_lest97=CoordinateLEST97(x=x, y=y),
        snapped_point_lest97=CoordinateLEST97(x=x_snap, y=y_snap),
        snap_distance_m=snap_dist,
        river=river_info,
        catchment=catchment_info,
        landcover=landcover_breakdown,
        hommik=hommik_result,
        dataset_versions=dataset_versions,
        warnings=warnings,
    )
