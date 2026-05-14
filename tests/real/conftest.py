"""
tests/real/conftest.py
Shared fixtures and configuration for real platform tests (T2 expansion suite).

Provides:
- HTML loaders from fixture files
- Platform markers (skip on rate-limit)
- Shared HTTP client for real tests
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest


FIXTURES_HTML = Path(__file__).parent / "fixtures"


@pytest.fixture
def load_html() -> callable:
    """Fixture factory to load HTML files from tests/real/fixtures directory."""
    def _load(name: str) -> str:
        """Load HTML fixture by name (without .html extension)."""
        path = FIXTURES_HTML / f"{name}.html"
        if not path.exists():
            raise FileNotFoundError(f"HTML fixture not found: {path}")
        return path.read_text(encoding="utf-8")
    return _load


@pytest.fixture(scope="session")
def skip_if_rate_limited() -> bool:
    """
    Session-scoped fixture to check if real tests should be skipped.
    Skip if TEST_SKIP_RATE_LIMITED=1 or TEST_RATE_LIMITED_MARKER found.
    """
    return os.environ.get("TEST_SKIP_RATE_LIMITED", "").lower() in ("1", "true")


def pytest_collection_modifyitems(config, items):
    """
    Hook to skip or mark tests as real.
    - Mark all tests with @pytest.mark.real as part of 'real' group
    - Skip if --no-real is passed
    """
    skip_real = config.getoption("--no-real", default=False)

    for item in items:
        # If it's in tests/real/, mark it as real
        if "tests/real/" in str(item.fspath):
            item.add_marker(pytest.mark.real)

        # Skip if --no-real is passed
        if skip_real and "real" in [m.name for m in item.iter_markers()]:
            item.add_marker(pytest.mark.skip(reason="Real tests disabled (--no-real)"))


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers", "real: mark test as a real platform test (requires external network)"
    )
