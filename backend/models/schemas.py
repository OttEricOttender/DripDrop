"""Pydantic request/response schemas.

These types are the public API contract. Every shape that crosses the
HTTP boundary or that lands in a PDF report goes through here. Two
invariants:

* All coordinates are tagged with their CRS — never implicit.
* Every scientific result carries provenance: dataset versions, formula
  revision, and a flag for any placeholder inputs.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Coordinates
# ---------------------------------------------------------------------------


class CoordinateWGS84(BaseModel):
    """Latitude/longitude in EPSG:4326. Used at the API boundary only."""

    model_config = ConfigDict(extra="forbid")
    lat: float = Field(..., ge=57.0, le=60.0, description="Latitude (Estonia bounds)")
    lon: float = Field(..., ge=21.0, le=29.0, description="Longitude (Estonia bounds)")


class CoordinateLEST97(BaseModel):
    """Easting/northing in EPSG:3301 (Estonia's official engineering CRS)."""

    model_config = ConfigDict(extra="forbid")
    x: float = Field(..., description="Easting in metres (L-EST97)")
    y: float = Field(..., description="Northing in metres (L-EST97)")


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


class HealthResponse(BaseModel):
    status: Literal["ok"]
    version: str
    formula_revision: str
    q_bar_k_source: Literal["raster", "placeholder"]


# ---------------------------------------------------------------------------
# Land-cover categorisation per TÜ_projekt_protsess.pdf step 4.c
# ---------------------------------------------------------------------------


class LandCoverBreakdown(BaseModel):
    """All values are percentages of the catchment area (0–100)."""

    model_config = ConfigDict(extra="forbid")
    A_ms: float = Field(..., ge=0, le=100, description="Madalsood ja soometsad (%)")
    A_r: float = Field(..., ge=0, le=100, description="Rabad (%)")
    A_km: float = Field(..., ge=0, le=100, description="Intensiivselt kuivendatud madalsood (%)")
    B: float = Field(..., ge=0, le=100, description="Metsaga ja võsaga kaetud mineraalmaa (%)")
    C: float = Field(..., ge=0, le=100, description="Lage mineraalmaa (%)")
    maaparandus: float = Field(..., ge=0, le=100, description="Maaparandussüsteemi pindala (%)")
    # The `a` parameter from formula (1.2): wet-mineral B share + A_km. Surfaced
    # explicitly so the report can document our derivation choice.
    a_wet_mineral_plus_akm: float = Field(
        ..., ge=0, le=100, description="`a` parameter for formula (1.2) — wet-mineral B + A_km (%)",
    )


# ---------------------------------------------------------------------------
# River metadata
# ---------------------------------------------------------------------------


class RiverInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(..., description="Vooluveekogu KKR code")
    name: str
    river_type: str | None = None
    length_m: float | None = None
    is_main: bool = Field(False, description="True for peajõed (main rivers)")


class CatchmentInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str | None = Field(None, description="Official Vooluveekogude valgla KKR code")
    name: str | None = None
    area_km2: float = Field(..., gt=0)


# ---------------------------------------------------------------------------
# Hommik calculation result
# ---------------------------------------------------------------------------


class HommikInputs(BaseModel):
    """Inputs to the Karl Hommik formulas (1.1)–(1.7).

    Every field has a unit + reference to the PDF where it is defined.
    """

    model_config = ConfigDict(extra="forbid")
    A_km2: float = Field(..., gt=0, description="Valgala pindala A (km²) — formula (1.3)/(1.6)")
    p_percent: float = Field(10.0, gt=0, le=100, description="Ületõusutõenäosus p (%)")
    q_bar_k_l_per_s_km2: float = Field(..., gt=0, description="Aasta klimaatiline äravoolunorm q̄_k")
    q95_l_per_s_km2: float = Field(..., ge=0, description="95% min äravoolumoodul (kartogramm)")
    landcover: LandCoverBreakdown


class HommikResult(BaseModel):
    """Output of the Karl Hommik calculator. Embedded in PDF reports."""

    model_config = ConfigDict(extra="forbid")
    q_bar_l_per_s_km2: float = Field(..., description="Äravoolunorm q̄ — formula (1.1)")
    delta_q_l_per_s_km2: float = Field(..., description="Parand Δq — formula (1.2)")
    k95: float = Field(..., description="k_95% = q_95% / q̄ — formula (1.4)")
    r_s: float = Field(..., description="Sügisene tippäravoolu parameeter — formula (1.5)")
    r: float = Field(..., description="Kevadine tippäravoolu parameeter — formula (1.7)")
    q_veg_max_l_per_s_km2: float = Field(..., description="Sügisene tippäravoolu moodul — formula (1.3)")
    q_kev_max_l_per_s_km2: float = Field(..., description="Kevadine tippäravoolu moodul — formula (1.6)")
    Q_veg_max_m3_per_s: float = Field(..., description="Sügisene tippvooluhulk — formula (1.8)")
    Q_kev_max_m3_per_s: float = Field(..., description="Kevadine tippvooluhulk — formula (1.8)")
    # Provenance — required for legal defensibility.
    formula_revision: str
    area_floored_to_100km2: bool = Field(
        ..., description="True if A < 100 km² was forced to 100 km² per PDF page 5"
    )
    q_bar_k_source: Literal["raster", "placeholder"]


# ---------------------------------------------------------------------------
# Top-level analyze response
# ---------------------------------------------------------------------------


class DatasetVersion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    source_url: str
    sha256: str
    retrieved_at: datetime
    crs: str


class AnalysisRequest(BaseModel):
    """Request to ``POST /api/analyze``.

    Exactly one of ``point_wgs84`` or ``point_lest97`` must be provided.
    Validation of mutual exclusivity is done in the route handler so the
    error message is human-friendly.
    """

    model_config = ConfigDict(extra="forbid")
    point_wgs84: CoordinateWGS84 | None = None
    point_lest97: CoordinateLEST97 | None = None
    p_percent: float = Field(10.0, gt=0, le=100, description="Ületõusutõenäosus")


class AnalysisResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_id: str
    timestamp: datetime
    input_point_lest97: CoordinateLEST97
    snapped_point_lest97: CoordinateLEST97
    snap_distance_m: float
    river: RiverInfo
    catchment: CatchmentInfo
    landcover: LandCoverBreakdown
    hommik: HommikResult
    catchment_geojson: dict | None = Field(None, description="GeoJSON Polygon in WGS84 for map display")
    dataset_versions: list[DatasetVersion]
    warnings: list[str] = Field(default_factory=list)
