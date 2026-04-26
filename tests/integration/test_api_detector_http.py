"""
tests/integration/test_api_detector_http.py
Integration tests for modules/api_detector.py using respx HTTP mocking.
"""
from pathlib import Path

import httpx
import pytest

from modules.api_detector import detect_apis

FIXTURES = Path(__file__).parent.parent / "fixtures" / "html"


@pytest.mark.asyncio
async def test_api_detector_rest(respx_mock):
    """React page with fetch('/api/v1/products') → internal_api_found=True, REST endpoint."""
    html = (FIXTURES / "react_api_driven.html").read_text()
    respx_mock.get("https://example.com").mock(
        return_value=httpx.Response(
            200, text=html, headers={"content-type": "text/html"}
        )
    )
    # GraphQL introspection probe should return 404 (no graphql in this page)
    respx_mock.post(url__regex=r".*/graphql.*").mock(
        return_value=httpx.Response(404)
    )

    result = await detect_apis("https://example.com", 15.0, classifier_type="API_DRIVEN")

    assert result is not None
    assert result.internal_api_found is True
    # At least one REST endpoint detected
    rest_endpoints = [ep for ep in result.endpoints if ep.type == "REST"]
    assert len(rest_endpoints) >= 1


@pytest.mark.asyncio
async def test_api_detector_graphql(respx_mock):
    """GraphQL app page with /graphql → endpoint classified as GraphQL."""
    html = (FIXTURES / "graphql_app.html").read_text()
    respx_mock.get("https://example.com").mock(
        return_value=httpx.Response(
            200, text=html, headers={"content-type": "text/html"}
        )
    )
    # GraphQL GET probe
    respx_mock.get(url__regex=r".*/graphql.*").mock(
        return_value=httpx.Response(200, json={"data": {}})
    )
    # GraphQL POST introspection probe
    respx_mock.post(url__regex=r".*/graphql.*").mock(
        return_value=httpx.Response(200, json={"data": {"__typename": "Query"}})
    )

    result = await detect_apis("https://example.com", 15.0, classifier_type="API_DRIVEN")

    assert result is not None
    gql_endpoints = [ep for ep in result.endpoints if ep.type == "GraphQL"]
    assert len(gql_endpoints) >= 1


@pytest.mark.asyncio
async def test_api_detector_no_apis(respx_mock):
    """Static blog → no API endpoints found."""
    html = (FIXTURES / "static_blog.html").read_text()
    respx_mock.get("https://example.com").mock(
        return_value=httpx.Response(
            200, text=html, headers={"content-type": "text/html"}
        )
    )

    result = await detect_apis("https://example.com", 15.0, classifier_type="STATIC")

    assert result is not None
    assert result.internal_api_found is False
    assert result.endpoints == []
