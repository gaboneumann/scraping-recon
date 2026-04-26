"""
tests/integration/test_legal_http.py
Integration tests for modules/legal.py using respx HTTP mocking.
"""
from pathlib import Path

import httpx
import pytest

from modules.legal import analyze_legal

FIXTURES_ROBOTS = Path(__file__).parent.parent / "fixtures" / "robots"
FIXTURES_SITEMAPS = Path(__file__).parent.parent / "fixtures" / "sitemaps"


@pytest.mark.asyncio
async def test_legal_happy_path(respx_mock):
    """robots.txt found + sitemap.xml found → both True."""
    robots_content = (FIXTURES_ROBOTS / "allow_all.txt").read_text()
    sitemap_content = (FIXTURES_SITEMAPS / "standard.xml").read_text()

    # robots.txt — same for all UAs (respx matches any request to this URL)
    respx_mock.get("https://example.com/robots.txt").mock(
        return_value=httpx.Response(200, text=robots_content)
    )
    # sitemap.xml → 200
    respx_mock.get("https://example.com/sitemap.xml").mock(
        return_value=httpx.Response(200, text=sitemap_content)
    )
    # ToS paths → first one hits /terms with a long enough response
    tos_html = "<html><body>" + "Terms of Service. " * 50 + "</body></html>"
    respx_mock.get("https://example.com/terms").mock(
        return_value=httpx.Response(200, text=tos_html)
    )
    # Remaining TOS paths (in case /terms doesn't match first)
    for path in ["/tos", "/legal", "/terms-of-service", "/privacy"]:
        respx_mock.get(f"https://example.com{path}").mock(
            return_value=httpx.Response(404, text="Not Found")
        )

    result = await analyze_legal("https://example.com/", 15.0)

    assert result.robots_txt.found is True
    assert result.sitemap.found is True
    assert result.tos.found is True


@pytest.mark.asyncio
async def test_legal_not_found(respx_mock):
    """All resources 404 → robots_txt.found == False, sitemap.found == False."""
    # robots.txt — 404 for all UAs
    respx_mock.get("https://example.com/robots.txt").mock(
        return_value=httpx.Response(404, text="Not Found")
    )
    # sitemap paths → 404
    respx_mock.get("https://example.com/sitemap.xml").mock(
        return_value=httpx.Response(404, text="Not Found")
    )
    respx_mock.get("https://example.com/sitemap_index.xml").mock(
        return_value=httpx.Response(404, text="Not Found")
    )
    # ToS paths → 404
    for path in ["/terms", "/tos", "/legal", "/terms-of-service", "/privacy"]:
        respx_mock.get(f"https://example.com{path}").mock(
            return_value=httpx.Response(404, text="Not Found")
        )
    # Homepage fallback for footer ToS link scanning
    respx_mock.get("https://example.com").mock(
        return_value=httpx.Response(200, text="<html><body>Nothing here</body></html>")
    )

    result = await analyze_legal("https://example.com/", 15.0)

    assert result.robots_txt.found is False
    assert result.sitemap.found is False
    assert result.tos.found is False


@pytest.mark.asyncio
async def test_legal_robots_with_disallow(respx_mock):
    """robots.txt with Disallow → blocked_paths populated."""
    robots_text = "User-agent: *\nDisallow: /admin\nDisallow: /private\n"

    respx_mock.get("https://example.com/robots.txt").mock(
        return_value=httpx.Response(200, text=robots_text)
    )
    respx_mock.get("https://example.com/sitemap.xml").mock(
        return_value=httpx.Response(404, text="Not Found")
    )
    respx_mock.get("https://example.com/sitemap_index.xml").mock(
        return_value=httpx.Response(404, text="Not Found")
    )
    for path in ["/terms", "/tos", "/legal", "/terms-of-service", "/privacy"]:
        respx_mock.get(f"https://example.com{path}").mock(
            return_value=httpx.Response(404, text="Not Found")
        )
    respx_mock.get("https://example.com").mock(
        return_value=httpx.Response(200, text="<html><body></body></html>")
    )

    result = await analyze_legal("https://example.com/", 15.0)

    assert result.robots_txt.found is True
    assert "/admin" in result.robots_txt.blocked_paths
    assert "/private" in result.robots_txt.blocked_paths
