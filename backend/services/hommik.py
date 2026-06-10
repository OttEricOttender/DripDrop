"""Karl Hommik design drainage calculator.

This is the scientific heart of HydroCalc. Every formula here is taken
**verbatim** from ``TÜ_projekt_protsess.pdf`` (the customer-provided
reference document, retrieved 2026-05-12, page references in each
docstring). Do not modify constants without a documented sign-off from
the customer — the ``formula_revision`` constant in
``backend.config`` must be bumped on any change so that historical PDF
reports remain replayable.

Symbol map (Estonian → ASCII used in code):

==============  ===================================================
PDF symbol      Code identifier
==============  ===================================================
q̄              q_bar           — äravoolunorm           l/(s·km²)
q̄_k            q_bar_k         — aasta klimaatiline    l/(s·km²)
Δq              delta_q         — kohalik parand        l/(s·km²)
q_95%           q95             — 95% min äravoolumoodul l/(s·km²)
k_95%           k95             — päevakeskmine kordaja  (dimensionless)
r_s             r_s             — sügisene parameeter   (dimensionless)
r               r               — kevadine parameeter   (dimensionless)
q_veg.max.p%    q_veg_max       — sügisene tippmoodul    l/(s·km²)
q_kev.maks.p%   q_kev_max       — kevadine tippmoodul    l/(s·km²)
Q_%             Q               — vooluhulk             l/s (×0.001 = m³/s)
A               A               — valgala pindala        km²
p               p               — ületõusutõenäosus      %
A_ms, A_r, A_km, B, C           — land-cover shares      % of A
a               a               — wet-mineral B share + A_km  %
==============  ===================================================

Logarithm convention: the PDF writes ``log(p+1)``. The legacy team's
implementation used ``log10``, which is the standard convention in
Estonian/Soviet empirical hydrology (Pol'akov, Sokolovskij). We keep
that convention here. This decision is logged as an assumption in the
PDF report footer; if the customer wants ``ln`` instead, change one
constant in this file and bump ``formula_revision``.
"""

from __future__ import annotations

import logging
import math
from typing import Literal

logger = logging.getLogger(__name__)

from backend.models.schemas import (
    HommikInputs,
    HommikResult,
    LandCoverBreakdown,
)

# ---------------------------------------------------------------------------
# Constraints from the PDF (page 5):
#   "kui valgala pindala A < 100 km², siis tuleb valgala pindala võrdsustada
#    100 km² ning arvutusvooluhulk määrata 10% ületõusutõenäosusega"
# ---------------------------------------------------------------------------
MIN_AREA_KM2: float = 100.0
DEFAULT_P_PERCENT_WHEN_FLOORED: float = 10.0


# ---------------------------------------------------------------------------
# Atomic formula functions
# ---------------------------------------------------------------------------


def delta_q(a_percent: float, q95: float) -> float:
    """Local correction Δq — formula (1.2).

    Δq = 0.020·a + 0.30·q_95% − 1.00

    Args:
        a_percent: share (%) of wet-mineral B (võsastunud/metsastunud
            liigniiske mineraalmaa) plus A_km (intensively drained
            low-bog). Derived in ``backend.services.landcover`` per the
            documented mapping; see ``LandCoverBreakdown.a_wet_mineral_plus_akm``.
        q95: 95%-probability minimum average annual drainage modulus from
            the cartogram, in l/(s·km²).

    Returns:
        Δq in l/(s·km²). May be negative for catchments dominated by
        forest/open-mineral land.
    """
    return 0.020 * a_percent + 0.30 * q95 - 1.00


def q_bar(q_bar_k: float, delta_q_value: float) -> float:
    """Annual drainage norm q̄ — formula (1.1).

    q̄ = q̄_k + Δq

    Args:
        q_bar_k: annual climatic drainage norm from the cartogram, l/(s·km²).
        delta_q_value: result of :func:`delta_q`.

    Returns:
        q̄ in l/(s·km²).

    Raises:
        ValueError: if the result is non-positive (would imply negative
            mean annual runoff, which is unphysical for Estonian rivers).
    """
    value = q_bar_k + delta_q_value
    if value <= 0:
        raise ValueError(
            f"q_bar (äravoolunorm) computed as {value:.4f} l/(s·km²); "
            "must be positive. Check that q_bar_k and the land-cover-derived "
            "`a` parameter are sensible for this catchment."
        )
    return value


def k95(q95: float, q_bar_value: float) -> float:
    """Daily-mean drainage modular coefficient k_95% — formula (1.4).

    k_95% = q_95% / q̄
    """
    if q_bar_value <= 0:
        raise ValueError("q_bar must be positive to compute k95.")
    return q95 / q_bar_value


def r_s(
    A_ms: float,
    A_r: float,
    A_km: float,
    B: float,
    C: float,
) -> float:
    """Autumn peak-flow parameter r_s — formula (1.5).

    r_s = 0.005·(A_ms + A_r − 0.2·A_km − 0.1·B − 0.6·C) − 0.02

    All arguments are percentages of catchment area (0–100).
    """
    return 0.005 * (A_ms + A_r - 0.2 * A_km - 0.1 * B - 0.6 * C) - 0.02


def r(
    A_ms: float,
    A_r: float,
    A_km: float,
    B: float,
    C: float,
) -> float:
    """Spring peak-flow parameter r — formula (1.7).

    r = 0.004·[A_ms + 0.4·(A_r + A_km) + B + 0.2·C] − 0.20
    """
    return 0.004 * (A_ms + 0.4 * (A_r + A_km) + B + 0.2 * C) - 0.20


def q_veg_max(
    q_bar_value: float,
    p_percent: float,
    A_km2: float,
    k95_value: float,
    r_s_value: float,
) -> float:
    """Autumn (vegetation-period) peak drainage modulus — formula (1.3).

    q_veg.max.p% = q̄ · [ (26 − 11.5·log10(p+1)) / (A+1)^0.11 ]^(1 − k_95% − r_s)
    """
    bracket = (26 - 11.5 * math.log10(p_percent + 1)) / (A_km2 + 1) ** 0.11
    exponent = 1 - k95_value - r_s_value
    return q_bar_value * (bracket ** exponent)


def q_kev_max(
    q_bar_value: float,
    p_percent: float,
    A_km2: float,
    k95_value: float,
    r_value: float,
) -> float:
    """Spring peak drainage modulus — formula (1.6).

    q_kev.maks.p% = q̄ · [ (112 − 52·log10(p+1)) / (A+1)^0.14 ]^(1 − k_95% − r)
    """
    bracket = (112 - 52 * math.log10(p_percent + 1)) / (A_km2 + 1) ** 0.14
    exponent = 1 - k95_value - r_value
    return q_bar_value * (bracket ** exponent)


def Q_from_modulus(q_modulus_l_per_s_km2: float, A_km2: float) -> float:
    """Convert a modulus to a flow rate — formula (1.8).

    Q_% = q_% · A,  with units l/s when q is l/(s·km²) and A is km².
    The caller divides by 1000 to express in m³/s for the report.
    """
    return q_modulus_l_per_s_km2 * A_km2


# ---------------------------------------------------------------------------
# Orchestrator — applies the < 100 km² floor and assembles the HommikResult
# ---------------------------------------------------------------------------


def compute(
    inputs: HommikInputs,
    *,
    formula_revision: str,
    q_bar_k_source: Literal["raster", "placeholder"],
) -> HommikResult:
    """Run the full Karl Hommik pipeline.

    Implements the page-5 PDF constraint: when A < 100 km², use 100 km²
    in the formulas and force p = 10 %. The original area is preserved
    only on the request side; calculations downstream use the floored A.

    Args:
        inputs: validated :class:`HommikInputs`.
        formula_revision: identifier embedded in the result for audit
            (passed in so tests don't have to import config).
        q_bar_k_source: ``"raster"`` once the cartogram is wired up,
            ``"placeholder"`` until then. Surfaced in the result for
            legal defensibility — placeholder reports are watermarked.

    Returns:
        A fully populated :class:`HommikResult`.
    """
    # --- Apply the A < 100 km² floor (PDF page 5) --------------------------
    if inputs.A_km2 < MIN_AREA_KM2:
        A_effective = MIN_AREA_KM2
        p_effective = DEFAULT_P_PERCENT_WHEN_FLOORED
        floored = True
    else:
        A_effective = inputs.A_km2
        p_effective = inputs.p_percent
        floored = False

    lc: LandCoverBreakdown = inputs.landcover

    # --- Atomic formulas, in PDF order ------------------------------------
    dq = delta_q(a_percent=lc.a_wet_mineral_plus_akm, q95=inputs.q95_l_per_s_km2)
    qbar = q_bar(q_bar_k=inputs.q_bar_k_l_per_s_km2, delta_q_value=dq)
    k_value = k95(q95=inputs.q95_l_per_s_km2, q_bar_value=qbar)
    rs_value = r_s(A_ms=lc.A_ms, A_r=lc.A_r, A_km=lc.A_km, B=lc.B, C=lc.C)
    r_value = r(A_ms=lc.A_ms, A_r=lc.A_r, A_km=lc.A_km, B=lc.B, C=lc.C)

    if k_value + rs_value > 1.0:
        logger.warning(
            "k95 + r_s = %.3f > 1 (k95=%.3f, r_s=%.3f); "
            "exponent is negative — result may be unrealistically large.",
            k_value + rs_value, k_value, rs_value,
        )

    q_veg = q_veg_max(qbar, p_effective, A_effective, k_value, rs_value)
    q_kev = q_kev_max(qbar, p_effective, A_effective, k_value, r_value)

    # Modulus is l/(s·km²); flow Q is l/s when multiplied by A in km²;
    # divide by 1000 to express m³/s for the engineering report.
    Q_veg = Q_from_modulus(q_veg, A_effective) / 1000.0
    Q_kev = Q_from_modulus(q_kev, A_effective) / 1000.0

    return HommikResult(
        q_bar_l_per_s_km2=qbar,
        delta_q_l_per_s_km2=dq,
        k95=k_value,
        r_s=rs_value,
        r=r_value,
        q_veg_max_l_per_s_km2=q_veg,
        q_kev_max_l_per_s_km2=q_kev,
        Q_veg_max_m3_per_s=Q_veg,
        Q_kev_max_m3_per_s=Q_kev,
        formula_revision=formula_revision,
        area_floored_to_100km2=floored,
        q_bar_k_source=q_bar_k_source,
    )
