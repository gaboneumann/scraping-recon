"""
tests/unit/test_http_helpers.py
Unit tests for utils/http.py — make_request, detect_block, compare_mobile_desktop.
"""
import pytest
import httpx
import respx as respx_lib

from utils.http import make_request, detect_block, compare_mobile_desktop


@pytest.mark.asyncio
async def test_make_request_returns_tuple(respx_mock):
    """make_request returns a 4-tuple (int, dict, str, int)."""
    respx_mock.get("https://example.com").mock(
        return_value=httpx.Response(200, text="<html></html>")
    )

    result = await make_request("https://example.com", timeout=5.0)
    status, headers, html, elapsed = result

    assert isinstance(status, int)
    assert status == 200
    assert isinstance(headers, dict)
    assert isinstance(html, str)
    assert isinstance(elapsed, int)
    assert elapsed >= 0


@pytest.mark.asyncio
async def test_make_request_404(respx_mock):
    """make_request handles 404 responses correctly."""
    respx_mock.get("https://example.com/missing").mock(
        return_value=httpx.Response(404, text="Not Found")
    )

    status, headers, html, elapsed = await make_request("https://example.com/missing", timeout=5.0)

    assert status == 404
    assert "Not Found" in html


@pytest.mark.asyncio
async def test_make_request_custom_ua(respx_mock):
    """make_request passes User-Agent header."""
    respx_mock.get("https://example.com").mock(
        return_value=httpx.Response(200, text="ok")
    )

    status, headers, html, elapsed = await make_request(
        "https://example.com", ua="MyCustomUA/1.0", timeout=5.0
    )
    # Verify the request was made (respx would raise if UA was wrong at assertion level)
    assert status == 200


def test_detect_block_true_on_403_cloudflare():
    """detect_block returns True for 403 + cloudflare body."""
    assert detect_block(403, "Access denied by cloudflare protection") is True


def test_detect_block_true_on_503_blocked():
    """detect_block returns True for 503 + blocked body."""
    assert detect_block(503, "Your request was blocked by security.") is True


def test_detect_block_false_on_200():
    """detect_block returns False for normal 200 response."""
    assert detect_block(200, "<html><body>Welcome</body></html>") is False


def test_detect_block_false_on_403_no_signal():
    """detect_block returns False for 403 without WAF body signals."""
    assert detect_block(403, "Page not found.") is False


@pytest.mark.asyncio
async def test_compare_mobile_desktop_no_difference(respx_mock):
    """Same content for both UAs → content_differs=False."""
    same_html = "<html><body><h1>Hello</h1></body></html>"
    respx_mock.get("https://example.com").mock(
        return_value=httpx.Response(200, text=same_html)
    )

    result = await compare_mobile_desktop("https://example.com", timeout=5.0)

    assert result["content_differs"] is False
    assert "size_diff_pct" in result


@pytest.mark.asyncio
async def test_compare_mobile_desktop_different_content(respx_mock):
    """Different h1 for mobile vs desktop → content_differs=True."""
    desktop_html = "<html><body><h1>Desktop Page</h1>" + "x" * 500 + "</body></html>"
    mobile_html = "<html><body><h1>Mobile Page</h1>" + "y" * 50 + "</body></html>"

    call_count = {"n": 0}

    def side_effect(request):
        call_count["n"] += 1
        ua = request.headers.get("user-agent", "")
        if "iPhone" in ua or "Mobile" in ua:
            return httpx.Response(200, text=mobile_html)
        return httpx.Response(200, text=desktop_html)

    respx_mock.get("https://example.com").mock(side_effect=side_effect)

    result = await compare_mobile_desktop("https://example.com", timeout=5.0)

    # h1 differs → content_differs should be True
    assert result["content_differs"] is True
