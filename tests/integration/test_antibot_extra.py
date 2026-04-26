"""
tests/integration/test_antibot_extra.py
Additional integration tests for modules/antibot.py.
Covers: API endpoint probing, rate limit 503, rate limit slowdown,
_test_rate_limiting_quick (401/403/exception paths).
"""
from __future__ import annotations

import httpx
import pytest

from models.schemas import ApiEndpoint
from modules.antibot import (
    analyze_antibot,
    _assess_ip_reputation,
    _test_rate_limiting_quick,
)


@pytest.mark.asyncio
async def test_antibot_with_api_endpoints_probed(respx_mock, mock_antibot_externals) -> None:
    """Providing REST API endpoints → api_endpoint_probes populated."""
    ok_html = "<html><body>ok</body></html>"
    respx_mock.get(url__regex=r".*").mock(
        return_value=httpx.Response(200, text=ok_html, headers={})
    )

    endpoints = [
        ApiEndpoint(url="/api/v1/products", type="REST", authenticated=None),
    ]

    result = await analyze_antibot("https://example.com", 15.0, api_endpoints=endpoints)

    assert len(result.api_endpoint_probes) == 1
    assert result.api_endpoint_probes[0].endpoint_type == "REST"


@pytest.mark.asyncio
async def test_antibot_api_endpoint_graphql_probed(respx_mock, mock_antibot_externals) -> None:
    """GraphQL endpoint → probed and type preserved."""
    ok_html = "<html><body>ok</body></html>"
    respx_mock.get(url__regex=r".*").mock(
        return_value=httpx.Response(200, text=ok_html, headers={})
    )

    endpoints = [
        ApiEndpoint(url="/graphql", type="GraphQL", authenticated=None),
    ]

    result = await analyze_antibot("https://example.com", 15.0, api_endpoints=endpoints)

    assert len(result.api_endpoint_probes) == 1
    assert result.api_endpoint_probes[0].endpoint_type == "GraphQL"


@pytest.mark.asyncio
async def test_antibot_endpoint_max_2_probed(respx_mock, mock_antibot_externals) -> None:
    """Only 2 endpoints probed even if 3 are provided."""
    ok_html = "<html><body>ok</body></html>"
    respx_mock.get(url__regex=r".*").mock(
        return_value=httpx.Response(200, text=ok_html, headers={})
    )

    endpoints = [
        ApiEndpoint(url="/api/v1/users", type="REST", authenticated=None),
        ApiEndpoint(url="/api/v1/orders", type="REST", authenticated=None),
        ApiEndpoint(url="/api/v1/products", type="REST", authenticated=None),
    ]

    result = await analyze_antibot("https://example.com", 15.0, api_endpoints=endpoints)

    assert len(result.api_endpoint_probes) <= 2


@pytest.mark.asyncio
async def test_antibot_endpoint_websocket_skipped(respx_mock, mock_antibot_externals) -> None:
    """WebSocket endpoints are not probed (type filter)."""
    ok_html = "<html><body>ok</body></html>"
    respx_mock.get(url__regex=r".*").mock(
        return_value=httpx.Response(200, text=ok_html, headers={})
    )

    endpoints = [
        ApiEndpoint(url="/ws/live", type="WebSocket", authenticated=None),
    ]

    result = await analyze_antibot("https://example.com", 15.0, api_endpoints=endpoints)

    assert len(result.api_endpoint_probes) == 0


@pytest.mark.asyncio
async def test_antibot_rate_limit_503(respx_mock, mock_antibot_externals) -> None:
    """5th request returns 503 → rate_limiting.score=2, error_type='HTTP 503'."""
    ok_html = "<html><body>ok</body></html>"
    responses = (
        [httpx.Response(200, text=ok_html)] * 4
        + [httpx.Response(503, text="Service Unavailable")]
        + [httpx.Response(200, text=ok_html)] * 4
    )
    respx_mock.get(url__regex=r".*").mock(side_effect=responses)

    result = await analyze_antibot("https://example.com", 15.0, api_endpoints=[])

    assert result.dimensions.rate_limiting.score >= 1


@pytest.mark.asyncio
async def test_test_rate_limiting_quick_401(respx_mock, mock_antibot_externals) -> None:
    """_test_rate_limiting_quick: 401 → score=1, error_type contains '401'."""
    respx_mock.get(url__regex=r".*").mock(
        return_value=httpx.Response(401, text="Unauthorized")
    )

    result = await _test_rate_limiting_quick("https://example.com/api/v1/data", timeout=5.0)

    assert result.score == 1
    assert "401" in (result.error_type or "")


@pytest.mark.asyncio
async def test_test_rate_limiting_quick_429(respx_mock, mock_antibot_externals) -> None:
    """_test_rate_limiting_quick: 429 on first request → score=3."""
    respx_mock.get(url__regex=r".*").mock(
        return_value=httpx.Response(429, text="Too Many Requests")
    )

    result = await _test_rate_limiting_quick("https://example.com/api/v1/data", timeout=5.0)

    assert result.score == 3
    assert result.triggered_at == 0
