"""Karl Hommik calculator tests — Phase 1.

These tests are the scientific contract. Every formula has both an
atomic test (single function, single input) and an integration test
(``hommik.compute`` end-to-end with a hand-derived worked example).

If you change any formula constant in ``backend/services/hommik.py``,
these tests must fail. If they don't, the bump was untested.
"""

from __future__ import annotations

import math

import pytest
from pydantic import ValidationError

from backend.models.schemas import HommikInputs, LandCoverBreakdown
from backend.services import hommik

FORMULA_REVISION = "test-rev-1"


# ---------------------------------------------------------------------------
# Atomic formula tests — exercise each function in PDF order
# ---------------------------------------------------------------------------


class TestDeltaQ:
    """Formula (1.2): Δq = 0.020·a + 0.30·q_95% − 1.00"""

    def test_zero_inputs(self):
        # 0.020·0 + 0.30·0 − 1.00 = −1.00
        assert hommik.delta_q(a_percent=0, q95=0) == pytest.approx(-1.00)

    def test_hand_computed(self):
        # 0.020·20 + 0.30·2.0 − 1.00 = 0.4 + 0.6 − 1.0 = 0.0
        assert hommik.delta_q(a_percent=20.0, q95=2.0) == pytest.approx(0.0)

    def test_typical_estonian_inputs(self):
        # a=15, q95=3 → 0.30 + 0.90 − 1.00 = 0.20
        assert hommik.delta_q(a_percent=15.0, q95=3.0) == pytest.approx(0.20)


class TestQBar:
    """Formula (1.1): q̄ = q̄_k + Δq"""

    def test_simple_sum(self):
        assert hommik.q_bar(q_bar_k=7.0, delta_q_value=0.0) == pytest.approx(7.0)

    def test_with_negative_correction(self):
        assert hommik.q_bar(q_bar_k=7.0, delta_q_value=-1.5) == pytest.approx(5.5)

    def test_rejects_non_positive_result(self):
        # If somehow q_bar_k + delta_q ≤ 0, that's unphysical for Estonia
        with pytest.raises(ValueError, match="must be positive"):
            hommik.q_bar(q_bar_k=1.0, delta_q_value=-1.0)


class TestK95:
    """Formula (1.4): k_95% = q_95% / q̄"""

    def test_ratio(self):
        assert hommik.k95(q95=2.0, q_bar_value=7.0) == pytest.approx(2.0 / 7.0)

    def test_rejects_zero_denominator(self):
        with pytest.raises(ValueError):
            hommik.k95(q95=2.0, q_bar_value=0.0)


class TestRs:
    """Formula (1.5): r_s = 0.005·(A_ms + A_r − 0.2·A_km − 0.1·B − 0.6·C) − 0.02"""

    def test_hand_computed(self):
        # 0.005·(10 + 5 − 0.2·15 − 0.1·30 − 0.6·40) − 0.02
        # = 0.005·(10 + 5 − 3 − 3 − 24) − 0.02
        # = 0.005·(−15) − 0.02
        # = −0.075 − 0.02 = −0.095
        result = hommik.r_s(A_ms=10, A_r=5, A_km=15, B=30, C=40)
        assert result == pytest.approx(-0.095)

    def test_all_zero(self):
        # 0.005·0 − 0.02 = −0.02
        assert hommik.r_s(0, 0, 0, 0, 0) == pytest.approx(-0.02)


class TestR:
    """Formula (1.7): r = 0.004·[A_ms + 0.4·(A_r+A_km) + B + 0.2·C] − 0.20"""

    def test_hand_computed(self):
        # 0.004·[10 + 0.4·(5+15) + 30 + 0.2·40] − 0.20
        # = 0.004·[10 + 8 + 30 + 8] − 0.20
        # = 0.004·56 − 0.20 = 0.224 − 0.20 = 0.024
        result = hommik.r(A_ms=10, A_r=5, A_km=15, B=30, C=40)
        assert result == pytest.approx(0.024)


class TestQVegMax:
    """Formula (1.3): q_veg.max = q̄·[(26−11.5·log(p+1))/(A+1)^0.11]^(1−k95−r_s)"""

    def test_against_hand_computation(self):
        # Inputs from the worked example below.
        # bracket = (26 − 11.5·log10(11)) / 101^0.11
        # = (26 − 11.5·1.0414) / 1.6618
        # = 14.024 / 1.6618 ≈ 8.4389
        # exponent = 1 − 0.2857 − (−0.095) = 0.8093
        # 8.4389^0.8093 ≈ 5.616
        # 7.0 · 5.616 ≈ 39.31
        result = hommik.q_veg_max(
            q_bar_value=7.0, p_percent=10, A_km2=100, k95_value=2.0 / 7.0, r_s_value=-0.095
        )
        assert result == pytest.approx(39.31, rel=1e-3)


class TestQKevMax:
    """Formula (1.6): q_kev.maks = q̄·[(112−52·log(p+1))/(A+1)^0.14]^(1−k95−r)"""

    def test_against_hand_computation(self):
        # bracket = (112 − 52·log10(11)) / 101^0.14
        # = (112 − 54.153) / 1.9079
        # = 57.847 / 1.9079 ≈ 30.32
        # exponent = 1 − 0.2857 − 0.024 = 0.6903
        # 30.32^0.6903 ≈ 10.53
        # 7.0 · 10.53 ≈ 73.74
        result = hommik.q_kev_max(
            q_bar_value=7.0, p_percent=10, A_km2=100, k95_value=2.0 / 7.0, r_value=0.024
        )
        assert result == pytest.approx(73.74, rel=1e-3)


class TestQFromModulus:
    def test_modulus_to_flow(self):
        # Q in l/s; caller divides by 1000 for m³/s
        assert hommik.Q_from_modulus(10.0, 100.0) == 1000.0


# ---------------------------------------------------------------------------
# End-to-end worked example
# ---------------------------------------------------------------------------


def _worked_example_inputs() -> HommikInputs:
    """Inputs that reproduce the by-hand worked example used throughout
    the atomic tests. A=100 km² is deliberately the boundary case so we
    also exercise the area-floor rule (no-op here, since A == 100).
    """
    return HommikInputs(
        A_km2=100.0,
        p_percent=10.0,
        q_bar_k_l_per_s_km2=7.0,
        q95_l_per_s_km2=2.0,
        landcover=LandCoverBreakdown(
            A_ms=10.0,
            A_r=5.0,
            A_km=15.0,
            B=30.0,
            C=40.0,
            maaparandus=20.0,
            a_wet_mineral_plus_akm=20.0,
        ),
    )


class TestComputeWorkedExample:
    """End-to-end check that the orchestrator produces the by-hand values.

    Hand-computation (all values rounded to 4 significant figures):
        Δq   = 0.020·20 + 0.30·2.0 − 1.00 = 0.000
        q̄   = 7.0 + 0.0 = 7.000
        k95  = 2.0 / 7.0 = 0.2857
        r_s  = −0.095
        r    = 0.024
        q_veg.max = 39.31 l/(s·km²)
        q_kev.maks = 73.74 l/(s·km²)
        Q_veg = 39.31 · 100 / 1000 = 3.931 m³/s
        Q_kev = 73.74 · 100 / 1000 = 7.374 m³/s
    """

    def test_matches_hand_computation(self):
        result = hommik.compute(
            inputs=_worked_example_inputs(),
            formula_revision=FORMULA_REVISION,
            q_bar_k_source="placeholder",
        )
        assert result.delta_q_l_per_s_km2 == pytest.approx(0.0, abs=1e-9)
        assert result.q_bar_l_per_s_km2 == pytest.approx(7.0)
        assert result.k95 == pytest.approx(2.0 / 7.0)
        assert result.r_s == pytest.approx(-0.095)
        assert result.r == pytest.approx(0.024)
        assert result.q_veg_max_l_per_s_km2 == pytest.approx(39.31, rel=1e-3)
        assert result.q_kev_max_l_per_s_km2 == pytest.approx(73.74, rel=1e-3)
        assert result.Q_veg_max_m3_per_s == pytest.approx(3.931, rel=1e-3)
        assert result.Q_kev_max_m3_per_s == pytest.approx(7.374, rel=1e-3)

    def test_provenance_fields(self):
        result = hommik.compute(
            inputs=_worked_example_inputs(),
            formula_revision=FORMULA_REVISION,
            q_bar_k_source="placeholder",
        )
        assert result.formula_revision == FORMULA_REVISION
        assert result.q_bar_k_source == "placeholder"
        assert result.area_floored_to_100km2 is False  # A == 100 exactly


# ---------------------------------------------------------------------------
# A < 100 km² floor rule (PDF page 5)
# ---------------------------------------------------------------------------


class TestAreaFloor:
    """If A < 100 km², the PDF mandates A := 100 and p := 10 %."""

    def test_floor_applied_for_small_catchment(self):
        small = _worked_example_inputs().model_copy(update={"A_km2": 50.0, "p_percent": 1.0})
        result = hommik.compute(
            inputs=small,
            formula_revision=FORMULA_REVISION,
            q_bar_k_source="placeholder",
        )
        # Flag must be set so the report can warn the engineer.
        assert result.area_floored_to_100km2 is True
        # Output should match the A=100, p=10 case (the worked example).
        expected = hommik.compute(
            inputs=_worked_example_inputs(),
            formula_revision=FORMULA_REVISION,
            q_bar_k_source="placeholder",
        )
        assert result.q_veg_max_l_per_s_km2 == pytest.approx(expected.q_veg_max_l_per_s_km2)
        assert result.q_kev_max_l_per_s_km2 == pytest.approx(expected.q_kev_max_l_per_s_km2)

    def test_floor_not_applied_for_large_catchment(self):
        big = _worked_example_inputs().model_copy(update={"A_km2": 500.0})
        result = hommik.compute(
            inputs=big,
            formula_revision=FORMULA_REVISION,
            q_bar_k_source="placeholder",
        )
        assert result.area_floored_to_100km2 is False


# ---------------------------------------------------------------------------
# Schema validation (Pydantic guards)
# ---------------------------------------------------------------------------


class TestSchemaValidation:
    def test_rejects_negative_area(self):
        with pytest.raises(ValidationError):
            HommikInputs(
                A_km2=-1.0,
                p_percent=10.0,
                q_bar_k_l_per_s_km2=7.0,
                q95_l_per_s_km2=2.0,
                landcover=_worked_example_inputs().landcover,
            )

    def test_rejects_out_of_range_landcover_percentage(self):
        with pytest.raises(ValidationError):
            LandCoverBreakdown(
                A_ms=-1, A_r=5, A_km=15, B=30, C=40, maaparandus=0, a_wet_mineral_plus_akm=0
            )


# ---------------------------------------------------------------------------
# Sanity ranges — orders of magnitude expected for Estonian catchments
# ---------------------------------------------------------------------------


class TestSanityRanges:
    """Spring peaks for typical Estonian catchments are typically larger
    than autumn peaks (snowmelt > vegetation-period rainfall events).
    This isn't a strict mathematical guarantee, but for our worked
    example the inequality should hold and any future regression that
    flips it is worth investigating.
    """

    def test_spring_peak_greater_than_autumn(self):
        result = hommik.compute(
            inputs=_worked_example_inputs(),
            formula_revision=FORMULA_REVISION,
            q_bar_k_source="placeholder",
        )
        assert result.q_kev_max_l_per_s_km2 > result.q_veg_max_l_per_s_km2

    def test_results_finite(self):
        result = hommik.compute(
            inputs=_worked_example_inputs(),
            formula_revision=FORMULA_REVISION,
            q_bar_k_source="placeholder",
        )
        for value in (
            result.delta_q_l_per_s_km2,
            result.q_bar_l_per_s_km2,
            result.k95,
            result.r_s,
            result.r,
            result.q_veg_max_l_per_s_km2,
            result.q_kev_max_l_per_s_km2,
            result.Q_veg_max_m3_per_s,
            result.Q_kev_max_m3_per_s,
        ):
            assert math.isfinite(value)
