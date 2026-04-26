"""
tests/integration/test_pagination_http.py
Integration tests for modules/pagination.py using respx HTTP mocking.
"""
from pathlib import Path

import httpx
import pytest

from modules.pagination import detect_pagination

FIXTURES = Path(__file__).parent.parent / "fixtures" / "html"


@pytest.mark.asyncio
async def test_pagination_query_param(respx_mock):
    """Page with ?page=N links → type=QUERY_PARAM."""
    html = (FIXTURES / "paginated_query.html").read_text()
    respx_mock.get("https://example.com/products").mock(
        return_value=httpx.Response(200, text=html)
    )

    result = await detect_pagination("https://example.com/products", 15.0)

    assert result.type == "QUERY_PARAM"
    assert result.parameter == "page"


@pytest.mark.asyncio
async def test_pagination_path(respx_mock):
    """Page with /page/N links (no link rel=next) → type=PATH."""
    html = (
        '<html><head></head><body>'
        '<nav><a href="/blog/page/2">Next</a><a href="/blog/page/3">3</a></nav>'
        '</body></html>'
    )
    respx_mock.get("https://example.com/blog").mock(
        return_value=httpx.Response(200, text=html)
    )

    result = await detect_pagination("https://example.com/blog", 15.0)

    assert result.type == "PATH"


@pytest.mark.asyncio
async def test_pagination_none(respx_mock):
    """Static blog with no pagination signals → type=NONE."""
    html = (FIXTURES / "static_blog.html").read_text()
    respx_mock.get("https://example.com").mock(
        return_value=httpx.Response(200, text=html)
    )

    result = await detect_pagination("https://example.com", 15.0)

    assert result.type == "NONE"


@pytest.mark.asyncio
async def test_pagination_link_rel_next(respx_mock):
    """Page with <link rel='next'> → highest priority → type=LINK_REL_NEXT."""
    html = (
        '<html><head>'
        '<link rel="next" href="/page/2">'
        '</head><body></body></html>'
    )
    respx_mock.get("https://example.com/articles").mock(
        return_value=httpx.Response(200, text=html)
    )

    result = await detect_pagination("https://example.com/articles", 15.0)

    assert result.type == "LINK_REL_NEXT"
    assert result.example_next_url == "https://example.com/page/2"
