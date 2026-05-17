"""Pytest configuration and shared fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--integration",
        action="store_true",
        default=False,
        help="Run integration tests that download real datasets (~1 min each)",
    )


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    if not config.getoption("--integration"):
        skip = pytest.mark.skip(reason="Pass --integration to run")
        for item in items:
            if "integration" in item.keywords:
                item.add_marker(skip)


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture(scope="session")
def fixtures_dir(repo_root: Path) -> Path:
    """Directory for test fixtures (small synthetic GeoTIFFs, sample GeoJSON)."""
    d = repo_root / "tests" / "fixtures"
    d.mkdir(parents=True, exist_ok=True)
    return d
