"""
tests/real/test_books_toscrape.py
Integration test against http://books.toscrape.com.

Static baseline site — designed for scraping, no antibot, no rate limiting.
These tests should always run (no skip guard needed).

Run with: make test-real
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

URL = "http://books.toscrape.com"
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
    return json.loads(result.stdout)


@pytest.mark.real
class TestBooksToscrapeClassifier:
    def test_type_static(self, scan: dict) -> None:
        assert scan["classifier"]["type"] == "STATIC"

    def test_confidence_high(self, scan: dict) -> None:
        assert scan["classifier"]["confidence"] == "HIGH"

    def test_is_ecommerce(self, scan: dict) -> None:
        assert scan["classifier"]["ecommerce"]["is_ecommerce"] is True

    def test_no_js_frameworks(self, scan: dict) -> None:
        assert scan["classifier"]["js_frameworks"] == []


@pytest.mark.real
class TestBooksToscrapeAuth:
    def test_no_auth_required(self, scan: dict) -> None:
        assert scan["auth"]["required"] is False

    def test_auth_type_none(self, scan: dict) -> None:
        assert scan["auth"]["type"] == "NONE"

    def test_no_cookie_consent(self, scan: dict) -> None:
        assert scan["auth"]["cookie_consent_blocking"] is False


@pytest.mark.real
class TestBooksToscrapeApiDetector:
    def test_no_internal_api(self, scan: dict) -> None:
        assert scan["api_detector"]["internal_api_found"] is False

    def test_no_endpoints(self, scan: dict) -> None:
        assert scan["api_detector"]["endpoints"] == []


@pytest.mark.real
class TestBooksToscrapeAntibot:
    def test_level_none(self, scan: dict) -> None:
        assert scan["antibot"]["overall_level"] == "NONE"

    def test_score_zero(self, scan: dict) -> None:
        assert scan["antibot"]["overall_score"] == 0.0

    def test_no_waf(self, scan: dict) -> None:
        assert scan["antibot"]["dimensions"]["waf"]["vendor"] is None


@pytest.mark.real
class TestBooksToscrapeModulesStatus:
    def test_all_modules_ok(self, scan: dict) -> None:
        failed = [m for m in scan["modules_status"] if m["status"] != "OK"]
        assert failed == [], f"Modules failed: {failed}"
