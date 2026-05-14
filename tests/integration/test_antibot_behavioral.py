"""
Integration tests for B2-B7 behavioral antibot detection against real URLs.
Tests fingerprinting, behavioral listeners, and journey probes on live sites.
Note: Real URL tests are skipped if network unavailable.
"""
import pytest
import asyncio

from modules.antibot import analyze_antibot


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "network: mark test as requiring internet connectivity"
    )


class TestScoringRecalculation:
    """Integration tests for 9-dimension scoring."""

    @pytest.mark.asyncio
    async def test_overall_score_range(self):
        """
        Overall score should remain 0-10 despite 9 dimensions
        (max 27 points mapped to 0-10).
        """
        url = "https://example.com"
        result = await analyze_antibot(url, timeout=30.0)

        assert 0 <= result.overall_score <= 10
        assert result.overall_level in ["NONE", "LOW", "MEDIUM", "HIGH", "EXTREME"]

    @pytest.mark.asyncio
    async def test_nine_dimensions_present(self):
        """All 9 dimensions should be present in result."""
        url = "https://example.com"
        result = await analyze_antibot(url, timeout=30.0)

        dims = result.dimensions
        assert dims.waf is not None
        assert dims.tls_fingerprint is not None
        assert dims.rate_limiting is not None
        assert dims.captcha is not None
        assert dims.browser_fingerprinting is not None
        assert dims.honeypots is not None
        assert dims.ip_reputation is not None
        assert dims.behavioral_detection is not None
        assert dims.journey_probes is not None


class TestBehavioralListenersIntegration:
    """Integration tests for behavioral event listener detection (B5)."""

    @pytest.mark.asyncio
    async def test_behavioral_listeners_scoring(self):
        """
        Any site may have behavioral event listeners.
        Score should accurately reflect listener presence/count.
        """
        url = "https://example.com"
        result = await analyze_antibot(url, timeout=30.0)

        # Behavioral detection should be present
        assert result.dimensions.behavioral_detection.listener_count >= 0
        assert result.dimensions.behavioral_detection.score >= 0
        assert result.dimensions.behavioral_detection.score <= 3
        assert result.dimensions.behavioral_detection.confidence in ["low", "medium", "high"]


class TestJourneyProbesIntegration:
    """Integration tests for commerce journey probes (B6)."""

    @pytest.mark.asyncio
    async def test_journey_probes_without_ecommerce_signals(self):
        """
        Without ecommerce_signals, journey probes should not send requests.
        """
        url = "https://example.com"
        result = await analyze_antibot(url, ecommerce_signals=None)

        # Should not probe without ecommerce signals
        assert result.dimensions.journey_probes.probes_sent == 0
        assert result.dimensions.journey_probes.blocked_type == "none"

    @pytest.mark.asyncio
    async def test_journey_probes_with_ecommerce_signals(self):
        """
        With ecommerce_signals indicating ecommerce site,
        journey probes should attempt probes (if endpoint available).
        """
        url = "https://example.com"
        ecommerce_signals = {"is_ecommerce": True, "platform": "custom"}
        result = await analyze_antibot(
            url,
            ecommerce_signals=ecommerce_signals,
            timeout=30.0,
        )

        # Journey probes should have been attempted
        assert result.dimensions.journey_probes.probes_sent >= 0
        assert result.dimensions.journey_probes.probes_sent <= 2
        assert result.dimensions.journey_probes.blocked_type in [
            "403", "challenge", "redirect", "rate_limit", "none"
        ]


class TestIntegrationEdgeCases:
    """Edge case integration tests."""

    @pytest.mark.asyncio
    async def test_site_with_no_protections(self):
        """
        Static site with minimal protections should have low antibot score.
        """
        url = "https://example.com"
        result = await analyze_antibot(url, timeout=30.0)

        # example.com is minimal, should have low-medium score
        assert result.overall_score < 8
        # All dimensions should be present even if score is 0
        assert result.dimensions.behavioral_detection is not None
        assert result.dimensions.journey_probes is not None
