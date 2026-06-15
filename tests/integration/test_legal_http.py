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



# ===== merged from test_legal_extra.py =====
import httpx
import pytest

from modules.legal import analyze_legal


@pytest.mark.asyncio
async def test_legal_tos_footer_fallback(respx_mock) -> None:
    """
    All ToS paths 404, but homepage footer has a /user-terms link →
    ToS found via footer fallback.
    NOTE: Register specific sub-paths BEFORE the base URL to prevent
    respx from greedily matching them to the base route.
    """
    # Register specific paths first (most-specific first)
    respx_mock.get("https://example.com/robots.txt").mock(
        return_value=httpx.Response(404, text="Not Found")
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

    tos_html = "<html><body>" + "Terms of service. Automated scraping is prohibited. " * 30 + "</body></html>"
    respx_mock.get("https://example.com/user-terms").mock(
        return_value=httpx.Response(200, text=tos_html)
    )

    # Register base URL last to avoid it capturing sub-paths
    home_html = (
        '<html><body>'
        '<footer><a href="/user-terms">Terms of Service</a></footer>'
        '</body></html>'
    )
    respx_mock.get("https://example.com").mock(
        return_value=httpx.Response(200, text=home_html)
    )

    result = await analyze_legal("https://example.com/", 15.0)

    assert result.tos.found is True


@pytest.mark.asyncio
async def test_legal_tos_risk_high(respx_mock) -> None:
    """ToS with 2+ keywords → risk=HIGH."""
    robots_text = "User-agent: *\nAllow: /\n"
    respx_mock.get("https://example.com/robots.txt").mock(
        return_value=httpx.Response(200, text=robots_text)
    )
    respx_mock.get("https://example.com/sitemap.xml").mock(
        return_value=httpx.Response(404, text="Not Found")
    )
    respx_mock.get("https://example.com/sitemap_index.xml").mock(
        return_value=httpx.Response(404, text="Not Found")
    )

    # ToS with 2+ flagged keywords
    tos_content = ("This site prohibits scraping, crawling, and automated bots. "
                   "Commercial use is prohibited. Data extraction is not allowed. " * 20)
    respx_mock.get("https://example.com/terms").mock(
        return_value=httpx.Response(200, text=f"<html><body>{tos_content}</body></html>")
    )
    for path in ["/tos", "/legal", "/terms-of-service", "/privacy"]:
        respx_mock.get(f"https://example.com{path}").mock(
            return_value=httpx.Response(404, text="Not Found")
        )

    result = await analyze_legal("https://example.com/", 15.0)

    assert result.tos.risk_level == "HIGH"
    assert len(result.tos.flagged_keywords) >= 2


@pytest.mark.asyncio
async def test_legal_tos_risk_medium_one_keyword(respx_mock) -> None:
    """ToS with exactly 1 keyword → risk=MEDIUM."""
    robots_text = "User-agent: *\nAllow: /\n"
    respx_mock.get("https://example.com/robots.txt").mock(
        return_value=httpx.Response(200, text=robots_text)
    )
    respx_mock.get("https://example.com/sitemap.xml").mock(
        return_value=httpx.Response(404, text="Not Found")
    )
    respx_mock.get("https://example.com/sitemap_index.xml").mock(
        return_value=httpx.Response(404, text="Not Found")
    )

    tos_content = ("This is a simple legal page. Scraping is not allowed. "
                   "Please contact us for licensing. " * 20)
    respx_mock.get("https://example.com/terms").mock(
        return_value=httpx.Response(200, text=f"<html><body>{tos_content}</body></html>")
    )
    for path in ["/tos", "/legal", "/terms-of-service", "/privacy"]:
        respx_mock.get(f"https://example.com{path}").mock(
            return_value=httpx.Response(404, text="Not Found")
        )

    result = await analyze_legal("https://example.com/", 15.0)

    assert result.tos.risk_level == "MEDIUM"


@pytest.mark.asyncio
async def test_legal_tos_risk_low_no_keywords(respx_mock) -> None:
    """ToS found but no flagged keywords → risk=LOW."""
    robots_text = "User-agent: *\nAllow: /\n"
    respx_mock.get("https://example.com/robots.txt").mock(
        return_value=httpx.Response(200, text=robots_text)
    )
    respx_mock.get("https://example.com/sitemap.xml").mock(
        return_value=httpx.Response(404, text="Not Found")
    )
    respx_mock.get("https://example.com/sitemap_index.xml").mock(
        return_value=httpx.Response(404, text="Not Found")
    )

    tos_content = ("Welcome to our site. We value your privacy and your experience. "
                   "Please read these terms carefully before using our services. " * 20)
    respx_mock.get("https://example.com/terms").mock(
        return_value=httpx.Response(200, text=f"<html><body>{tos_content}</body></html>")
    )
    for path in ["/tos", "/legal", "/terms-of-service", "/privacy"]:
        respx_mock.get(f"https://example.com{path}").mock(
            return_value=httpx.Response(404, text="Not Found")
        )

    result = await analyze_legal("https://example.com/", 15.0)

    assert result.tos.risk_level == "LOW"
    assert result.tos.flagged_keywords == []


@pytest.mark.asyncio
async def test_legal_risk_medium_robots_disallows(respx_mock) -> None:
    """No ToS found + robots.txt disallows target path → risk=MEDIUM."""
    robots_text = "User-agent: *\nDisallow: /\n"
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

    assert result.tos.found is False
    assert result.tos.risk_level == "MEDIUM"


@pytest.mark.asyncio
async def test_legal_sitemap_index(respx_mock) -> None:
    """sitemap_index.xml returns sitemapindex XML → type='sitemapindex'."""
    robots_text = "User-agent: *\nAllow: /\n"
    respx_mock.get("https://example.com/robots.txt").mock(
        return_value=httpx.Response(200, text=robots_text)
    )
    respx_mock.get("https://example.com/sitemap.xml").mock(
        return_value=httpx.Response(404, text="Not Found")
    )
    sitemap_index_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        '<sitemap><loc>https://example.com/sitemap-1.xml</loc></sitemap>'
        '<sitemap><loc>https://example.com/sitemap-2.xml</loc></sitemap>'
        '</sitemapindex>'
    )
    respx_mock.get("https://example.com/sitemap_index.xml").mock(
        return_value=httpx.Response(200, text=sitemap_index_xml)
    )
    for path in ["/terms", "/tos", "/legal", "/terms-of-service", "/privacy"]:
        respx_mock.get(f"https://example.com{path}").mock(
            return_value=httpx.Response(404, text="Not Found")
        )
    respx_mock.get("https://example.com").mock(
        return_value=httpx.Response(200, text="<html><body></body></html>")
    )

    result = await analyze_legal("https://example.com/", 15.0)

    assert result.sitemap.found is True
    assert result.sitemap.type == "sitemapindex"
    assert result.sitemap.url_count == 2


@pytest.mark.asyncio
async def test_legal_sitemap_with_lastmod(respx_mock) -> None:
    """sitemap.xml with lastmod → last_modified populated."""
    robots_text = "User-agent: *\nAllow: /\n"
    respx_mock.get("https://example.com/robots.txt").mock(
        return_value=httpx.Response(200, text=robots_text)
    )
    sitemap_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        '<url><loc>https://example.com/</loc><lastmod>2026-01-01</lastmod></url>'
        '</urlset>'
    )
    respx_mock.get("https://example.com/sitemap.xml").mock(
        return_value=httpx.Response(200, text=sitemap_xml)
    )
    for path in ["/terms", "/tos", "/legal", "/terms-of-service", "/privacy"]:
        respx_mock.get(f"https://example.com{path}").mock(
            return_value=httpx.Response(404, text="Not Found")
        )
    respx_mock.get("https://example.com").mock(
        return_value=httpx.Response(200, text="<html><body></body></html>")
    )

    result = await analyze_legal("https://example.com/", 15.0)

    assert result.sitemap.found is True
    assert result.sitemap.last_modified == "2026-01-01"
