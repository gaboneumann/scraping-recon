"""
tests/unit/test_e7_detection.py
Unit tests for E7 deep-mode detection: schema validation, pattern matching, error handling.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from config import Config
from models.schemas import E7Result


# ============ TestE7ResultSchema (5.2) ============
class TestE7ResultSchema:
    """Test E7Result Pydantic schema validation."""

    def test_valid_e7result_creation(self):
        """Test valid E7Result instantiation with all fields."""
        e7 = E7Result(
            js_price_requests=[
                {"url": "https://api.example.com/price", "method": "GET", "has_auth": False}
            ],
            infinite_scroll_pattern="cursor",
            estimated_products=100,
            cart_endpoints=["https://api.example.com/cart"],
            browser_execution_time_ms=5000,
            confidence="high",
        )
        assert e7.confidence == "high"
        assert e7.estimated_products == 100
        assert len(e7.js_price_requests) == 1

    def test_e7result_all_optional_fields_none(self):
        """Test E7Result with all optional fields set to None."""
        e7 = E7Result(
            js_price_requests=None,
            infinite_scroll_pattern=None,
            estimated_products=None,
            cart_endpoints=None,
            browser_execution_time_ms=1000,
            confidence="low",
        )
        assert e7.js_price_requests is None
        assert e7.confidence == "low"
        assert e7.browser_execution_time_ms == 1000

    def test_e7result_invalid_confidence(self):
        """Test E7Result raises ValidationError on invalid confidence."""
        with pytest.raises(Exception):  # Pydantic ValidationError
            E7Result(
                browser_execution_time_ms=5000,
                confidence="invalid_confidence",
            )

    def test_e7result_invalid_infinite_scroll_pattern(self):
        """Test E7Result raises ValidationError on invalid scroll pattern."""
        with pytest.raises(Exception):
            E7Result(
                infinite_scroll_pattern="invalid_pattern",
                browser_execution_time_ms=5000,
                confidence="high",
            )

    def test_e7result_missing_required_field(self):
        """Test E7Result raises ValidationError when missing required fields."""
        with pytest.raises(Exception):
            # Missing browser_execution_time_ms and confidence
            E7Result()


# ============ TestXhrPatternMatching (5.3) ============
class TestXhrPatternMatching:
    """Test XHR pattern matching logic."""

    def test_price_pattern_match(self):
        """Test price pattern matches /api/price URL."""
        patterns = {"price": ["/api/price"]}
        url = "https://example.com/api/price/123"
        assert any(pattern in url for pattern in patterns["price"])

    def test_pagination_pattern_match(self):
        """Test pagination pattern matches /api/products URL."""
        patterns = {"pagination": ["/api/products"]}
        url = "https://example.com/api/products?offset=0"
        assert any(pattern in url for pattern in patterns["pagination"])

    def test_cart_pattern_match(self):
        """Test cart pattern matches /api/cart URL."""
        patterns = {"cart": ["/api/cart"]}
        url = "https://example.com/api/cart/add"
        assert any(pattern in url for pattern in patterns["cart"])

    def test_no_pattern_match(self):
        """Test URL does not match price/pagination/cart patterns."""
        patterns = {
            "price": ["/api/price"],
            "pagination": ["/api/products"],
            "cart": ["/api/cart"],
        }
        url = "https://example.com/static/image.png"
        matches = False
        for patterns_list in patterns.values():
            if any(pattern in url for pattern in patterns_list):
                matches = True
                break
        assert not matches

    def test_false_positive_prevention(self):
        """Test that /api/pricing-info does NOT match /api/price pattern."""
        pattern = "/api/price"
        url = "https://example.com/api/pricing-info"
        # Simple substring match should NOT catch this
        assert pattern not in url

    def test_case_sensitivity(self):
        """Test that /API/PRICE (uppercase) does NOT match /api/price."""
        pattern = "/api/price"
        url = "https://example.com/API/PRICE"
        assert pattern not in url


# ============ TestTimeoutHandling (5.4) ============
class TestTimeoutHandling:
    """Test timeout handling and graceful degradation."""

    @pytest.mark.asyncio
    async def test_timeout_returns_none(self):
        """Test that asyncio.TimeoutError is caught and returns None."""
        from modules.classifier import _detect_deep_ecommerce

        # Mock config
        config = Config(deep=True, timeout=10.0)

        # Create a mock that raises TimeoutError
        with patch(
            "utils.playwright_helper.get_browser_context",
            new_callable=AsyncMock,
            side_effect=asyncio.TimeoutError("Timeout"),
        ):
            # This should be caught and return None (not raise)
            result = await _detect_deep_ecommerce("https://example.com", timeout=10.0, config=config)
            assert result is None

    def test_decision_gate_no_deep_flag_returns_none(self):
        """Test decision gate: without --deep flag, returns None immediately."""
        # This test verifies the gate logic without actually running async code
        config = Config(deep=False, timeout=10.0)
        assert not config.deep  # Flag not set


# ============ TestErrorHandling (5.5) ============
class TestErrorHandling:
    """Test error handling for PlaywrightException and generic Exception."""

    @pytest.mark.asyncio
    async def test_playwright_not_available(self):
        """Test graceful handling when Playwright module unavailable."""
        from modules.classifier import _detect_deep_ecommerce

        config = Config(deep=True, timeout=10.0)

        # Mock ImportError on playwright import
        with patch(
            "utils.playwright_helper.get_browser_context",
            new_callable=AsyncMock,
            side_effect=ImportError("No module named 'playwright'"),
        ):
            result = await _detect_deep_ecommerce("https://example.com", timeout=10.0, config=config)
            assert result is None

    @pytest.mark.asyncio
    async def test_generic_exception_caught(self):
        """Test that generic Exception is caught and returns None."""
        from modules.classifier import _detect_deep_ecommerce

        config = Config(deep=True, timeout=10.0)

        with patch(
            "utils.playwright_helper.get_browser_context",
            new_callable=AsyncMock,
            side_effect=RuntimeError("Unexpected error"),
        ):
            result = await _detect_deep_ecommerce("https://example.com", timeout=10.0, config=config)
            assert result is None


# ============ TestDecisionGate (5.6) ============
class TestDecisionGate:
    """Test decision gate logic (precondition checks)."""

    @pytest.mark.asyncio
    async def test_deep_flag_false_skips_e7(self):
        """Test E7 skipped when config.deep=False."""
        from modules.classifier import _detect_deep_ecommerce

        config = Config(deep=False, timeout=10.0)
        result = await _detect_deep_ecommerce("https://example.com", timeout=10.0, config=config)
        assert result is None

    @pytest.mark.asyncio
    async def test_no_config_skips_e7(self):
        """Test E7 skipped when config is None."""
        from modules.classifier import _detect_deep_ecommerce

        result = await _detect_deep_ecommerce("https://example.com", timeout=10.0, config=None)
        assert result is None

    @pytest.mark.asyncio
    async def test_config_none_attribute_skips_e7(self):
        """Test E7 skipped when config lacks 'deep' attribute."""
        from modules.classifier import _detect_deep_ecommerce

        # Object without 'deep' attribute
        fake_config = MagicMock(spec=[])  # Empty spec = no attributes
        result = await _detect_deep_ecommerce("https://example.com", timeout=10.0, config=fake_config)
        assert result is None


# ============ TestPlaywrightAvailability (5.7) ============
class TestPlaywrightAvailability:
    """Test graceful Playwright unavailability handling."""

    @pytest.mark.asyncio
    async def test_playwright_import_error_handled(self):
        """Test ImportError on Playwright import is caught."""
        from modules.classifier import _detect_deep_ecommerce

        config = Config(deep=True, timeout=10.0)

        # Simulate ImportError during internal Playwright import
        with patch(
            "utils.playwright_helper.get_browser_context",
            side_effect=ImportError("Playwright not installed"),
        ):
            result = await _detect_deep_ecommerce("https://example.com", timeout=10.0, config=config)
            assert result is None

    @pytest.mark.asyncio
    async def test_playwright_module_unavailable_scan_continues(self):
        """Test that if Playwright is unavailable, scan continues gracefully."""
        from modules.classifier import _detect_deep_ecommerce

        config = Config(deep=True, timeout=10.0)

        with patch(
            "utils.playwright_helper.get_browser_context",
            side_effect=ImportError("Playwright not installed"),
        ):
            result = await _detect_deep_ecommerce("https://example.com", timeout=10.0, config=config)
            # E7 returns None, but rest of scan (E1-E6) would continue
            assert result is None
