"""Pytest configuration and shared fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture(scope="session")
def fixtures_dir(repo_root: Path) -> Path:
    """Directory for test fixtures (small synthetic GeoTIFFs, sample GeoJSON)."""
    d = repo_root / "tests" / "fixtures"
    d.mkdir(parents=True, exist_ok=True)
    return d
