"""Health and readiness endpoints.

Kept deliberately minimal — only reports whether the app is up and whether
the q̄_k cartogram has been configured. Real readiness (DB connectivity,
preprocessed data availability) is added in Phase 3 when the runtime
pipeline lands.
"""

from __future__ import annotations

from fastapi import APIRouter

from backend import __version__
from backend.config import get_settings
from backend.models.schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/healthz", response_model=HealthResponse)
def healthz() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="ok",
        version=__version__,
        formula_revision=settings.hommik_formula_revision,
        q_bar_k_source=("raster" if settings.q_bar_k_raster_path else "placeholder"),
    )
