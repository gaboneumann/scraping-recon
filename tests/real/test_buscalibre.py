"""
tests/real/test_buscalibre.py
Integration test against https://www.buscalibre.cl/libros/computacion.

Runs the full CLI pipeline and asserts on stable signals. Volatile fields
(timestamp, duration, DNS, endpoint lists) are intentionally excluded.

Requires network. Run with: make test-real
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

URL = "https://www.buscalibre.cl/libros/computacion"
VENV_PYTHON = sys.executable
MAIN = Path(__file__).parents[2] / "main.py"


@pytest.fixture(scope="module")
def scan() -> dict:
    """Run one full scan and share result across all tests in this module."""
    result = subprocess.run(
        [str(VENV_PYTHON), str(MAIN), "--url", URL, "--json"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, f"Scan failed:\n{result.stderr}"
    data = json.loads(result.stdout)

    # Detect AWS ELB challenge page: site is rate-limiting this IP.
    # Signals: content_ratio=0.0 + internal_link_count=0 + cache-control=no-store
    clf = data.get("classifier") or {}
    if clf.get("content_ratio", 1.0) == 0.0 and clf.get("internal_link_count", 1) == 0:
        pytest.skip("Site returned a bot challenge page — rate limited. Retry later.")

    return data


@pytest.mark.real
class TestBuscalibreClassifier:
    def test_type_api_driven(self, scan: dict) -> None:
        assert scan["classifier"]["type"] == "API_DRIVEN"

    def test_cms_prestashop(self, scan: dict) -> None:
        assert scan["classifier"]["cms"] == "PrestaShop"

    def test_is_ecommerce(self, scan: dict) -> None:
        assert scan["classifier"]["ecommerce"]["is_ecommerce"] is True

    def test_ecommerce_platform(self, scan: dict) -> None:
        assert scan["classifier"]["ecommerce"]["platform"] == "PrestaShop"


@pytest.mark.real
class TestBuscalibrePagination:
    def test_type_query_param(self, scan: dict) -> None:
        assert scan["pagination"]["type"] == "QUERY_PARAM"

    def test_parameter_page(self, scan: dict) -> None:
        assert scan["pagination"]["parameter"] == "page"

    def test_no_js_required(self, scan: dict) -> None:
        assert scan["pagination"]["requires_js"] is False


@pytest.mark.real
class TestBuscalibreAuth:
    def test_no_auth_required(self, scan: dict) -> None:
        assert scan["auth"]["required"] is False

    def test_auth_type_none(self, scan: dict) -> None:
        assert scan["auth"]["type"] == "NONE"


@pytest.mark.real
class TestBuscalibreApiDetector:
    def test_internal_api_found(self, scan: dict) -> None:
        assert scan["api_detector"]["internal_api_found"] is True


@pytest.mark.real
class TestBuscalibreAntibot:
    def test_level_low_or_medium(self, scan: dict) -> None:
        assert scan["antibot"]["overall_level"] in {"LOW", "MEDIUM"}


@pytest.mark.real
class TestBuscalibreModulesStatus:
    def test_all_modules_ok(self, scan: dict) -> None:
        failed = [m for m in scan["modules_status"] if m["status"] != "OK"]
        assert failed == [], f"Modules failed: {failed}"
