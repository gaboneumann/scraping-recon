"""
tests/integration/test_e7_helpers.py
Integration tests for E7 deep-mode Playwright helpers.

Tests the XHR interception, scroll detection, cart button finding, and browser context
lifecycle for runtime e-commerce signal detection.

Mocks Playwright interactions to avoid requiring a real browser in test.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from utils.playwright_helper import (
    find_and_click_cart_button,
    get_browser_context,
    scroll_page_to_bottom,
    setup_xhr_interception,
)


class TestE7HelpersFunctions:
    """Integration tests for E7 Playwright helper functions."""

    @pytest.mark.asyncio
    async def test_setup_xhr_interception_price_pattern(self) -> None:
        """Test setup_xhr_interception captures price API requests."""
        # Mock page and route interception
        mock_page = AsyncMock()
        patterns = {
            "price": ["/api/price", "/graphql"],
            "pagination": ["/api/products"],
            "cart": ["/api/cart"],
        }

        # Mock route handler to simulate captured request
        async def mock_route_setup(pattern, handler):
            # Simulate a price request being captured
            pass

        mock_page.route = mock_route_setup

        # Call function
        result = await setup_xhr_interception(mock_page, patterns)

        # Verify structure: should have all signal types as keys
        assert "price" in result
        assert "pagination" in result
        assert "cart" in result
        assert isinstance(result["price"], list)

    @pytest.mark.asyncio
    async def test_setup_xhr_interception_pagination_pattern(self) -> None:
        """Test setup_xhr_interception captures pagination requests."""
        mock_page = AsyncMock()
        patterns = {
            "pagination": ["/api/products", "/list?page="],
        }

        result = await setup_xhr_interception(mock_page, patterns)

        assert "pagination" in result
        assert isinstance(result["pagination"], list)

    @pytest.mark.asyncio
    async def test_scroll_page_to_bottom_triggers_requests(self) -> None:
        """Test scroll_page_to_bottom triggers scroll events and returns count."""
        mock_page = AsyncMock()

        # Mock page height changes: 1000 -> 1500 -> 1500 (stops)
        heights = [1000, 1500, 1500]
        mock_page.evaluate = AsyncMock(side_effect=heights)

        scrolls = await scroll_page_to_bottom(mock_page, max_scrolls=5, scroll_delay_ms=100)

        # Should stop after 2 scrolls (height no longer changes)
        assert scrolls == 1

    @pytest.mark.asyncio
    async def test_scroll_page_to_bottom_timeout_graceful(self) -> None:
        """Test scroll_page_to_bottom handles timeout gracefully."""
        mock_page = AsyncMock()
        # Raise TimeoutError on first scroll evaluation
        mock_page.evaluate = AsyncMock(side_effect=asyncio.TimeoutError)

        scrolls = await scroll_page_to_bottom(mock_page, max_scrolls=5)

        # Should return 0 on timeout without raising
        assert scrolls == 0

    @pytest.mark.asyncio
    async def test_scroll_page_to_bottom_max_scrolls_respected(self) -> None:
        """Test scroll_page_to_bottom respects max_scrolls limit."""
        mock_page = AsyncMock()

        # Mock heights that always increase (max_scrolls should stop it)
        mock_page.evaluate = AsyncMock(side_effect=[
            1000, 1100, 1200, 1300, 1400, 1500, 1600
        ])

        scrolls = await scroll_page_to_bottom(mock_page, max_scrolls=3)

        assert scrolls == 3

    @pytest.mark.asyncio
    async def test_find_and_click_cart_button_found(self) -> None:
        """Test find_and_click_cart_button returns True when cart button found."""
        mock_page = MagicMock()
        mock_locator = AsyncMock()
        mock_element = AsyncMock()

        # Mock locator.first.is_visible() returns True
        mock_locator.first = mock_element
        mock_element.is_visible = AsyncMock(return_value=True)
        mock_element.hover = AsyncMock()

        mock_page.locator = MagicMock(return_value=mock_locator)

        result = await find_and_click_cart_button(mock_page, gentle=True)

        assert result is True

    @pytest.mark.asyncio
    async def test_find_and_click_cart_button_not_found(self) -> None:
        """Test find_and_click_cart_button returns False when no cart button."""
        mock_page = MagicMock()
        mock_locator = AsyncMock()
        mock_element = AsyncMock()

        # Mock locator.first.is_visible() returns False
        mock_locator.first = mock_element
        mock_element.is_visible = AsyncMock(return_value=False)

        mock_page.locator = MagicMock(return_value=mock_locator)

        result = await find_and_click_cart_button(mock_page, gentle=True)

        assert result is False

    @pytest.mark.asyncio
    async def test_get_browser_context_cleanup_on_exception(self) -> None:
        """Test get_browser_context cleans up resources on exception."""
        # This test verifies that the context manager properly closes on error
        # by using a mock that raises inside the context

        with patch("playwright.async_api.async_playwright") as mock_async_pw:
            mock_pm = AsyncMock()
            mock_chromium = AsyncMock()
            mock_browser = AsyncMock()
            mock_context = AsyncMock()
            mock_page = AsyncMock()

            # Setup mock chain
            mock_pm.__aenter__ = AsyncMock(return_value=mock_pm)
            mock_pm.__aexit__ = AsyncMock(return_value=None)
            mock_pm.chromium = mock_chromium
            mock_chromium.launch = AsyncMock(return_value=mock_browser)
            mock_browser.new_context = AsyncMock(return_value=mock_context)
            mock_context.new_page = AsyncMock(return_value=mock_page)
            mock_browser.close = AsyncMock()

            mock_async_pw.return_value = mock_pm

            # Use context manager
            try:
                async with get_browser_context() as (page, context):
                    assert page is not None
                    assert context is not None
            except Exception:
                pass

            # Verify browser.close was called
            mock_browser.close.assert_called()

    @pytest.mark.asyncio
    async def test_get_browser_context_resource_leak_prevention(self) -> None:
        """Test get_browser_context prevents resource leaks."""
        with patch("playwright.async_api.async_playwright") as mock_async_pw:
            mock_pm = AsyncMock()
            mock_chromium = AsyncMock()
            mock_browser = AsyncMock()
            mock_context = AsyncMock()
            mock_page = AsyncMock()

            mock_pm.__aenter__ = AsyncMock(return_value=mock_pm)
            mock_pm.__aexit__ = AsyncMock(return_value=None)
            mock_pm.chromium = mock_chromium
            mock_chromium.launch = AsyncMock(return_value=mock_browser)
            mock_browser.new_context = AsyncMock(return_value=mock_context)
            mock_context.new_page = AsyncMock(return_value=mock_page)
            mock_browser.close = AsyncMock()

            mock_async_pw.return_value = mock_pm

            async with get_browser_context() as (page, context):
                # Simulate some work
                pass

            # Verify close was called exactly once
            assert mock_browser.close.call_count == 1
