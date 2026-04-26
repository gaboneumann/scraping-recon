"""
tests/integration/test_classifier_http.py
Integration tests for modules/classifier.py using respx HTTP mocking.
DNS and mobile-compare are patched to eliminate extra requests.
"""
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from modules.classifier import classify_page

FIXTURES = Path(__file__).parent.parent / "fixtures" / "html"


@pytest.mark.asyncio
async def test_classifier_static(respx_mock):
    """Static blog HTML → type=STATIC."""
    html = (FIXTURES / "static_blog.html").read_text()
    respx_mock.get(url__regex=r".*").mock(
        return_value=httpx.Response(200, text=html, headers={"content-type": "text/html"})
    )
    with (
        patch("modules.classifier._dns_lookup", return_value={}),
        patch(
            "modules.classifier.compare_mobile_desktop",
            new=AsyncMock(return_value={"content_differs": False, "mobile_html": "", "mobile_headers": {}}),
        ),
    ):
        result = await classify_page("https://example.com", 15.0)

    assert result.type == "STATIC"


@pytest.mark.asyncio
async def test_classifier_dynamic_nextjs(respx_mock):
    """Next.js SPA page → type DYNAMIC or HYBRID (JS framework detected)."""
    html = (FIXTURES / "nextjs_spa.html").read_text()
    respx_mock.get(url__regex=r".*").mock(
        return_value=httpx.Response(200, text=html, headers={"content-type": "text/html"})
    )
    with (
        patch("modules.classifier._dns_lookup", return_value={}),
        patch(
            "modules.classifier.compare_mobile_desktop",
            new=AsyncMock(return_value={"content_differs": False, "mobile_html": "", "mobile_headers": {}}),
        ),
    ):
        result = await classify_page("https://example.com", 15.0)

    assert result.type in ("DYNAMIC", "HYBRID", "API_DRIVEN")
    # NextJS should be detected
    assert "Next.js" in result.js_frameworks or "React" in result.js_frameworks


@pytest.mark.asyncio
async def test_classifier_api_driven(respx_mock):
    """React SPA with minimal HTML content → type API_DRIVEN or DYNAMIC."""
    html = (FIXTURES / "react_api_driven.html").read_text()
    respx_mock.get(url__regex=r".*").mock(
        return_value=httpx.Response(200, text=html, headers={"content-type": "text/html"})
    )
    with (
        patch("modules.classifier._dns_lookup", return_value={}),
        patch(
            "modules.classifier.compare_mobile_desktop",
            new=AsyncMock(return_value={"content_differs": False, "mobile_html": "", "mobile_headers": {}}),
        ),
    ):
        result = await classify_page("https://example.com", 15.0)

    # Very little HTML content → should not be STATIC
    assert result.type in ("API_DRIVEN", "DYNAMIC", "UNKNOWN")


@pytest.mark.asyncio
async def test_classifier_returns_all_fields(respx_mock):
    """ClassifierResult must have all required fields populated."""
    html = (FIXTURES / "static_blog.html").read_text()
    respx_mock.get(url__regex=r".*").mock(
        return_value=httpx.Response(
            200, text=html,
            headers={"content-type": "text/html", "server": "nginx"}
        )
    )
    with (
        patch("modules.classifier._dns_lookup", return_value={}),
        patch(
            "modules.classifier.compare_mobile_desktop",
            new=AsyncMock(return_value={"content_differs": False, "mobile_html": "", "mobile_headers": {}}),
        ),
    ):
        result = await classify_page("https://example.com", 15.0)

    assert result.type is not None
    assert result.confidence is not None
    assert isinstance(result.js_frameworks, list)
    assert isinstance(result.content_ratio, float)
    assert isinstance(result.response_time_ms, int)
    assert result.ecommerce is not None
