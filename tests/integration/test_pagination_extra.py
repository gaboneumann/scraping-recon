"""
tests/integration/test_pagination_extra.py
Additional integration tests for modules/pagination.py — covers CURSOR (from state blob),
LOAD_MORE, and INFINITE_SCROLL branches.
"""
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
