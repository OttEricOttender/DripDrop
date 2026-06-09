"""Land-cover breakdown service.

Computes the ETAK kolvikud category percentages for a catchment polygon and
maps them to the Hommik formula parameters (A_ms, A_r, A_km, B, C).

ETAK code mapping
-----------------
301  muu kõlvik        → C (lage / bare mineral land)
302  õu                → C
303  haritav maa       → C (arable)
304  lage              → C
305  puittaimestik     → B (wooded/shrubby mineral land)
306  märgala           → wetland pool; split by msr_vork overlay:
       ∩ msr_vork  → A_km (intensively drained low-bog)
       outside     → split 80/20 → A_ms (madalsood) + A_r (rabad)

The 80 / 20 märgala split is a legacy approximation used in scripts/delineate.py
because ETAK does not distinguish between low-bogs (madalsood) and raised-bogs
(rabad) within kood 306.  See docs/decisions.md ADR-003 for rationale.

a_wet_mineral_plus_akm
----------------------
The Hommik formula (1.2) uses `a` = wet-mineral land + A_km.  Since ETAK
codes 305 and 306 are mutually exclusive per polygon (each polygon has exactly
one kood value), the 305 ∩ 306 spatial overlap is zero by construction.
Therefore a_wet_mineral_plus_akm = A_km.  This is documented here and in the
ADR; no future change is expected unless the ETAK schema changes.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
from shapely.geometry import mapping

from backend.models.schemas import LandCoverBreakdown

logger = logging.getLogger(__name__)

# ETAK codes that map to the "C" (lage mineraalmaa) parameter
_C_CODES = frozenset({301, 302, 303, 304})
_B_CODE = 305
_WETLAND_CODE = 306

# 80/20 split of non-drained märgala (kood 306 outside msr_vork).
# Legacy approximation — see docs/decisions.md ADR-003.
_A_MS_FRACTION = 0.80
_A_R_FRACTION = 0.20


def compute_landcover(
    catchment_poly: Any,
    catchment_area_km2: float,
    kolvikud_fgb: Path,
    msr_vork_fgb: Path,
) -> tuple[LandCoverBreakdown, list[str]]:
    """Compute the Hommik land-cover breakdown for a catchment polygon.

    Parameters
    ----------
    catchment_poly : shapely Polygon
        Catchment boundary in EPSG:3301.
    catchment_area_km2 : float
        Catchment area in km² (used as denominator; must be > 0).
    kolvikud_fgb : Path
        FlatGeoBuf produced by ``merge_kolvikud()`` (columns: kood, kood_t, geometry).
    msr_vork_fgb : Path
        FlatGeoBuf produced by preprocess Step 3d (drainage system polygons).

    Returns
    -------
    breakdown : LandCoverBreakdown
        All values as % of catchment area, clamped to [0, 100].
    warnings : list[str]
        Non-fatal data-quality and placeholder notes.
    """
    if catchment_area_km2 <= 0:
        raise ValueError("catchment_area_km2 must be positive")

    warnings: list[str] = []
    catchment_area_m2 = catchment_area_km2 * 1_000_000.0

    catchment_gdf = gpd.GeoDataFrame(
        geometry=[catchment_poly], crs="EPSG:3301"
    )
    bounds = catchment_poly.bounds  # (minx, miny, maxx, maxy)

    # ------------------------------------------------------------------
    # 1. Clip kolvikud to catchment and compute area per kood
    # ------------------------------------------------------------------
    kolvikud_clip = _read_and_clip(kolvikud_fgb, bounds, catchment_gdf, "kolvikud")

    area_by_kood: dict[int, float] = {}  # kood → area in m²
    if kolvikud_clip is not None and not kolvikud_clip.empty:
        kolvikud_clip = kolvikud_clip.copy()
        kolvikud_clip["_area"] = kolvikud_clip.geometry.area
        for kood, group in kolvikud_clip.groupby("kood"):
            area_by_kood[int(kood)] = float(group["_area"].sum())

    wetland_m2 = area_by_kood.get(_WETLAND_CODE, 0.0)
    B_m2 = area_by_kood.get(_B_CODE, 0.0)
    C_m2 = sum(v for k, v in area_by_kood.items() if k in _C_CODES)

    # ------------------------------------------------------------------
    # 2. Clip msr_vork to catchment → total drainage area
    # ------------------------------------------------------------------
    msr_clip = _read_and_clip(msr_vork_fgb, bounds, catchment_gdf, "msr_vork")
    msr_area_m2 = float(msr_clip.geometry.area.sum()) if (msr_clip is not None and not msr_clip.empty) else 0.0

    # ------------------------------------------------------------------
    # 3. Overlay ETAK 306 with msr_vork → A_km (drained märgala)
    # ------------------------------------------------------------------
    A_km_m2 = 0.0
    if wetland_m2 > 0 and msr_area_m2 > 0 and kolvikud_clip is not None:
        wetland_poly = kolvikud_clip[kolvikud_clip["kood"] == _WETLAND_CODE]
        if not wetland_poly.empty and msr_clip is not None and not msr_clip.empty:
            try:
                drained = gpd.overlay(wetland_poly, msr_clip, how="intersection")
                A_km_m2 = float(drained.geometry.area.sum())
            except Exception as exc:
                logger.warning("msr_vork ∩ märgala overlay failed: %s", exc)

    # ------------------------------------------------------------------
    # 4. Non-drained märgala → 80 % A_ms + 20 % A_r (legacy split)
    # ------------------------------------------------------------------
    non_drained_m2 = max(0.0, wetland_m2 - A_km_m2)
    A_ms_m2 = non_drained_m2 * _A_MS_FRACTION
    A_r_m2 = non_drained_m2 * _A_R_FRACTION

    # ------------------------------------------------------------------
    # 5. Convert to % of catchment area; clamp to [0, 100]
    # ------------------------------------------------------------------
    def _pct(m2: float) -> float:
        return float(np.clip(m2 / catchment_area_m2 * 100.0, 0.0, 100.0))

    A_ms = _pct(A_ms_m2)
    A_r = _pct(A_r_m2)
    A_km = _pct(A_km_m2)
    B = _pct(B_m2)
    C = _pct(C_m2)
    maaparandus = _pct(msr_area_m2)

    # a_wet_mineral_plus_akm = A_km (305 ∩ 306 overlap is zero by ETAK design)
    a_wet_mineral_plus_akm = A_km

    # Sanity check — ETAK polygons may overlap the catchment boundary in ways
    # that push the sum slightly above 100 % due to edge rasterisation artefacts.
    total = A_ms + A_r + A_km + B + C
    if total > 100.5:
        warnings.append(
            f"Land-cover categories sum to {total:.1f}% > 100% — possible ETAK "
            f"polygon overlap at catchment boundary. Values are individually clamped."
        )

    # These two notes are logged at INFO level, not surfaced to the user, because
    # they describe known approximations that are already documented in ADR-011 and
    # ADR-003 respectively.  They are intentional design choices, not actionable
    # warnings for the end user.  See docs/decisions.md for the full rationale.
    logger.info(
        "maaparandus area: %.4f %% of catchment (from msr_vork.fgb); "
        "informational only — maaparandus is not yet consumed by Karl Hommik formulas",
        maaparandus,
    )
    logger.info(
        "A_ms/A_r 80/20 split applied (legacy approximation, ADR-011): "
        "A_ms=%.4f %%, A_r=%.4f %%",
        A_ms,
        A_r,
    )

    return (
        LandCoverBreakdown(
            A_ms=A_ms,
            A_r=A_r,
            A_km=A_km,
            B=B,
            C=C,
            maaparandus=maaparandus,
            a_wet_mineral_plus_akm=a_wet_mineral_plus_akm,
        ),
        warnings,
    )


def _read_and_clip(
    fgb_path: Path,
    bounds: tuple[float, float, float, float],
    catchment_gdf: gpd.GeoDataFrame,
    label: str,
) -> gpd.GeoDataFrame | None:
    """Read a FlatGeoBuf by bbox, clip to catchment, return clipped GDF or None."""
    if not fgb_path.exists():
        logger.warning("%s FlatGeoBuf not found: %s — using zero area", label, fgb_path)
        return None
    try:
        gdf = gpd.read_file(fgb_path, bbox=bounds)
    except Exception as exc:
        logger.warning("Failed to read %s: %s — using zero area", label, exc)
        return None
    if gdf.empty:
        return gdf
    try:
        return gpd.overlay(gdf, catchment_gdf, how="intersection")
    except Exception as exc:
        logger.warning("Overlay with catchment failed for %s: %s", label, exc)
        return gdf  # fall back to unclipped (over-counts near boundary)
