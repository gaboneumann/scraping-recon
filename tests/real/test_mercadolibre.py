"""
tests/real/test_mercadolibre.py
Integration test against https://www.mercadolibre.cl/c/celulares-y-telefonia.

API-driven site with Cloudfront WAF and cookie consent wall.
Skip guard detects bot challenge pages (same pattern as buscalibre).

Run with: make test-real
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

URL = "https://www.mercadolibre.cl/c/celulares-y-telefonia#menu=categories"
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

    clf = data.get("classifier") or {}
    if clf.get("content_ratio", 1.0) == 0.0 and clf.get("internal_link_count", 1) == 0:
        pytest.skip("Site returned a bot challenge page — rate limited. Retry later.")

    return data


@pytest.mark.real
class TestMercadolibreClassifier:
    def test_type_api_driven(self, scan: dict) -> None:
        assert scan["classifier"]["type"] == "API_DRIVEN"

    def test_cdn_aws(self, scan: dict) -> None:
        assert scan["classifier"]["cdn"] == "AWS"

    def test_is_ecommerce_platform(self, scan: dict) -> None:
        assert scan["classifier"]["is_ecommerce_platform"] is True


@pytest.mark.real
class TestMercadolibreAuth:
    def test_no_auth_required(self, scan: dict) -> None:
        assert scan["auth"]["required"] is False

    def test_cookie_consent_blocking(self, scan: dict) -> None:
        assert scan["auth"]["cookie_consent_blocking"] is True


@pytest.mark.real
class TestMercadolibreAntibot:
    def test_level_low_or_medium(self, scan: dict) -> None:
        assert scan["antibot"]["overall_level"] in {"LOW", "MEDIUM"}

    def test_waf_cloudfront(self, scan: dict) -> None:
        assert scan["antibot"]["dimensions"]["waf"]["vendor"] == "Cloudfront"


@pytest.mark.real
class TestMercadolibreLegal:
    def test_robots_txt_found(self, scan: dict) -> None:
        assert scan["legal"]["robots_txt"]["found"] is True

    def test_crawl_delay(self, scan: dict) -> None:
        assert scan["legal"]["robots_txt"]["crawl_delay_seconds"] == 5


@pytest.mark.real
class TestMercadolibreApiDetector:
    def test_internal_api_found(self, scan: dict) -> None:
        assert scan["api_detector"]["internal_api_found"] is True


@pytest.mark.real
class TestMercadolibreModulesStatus:
    def test_all_modules_ok(self, scan: dict) -> None:
        failed = [m for m in scan["modules_status"] if m["status"] != "OK"]
        assert failed == [], f"Modules failed: {failed}"
