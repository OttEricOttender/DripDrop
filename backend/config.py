"""Centralised runtime configuration.

All paths, dataset versions, and feature flags flow through here so that
nothing else in the codebase hardcodes a path or magic number. This is a
prerequisite for the project's reproducibility goals — a single config
object is hashed into every PDF report footer so we can prove which
inputs and which formula revision produced a given calculation.

Environment overrides take the form ``HYDROCALC_<FIELD>``.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


# Repository root — resolved from this file's location so it survives both
# Docker volume mounts and local development.
REPO_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Runtime configuration loaded from environment + .env file."""

    model_config = SettingsConfigDict(
        env_prefix="HYDROCALC_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ---- Paths ----------------------------------------------------------
    repo_root: Path = REPO_ROOT
    data_dir: Path = REPO_ROOT / "data"
    raw_data_dir: Path = REPO_ROOT / "data" / "raw"
    preprocessed_dir: Path = REPO_ROOT / "data" / "preprocessed"
    output_dir: Path = REPO_ROOT / "output"
    datasets_manifest: Path = REPO_ROOT / "data" / "datasets.lock.json"

    # ---- CRS ------------------------------------------------------------
    # Estonia uses L-EST97 (EPSG:3301) for all official spatial datasets and
    # all engineering computations. WGS84 (EPSG:4326) is only for the
    # frontend basemap and API I/O.
    project_crs: str = "EPSG:3301"
    wgs84_crs: str = "EPSG:4326"

    # ---- Hydrology ------------------------------------------------------
    # Snap distance for "find nearest watercourse" per TÜ_projekt_protsess.pdf
    # step 2.c.ii: "Eeldatavalt punktil nt 30 m puhver".
    snap_buffer_m: float = 30.0

    # Hommik formula revision identifier — embedded into every result so we
    # can trace which formula version produced any historical PDF report.
    # Source: TÜ_projekt_protsess.pdf (formulas 1.1–1.8), retrieved 2026-05-12.
    hommik_formula_revision: str = "TY-protsess-2024-v1"

    # ---- Placeholder cartogram values (Phase 0/1 only!) -----------------
    # q̄_k (annual climatic drainage norm, l/(s·km²)) is normally sampled
    # from a Maa-amet cartogram raster. The raster has not been provided yet,
    # so we fall back to a hardcoded average for Estonia. THIS IS NOT
    # SCIENTIFICALLY DEFENSIBLE and every output that uses this value is
    # flagged with ``q_bar_k_source = "placeholder"`` in the result schema.
    q_bar_k_placeholder_l_per_s_km2: float = 7.0
    q_bar_k_raster_path: Path | None = None  # set when user provides raster

    # ---- Feature flags --------------------------------------------------
    enable_legacy_flask: bool = Field(
        default=True,
        description="Keep the legacy Flask app available at port 5000 during the FastAPI migration.",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the singleton Settings instance (cached for the process lifetime)."""
    return Settings()
