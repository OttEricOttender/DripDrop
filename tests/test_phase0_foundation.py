"""Phase 0 baseline tests.

These tests pin down two things:

1.  The new FastAPI scaffold boots and serves ``/healthz``. This proves
    the migration foundation works before any business logic is added.

2.  The legacy ``scripts/calculations.py`` cannot be imported because of
    the module-level ``None`` arithmetic on lines 26 and 56. This is the
    bug Phase 1 must remove. By asserting the import error here we lock
    in the "before" state — the test will start failing the moment Phase
    1 lands, signalling that we should switch this test to assert the
    new behaviour.

Together these two tests are the regression target for the migration.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app

REPO_ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# 1) FastAPI scaffold boots
# ---------------------------------------------------------------------------


def test_fastapi_app_boots_and_healthz_returns_ok() -> None:
    client = TestClient(create_app())
    response = client.get("/healthz")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "version" in body
    assert "formula_revision" in body
    # q_bar_k cartogram raster has not been provided yet — we must surface that.
    assert body["q_bar_k_source"] == "placeholder"


def test_healthz_reports_formula_revision_matches_settings() -> None:
    from backend.config import get_settings

    client = TestClient(create_app())
    body = client.get("/healthz").json()
    assert body["formula_revision"] == get_settings().hommik_formula_revision


# ---------------------------------------------------------------------------
# 2) Legacy calculations.py is broken (locks in current state)
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Phase 0 baseline: scripts/calculations.py runs `None * 0.95` at module "
        "level. This test is expected to fail until Phase 1 rewrites the module "
        "into pure functions. When Phase 1 lands, remove the xfail and replace "
        "this with positive assertions against backend.services.hommik."
    ),
)
def test_legacy_calculations_module_is_importable() -> None:
    # Ensure we test a fresh import.
    sys.modules.pop("scripts.calculations", None)
    scripts_path = str(REPO_ROOT / "scripts")
    if scripts_path not in sys.path:
        sys.path.insert(0, scripts_path)
    importlib.import_module("calculations")


def test_legacy_calculations_has_known_bugs_documented() -> None:
    """Document the specific defects we will fix in Phase 1.

    This is a meta-test: it doesn't execute the buggy code, it just
    verifies that the file still contains the lines we plan to fix, so
    no one silently fixes them without coordinating with Phase 1.
    """
    source = (REPO_ROOT / "scripts" / "calculations.py").read_text(encoding="utf-8")
    # Bug 1: q95 = kesk_min_aravool * 0.95 (should be sampled from cartogram raster)
    assert "kesk_min_aravool * 0.95" in source, (
        "Expected bug `q95 = kesk_min_aravool * 0.95` is no longer present. "
        "If you fixed it, please update tests/test_phase0_foundation.py and "
        "the Phase 1 plan."
    )
    # Bug 2: module-level arithmetic on None
    assert "a = Ams + Akm" in source, (
        "Expected module-level `a = Ams + Akm` on None values is no longer present."
    )
    # Bug 3: `a` is incorrectly defined as Ams + Akm rather than wet-mineral B + Akm.
    # The fix lives in Phase 1 (see backend/services/hommik.py).
