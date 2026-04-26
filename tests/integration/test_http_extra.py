"""
tests/integration/test_http_extra.py
Additional integration tests for utils/http.py.
Covers: try_with_fallback_uas, make_request retry on TimeoutException, 429/520 status.
"""
from __future__ import annotations

import httpx
import pytest

from utils.http import try_with_fallback_uas, make_request, detect_block


@pytest.mark.asyncio
async def test_try_with_fallback_uas_first_not_blocked(respx_mock) -> None:
    """First UA (Chrome) not blocked → returns immediately."""
    respx_mock.get("https://example.com").mock(
        return_value=httpx.Response(200, text="<html>OK</html>")
    )

    status, headers, text, ms = await try_with_fallback_uas("https://example.com", timeout=5.0)

    assert status == 200
    assert "OK" in text


@pytest.mark.asyncio
async def test_try_with_fallback_uas_first_blocked_second_ok(respx_mock) -> None:
    """Chrome UA blocked (403+cloudflare), Googlebot OK → returns Googlebot response."""
    call_count = {"n": 0}

    def side_effect(request):
        call_count["n"] += 1
        ua = request.headers.get("user-agent", "")
        if "Chrome" in ua and "Googlebot" not in ua:
            return httpx.Response(403, text="Access denied by cloudflare firewall")
        return httpx.Response(200, text="<html>OK via Googlebot</html>")

    respx_mock.get("https://example.com").mock(side_effect=side_effect)

    status, headers, text, ms = await try_with_fallback_uas("https://example.com", timeout=5.0)

    assert status == 200
    assert "OK via Googlebot" in text


@pytest.mark.asyncio
async def test_make_request_timeout_raises(respx_mock) -> None:
    """After 3 timeout retries the TimeoutException propagates."""
    import httpx as httpx_lib

    respx_mock.get("https://example.com/slow").mock(
        side_effect=httpx.ReadTimeout("timed out", request=None)
    )

    with pytest.raises(httpx.ReadTimeout):
        await make_request("https://example.com/slow", timeout=1.0)


@pytest.mark.asyncio
async def test_make_request_429(respx_mock) -> None:
    """make_request handles 429 response cleanly."""
    respx_mock.get("https://example.com/api").mock(
        return_value=httpx.Response(429, text="Too Many Requests")
    )

    status, headers, text, ms = await make_request("https://example.com/api", timeout=5.0)

    assert status == 429
    assert "Too Many Requests" in text


@pytest.mark.asyncio
async def test_make_request_520(respx_mock) -> None:
    """make_request handles 520 (Cloudflare unknown) cleanly."""
    respx_mock.get("https://example.com").mock(
        return_value=httpx.Response(520, text="Unknown error")
    )

    status, headers, text, ms = await make_request("https://example.com", timeout=5.0)

    assert status == 520


def test_detect_block_429() -> None:
    """detect_block returns True for 429 + blocked body."""
    assert detect_block(429, "Too many requests. Security check required.") is True


def test_detect_block_520() -> None:
    """detect_block returns True for 520 + cloudflare body."""
    assert detect_block(520, "Cloudflare unknown error.") is True
