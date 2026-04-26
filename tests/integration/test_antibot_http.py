"""
tests/integration/test_antibot_http.py
Integration tests for modules/antibot.py using respx HTTP mocking.
Requires mock_antibot_externals to suppress wafw00f subprocess and TLS test.
"""
from pathlib import Path

import httpx
import pytest

from modules.antibot import analyze_antibot

FIXTURES = Path(__file__).parent.parent / "fixtures" / "html"


@pytest.mark.asyncio
async def test_antibot_cloudflare_waf(respx_mock, mock_antibot_externals):
    """Cloudflare headers + cf-ray body → WAF score >= 2."""
    cf_html = (FIXTURES / "cloudflare_gated.html").read_text()
    respx_mock.get(url__regex=r".*").mock(
        return_value=httpx.Response(
            200,
            text=cf_html,
            headers={"cf-ray": "abc123-SJC", "server": "cloudflare"},
        )
    )

    result = await analyze_antibot("https://example.com", 15.0, api_endpoints=[])

    assert result.dimensions.waf.score >= 2


@pytest.mark.asyncio
async def test_antibot_rate_limit_429(respx_mock, mock_antibot_externals):
    """4th request returns 429 → rate_limiting.score >= 1."""
    ok_html = "<html><body>ok</body></html>"
    responses = (
        [httpx.Response(200, text=ok_html)] * 3
        + [httpx.Response(429, text="Too Many Requests")]
        + [httpx.Response(200, text=ok_html)] * 5
    )
    respx_mock.get(url__regex=r".*").mock(side_effect=responses)

    result = await analyze_antibot("https://example.com", 15.0, api_endpoints=[])

    assert result.dimensions.rate_limiting.score >= 1
    assert result.dimensions.rate_limiting.error_type == "HTTP 429"


@pytest.mark.asyncio
async def test_antibot_clean_site(respx_mock, mock_antibot_externals):
    """Static blog — no antibot signals → overall_level NONE or LOW."""
    static_html = (FIXTURES / "static_blog.html").read_text()
    respx_mock.get(url__regex=r".*").mock(
        return_value=httpx.Response(200, text=static_html, headers={})
    )

    result = await analyze_antibot("https://example.com", 15.0, api_endpoints=[])

    assert result.overall_level in ("NONE", "LOW")
    assert result.overall_score >= 0


@pytest.mark.asyncio
async def test_antibot_returns_all_dimensions(respx_mock, mock_antibot_externals):
    """All 7 dimension fields must be populated."""
    static_html = (FIXTURES / "static_blog.html").read_text()
    respx_mock.get(url__regex=r".*").mock(
        return_value=httpx.Response(200, text=static_html, headers={})
    )

    result = await analyze_antibot("https://example.com", 15.0, api_endpoints=[])

    dims = result.dimensions
    assert dims.waf is not None
    assert dims.tls_fingerprint is not None
    assert dims.rate_limiting is not None
    assert dims.captcha is not None
    assert dims.browser_fingerprinting is not None
    assert dims.honeypots is not None
    assert dims.ip_reputation is not None
