"""Karl Hommik calculator endpoint.

This route is the Phase 1 demo surface. It accepts a fully specified
``HommikInputs`` payload (no GIS dependencies yet) and returns the
complete ``HommikResult``. In Phase 3 it gets wrapped inside the larger
``POST /api/analyze`` pipeline, but it stays callable on its own so
engineers can sanity-check the formulas with hand-tuned inputs.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Body, HTTPException, status

from backend.config import get_settings
from backend.models.schemas import HommikInputs, HommikResult
from backend.services import cartogram, hommik

router = APIRouter(prefix="/api/hommik", tags=["hommik"])


# Example payload shown in the Swagger UI — based on the worked example
# in tests/test_hommik.py so the docs page is a runnable demo.
EXAMPLE_PAYLOAD = {
    "A_km2": 100.0,
    "p_percent": 10.0,
    "q_bar_k_l_per_s_km2": 7.0,
    "q95_l_per_s_km2": 2.0,
    "landcover": {
        "A_ms": 10.0,
        "A_r": 5.0,
        "A_km": 15.0,
        "B": 30.0,
        "C": 40.0,
        "maaparandus": 20.0,
        "a_wet_mineral_plus_akm": 20.0,
    },
}


@router.post(
    "/calculate",
    response_model=HommikResult,
    summary="Compute Karl Hommik design drainage from raw inputs",
    description=(
        "Phase 1 demo endpoint. Accepts hand-specified catchment area, "
        "land-cover percentages, and cartogram values, and returns the "
        "full Hommik calculation (formulas 1.1–1.8). Useful for "
        "regression-testing the formulas without needing the full GIS "
        "pipeline (which lands in Phase 3)."
    ),
)
def calculate(
    inputs: Annotated[HommikInputs, Body(examples=[EXAMPLE_PAYLOAD])],
) -> HommikResult:
    settings = get_settings()

    # Sanity check: land-cover shares must sum to ~100 % (allow 1 % slack
    # for rounding and the maaparandus overlap, which isn't part of the sum).
    lc = inputs.landcover
    total = lc.A_ms + lc.A_r + lc.A_km + lc.B + lc.C
    if not 99.0 <= total <= 101.0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Land-cover percentages must sum to ~100 (got {total:.2f}). "
                "A_ms + A_r + A_km + B + C should cover the entire catchment."
            ),
        )

    # In Phase 1 we trust the inputs as supplied. In Phase 3 the caller will
    # have sampled cartogram.sample_q_bar_k / sample_q95 already, but we
    # still record provenance here so /docs always knows whether the answer
    # is defensible.
    q_bar_k_source = "raster" if settings.q_bar_k_raster_path else "placeholder"

    try:
        result = hommik.compute(
            inputs=inputs,
            formula_revision=settings.hommik_formula_revision,
            q_bar_k_source=q_bar_k_source,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    return result


@router.get(
    "/cartogram-status",
    summary="Report whether q̄_k / q_95% rasters are wired up",
)
def cartogram_status() -> dict[str, object]:
    settings = get_settings()
    return {
        "q_bar_k": {
            "source": "raster" if settings.q_bar_k_raster_path else "placeholder",
            "placeholder_value_l_per_s_km2": settings.q_bar_k_placeholder_l_per_s_km2,
            "raster_path": (
                str(settings.q_bar_k_raster_path) if settings.q_bar_k_raster_path else None
            ),
        },
        "q95": {
            "source": "request-body-fallback",
            "note": (
                "q_95% raster sampling is implemented in Phase 2. Until then the "
                "caller supplies it in the request body."
            ),
        },
        "formula_revision": settings.hommik_formula_revision,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
