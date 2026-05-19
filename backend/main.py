"""FastAPI application entry point.

This is the new HTTP layer for HydroCalc, replacing the Flask app in
``app/main.py``. The Flask app is preserved during the migration so that
the existing Cypress E2E tests and demo environments keep working.

Run locally::

    uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000

In Docker, ``docker/backend/Dockerfile`` invokes uvicorn directly.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend import __version__
from backend.api.routes import analyze, health, hommik, report
from backend.config import get_settings
from backend.utils.logging import configure_logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Startup/shutdown hook — sets up logging and prints a placeholder warning
    if the q̄_k cartogram has not been provided yet.
    """
    configure_logging()
    settings = get_settings()
    if settings.q_bar_k_raster_path is None:
        logger.warning(
            "q_bar_k cartogram raster is NOT configured; using placeholder value "
            "%.3f l/(s·km²). Outputs will be flagged as non-defensible until the "
            "raster is provided. See backend/services/cartogram.py.",
            settings.q_bar_k_placeholder_l_per_s_km2,
        )
    yield
    # nothing to clean up on shutdown yet


def create_app() -> FastAPI:
    """Application factory — keeps the module side-effect-free so the same
    factory can be reused by tests with a clean ``Settings`` instance.
    """
    app = FastAPI(
        title="HydroCalc API",
        description=(
            "Estonia-specific hydrological analysis platform (svam.ee). "
            "Computes Karl Hommik design drainage values for engineering use."
        ),
        version=__version__,
        lifespan=lifespan,
    )

    # CORS — the React frontend runs on a separate origin in dev.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],          # tightened per-environment in Phase 6
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(hommik.router)
    app.include_router(analyze.router)
    app.include_router(report.router)

    return app


app = create_app()
