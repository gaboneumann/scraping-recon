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



# ===== merged from test_pagination_extra.py =====
import httpx
import pytest

from modules.pagination import detect_pagination


@pytest.mark.asyncio
async def test_pagination_cursor_from_state_blob(respx_mock) -> None:
    """__NEXT_DATA__ with 'cursor' key → type=CURSOR, requires_js=True."""
    html = (
        '<html><head></head><body>'
        '<script id="__NEXT_DATA__">'
        '{"props":{"pageProps":{"cursor":"abc123","after":"next-page"}}}'
        '</script>'
        '</body></html>'
    )
    respx_mock.get("https://example.com/feed").mock(
        return_value=httpx.Response(200, text=html)
    )

    result = await detect_pagination("https://example.com/feed", 15.0)

    assert result.type == "CURSOR"
    assert result.requires_js is True


@pytest.mark.asyncio
async def test_pagination_load_more_button(respx_mock) -> None:
    """Page with 'load-more' class button → type=LOAD_MORE, requires_js=True."""
    html = (
        '<html><head></head><body>'
        '<button class="load-more" data-page="2">Load More</button>'
        '</body></html>'
    )
    respx_mock.get("https://example.com/articles").mock(
        return_value=httpx.Response(200, text=html)
    )

    result = await detect_pagination("https://example.com/articles", 15.0)

    assert result.type == "LOAD_MORE"
    assert result.requires_js is True


@pytest.mark.asyncio
async def test_pagination_infinite_scroll_intersection_observer(respx_mock) -> None:
    """IntersectionObserver in inline script → type=INFINITE_SCROLL."""
    html = (
        '<html><head></head><body>'
        '<script>'
        'const observer = new IntersectionObserver((entries) => {'
        '  if (entries[0].isIntersecting) { fetch("/api/more"); }'
        '});'
        '</script>'
        '</body></html>'
    )
    respx_mock.get("https://example.com/timeline").mock(
        return_value=httpx.Response(200, text=html)
    )

    result = await detect_pagination("https://example.com/timeline", 15.0)

    assert result.type == "INFINITE_SCROLL"
    assert result.requires_js is True


@pytest.mark.asyncio
async def test_pagination_cursor_from_href(respx_mock) -> None:
    """Link with ?cursor=abc → type=CURSOR."""
    html = (
        '<html><head></head><body>'
        '<a href="/items?cursor=abc123">Next</a>'
        '</body></html>'
    )
    respx_mock.get("https://example.com/items").mock(
        return_value=httpx.Response(200, text=html)
    )

    result = await detect_pagination("https://example.com/items", 15.0)

    assert result.type == "CURSOR"
    assert result.parameter == "cursor"
