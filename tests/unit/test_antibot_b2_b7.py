"""
Unit tests for B2-B7 behavioral antibot vendor detection.
Tests fingerprinting patterns (B2, B3, B7), PoW detection (B4),
behavioral listeners (B5), and journey probes (B6 mock).
"""
import pytest
from bs4 import BeautifulSoup
from unittest.mock import AsyncMock, patch

from modules.antibot import (
    _detect_behavioral_events,
    _detect_captcha,
    _detect_fingerprinting,
    _detect_journey_probes,
)


class TestB2CanvasFingerprinting:
    """B2: Canvas fingerprinting via toDataURL."""

    def test_canvas_todataurl_detected(self):
        """Canvas.toDataURL pattern should be detected."""
        html = """
        <script>
            const canvas = document.createElement('canvas');
            canvas.toDataURL('image/png');
        </script>
        """
        soup = BeautifulSoup(html, "lxml")
        result = _detect_fingerprinting(html)
        assert result.score > 0
        assert any("Canvas" in lib for lib in result.libraries)

    def test_canvas_getimagedata_detected(self):
        """Canvas.getImageData pattern should be detected."""
        html = "<script>ctx.getImageData(0, 0, 100, 100);</script>"
        result = _detect_fingerprinting(html)
        assert result.score > 0
        assert any("Canvas" in lib for lib in result.libraries)

    def test_canvas_not_detected_without_pattern(self):
        """HTML without canvas patterns should have low/no score."""
        html = "<p>No fingerprinting here</p>"
        result = _detect_fingerprinting(html)
        assert "Canvas FP" not in result.libraries


class TestB2AudioContextFingerprinting:
    """B2: AudioContext fingerprinting via createDynamicsCompressor."""

    def test_audiocontext_detected(self):
        """AudioContext pattern should be detected."""
        html = """
        <script>
            const ctx = new AudioContext();
            ctx.createDynamicsCompressor();
        </script>
        """
        result = _detect_fingerprinting(html)
        assert result.score > 0
        assert any("AudioContext" in lib for lib in result.libraries)

    def test_webkit_audiocontext_detected(self):
        """WebKit AudioContext variant should be detected."""
        html = "<script>const ctx = new webkitAudioContext();</script>"
        result = _detect_fingerprinting(html)
        assert any("AudioContext" in lib for lib in result.libraries)


class TestB2WebGLFingerprinting:
    """B2: WebGL fingerprinting via getParameter."""

    def test_webgl_renderer_detected(self):
        """WebGL renderer query (0x9245) should be detected."""
        html = "<script>gl.getParameter(0x9245);</script>"
        result = _detect_fingerprinting(html)
        assert result.score > 0
        assert "WebGL FP" in result.libraries

    def test_webgl_vendor_detected(self):
        """WebGL vendor query (0x846D) should be detected."""
        html = "<script>gl.getParameter(0x846D);</script>"
        result = _detect_fingerprinting(html)
        assert "WebGL FP" in result.libraries


class TestB3HeadlessBrowserChecks:
    """B3: Headless browser detection via navigator and window checks."""

    def test_navigator_webdriver_detected(self):
        """navigator.webdriver check should be detected."""
        html = "<script>if (navigator.webdriver) { alert('bot'); }</script>"
        result = _detect_fingerprinting(html)
        assert result.score > 0
        assert any("Webdriver" in lib for lib in result.libraries)

    def test_navigator_plugins_detected(self):
        """navigator.plugins check should be detected."""
        html = "<script>const plugins = navigator.plugins; const mimes = navigator.mimeTypes;</script>"
        result = _detect_fingerprinting(html)
        assert "Plugins check" in result.libraries

    def test_chrome_object_detected(self):
        """window.chrome check should be detected."""
        html = "<script>if (window.chrome || chrome.runtime) { console.log('Chrome'); }</script>"
        result = _detect_fingerprinting(html)
        assert "Chrome check" in result.libraries


class TestB4TurnstilePoWDetection:
    """B4: Proof of Work detection via Turnstile widget."""

    def test_turnstile_widget_detected(self):
        """Turnstile widget in HTML should be detected with score 3."""
        html = """
        <div class="cf-turnstile" data-sitekey="..."></div>
        <script src="https://challenges.cloudflare.com/turnstile/v0/api.js"></script>
        """
        result = _detect_captcha(html)
        assert result.score == 3
        assert result.provider in ["Turnstile", "Turnstile PoW"]

    def test_turnstile_inline_js_detected(self):
        """Turnstile inline JS should be detected."""
        html = "<script src='https://challenges.cloudflare.com/turnstile/v0/api.js'></script>"
        result = _detect_captcha(html)
        assert result.score == 3
        assert result.provider in ["Turnstile", "Turnstile PoW"]


class TestB5BehavioralEventListeners:
    """B5: Behavioral event listener detection."""

    def test_multiple_listeners_detected(self):
        """Multiple event listeners should increase score."""
        html = """
        <script>
            document.addEventListener('mousemove', handler);
            document.addEventListener('keydown', handler);
            document.addEventListener('scroll', handler);
        </script>
        """
        soup = BeautifulSoup(html, "lxml")
        result = _detect_behavioral_events(html, soup)
        assert result.listener_count >= 2
        assert result.score > 0
        assert "mousemove" in result.listener_types

    def test_single_listener_low_score(self):
        """Single listener should have low score."""
        html = "<script>document.addEventListener('mousemove', handler);</script>"
        soup = BeautifulSoup(html, "lxml")
        result = _detect_behavioral_events(html, soup)
        assert result.listener_count == 1
        assert result.score == 0  # Need 2+ to trigger

    def test_no_listeners_zero_score(self):
        """No listeners should have zero score."""
        html = "<p>No event listeners</p>"
        soup = BeautifulSoup(html, "lxml")
        result = _detect_behavioral_events(html, soup)
        assert result.score == 0
        assert result.listener_count == 0


class TestB6JourneyProbesMock:
    """B6: Commerce journey probes (mocked HTTP responses)."""

    @pytest.mark.asyncio
    async def test_journey_probe_403_blocked(self):
        """Journey probe returning 403 should indicate blockage."""
        with patch("modules.antibot.make_request") as mock_request:
            mock_request.return_value = (403, {}, "", None)
            result = await _detect_journey_probes(
                "https://example.com",
                {"is_ecommerce": True},
                timeout=15.0,
            )
            assert result.blocked_type == "403"
            assert result.blocked_at_url is not None
            assert result.score > 0
            assert result.probes_sent > 0

    @pytest.mark.asyncio
    async def test_journey_probe_redirect(self):
        """Journey probe with 302 redirect should be flagged."""
        with patch("modules.antibot.make_request") as mock_request:
            mock_request.return_value = (302, {"location": "/login"}, "", None)
            result = await _detect_journey_probes(
                "https://example.com",
                {"is_ecommerce": True},
                timeout=15.0,
            )
            assert result.blocked_type == "redirect"
            assert result.score > 0

    @pytest.mark.asyncio
    async def test_journey_probe_no_ecommerce(self):
        """Non-ecommerce site should skip probes."""
        result = await _detect_journey_probes(
            "https://example.com",
            {"is_ecommerce": False},
            timeout=15.0,
        )
        assert result.blocked_type == "none"
        assert result.probes_sent == 0
        assert result.score == 0

    @pytest.mark.asyncio
    async def test_journey_probe_max_2_requests(self):
        """Journey probes should max out at 2 requests."""
        with patch("modules.antibot.make_request") as mock_request:
            mock_request.return_value = (200, {}, "", None)
            result = await _detect_journey_probes(
                "https://example.com",
                {"is_ecommerce": True},
                timeout=15.0,
            )
            assert result.probes_sent <= 2


class TestB7WebRTCDetection:
    """B7: WebRTC leak detection patterns."""

    def test_rtcpeerconnection_detected(self):
        """RTCPeerConnection pattern should be detected."""
        html = """
        <script>
            const peerConnection = new RTCPeerConnection({
                iceServers: [{ urls: ['stun:stun.l.google.com:19302'] }]
            });
        </script>
        """
        result = _detect_fingerprinting(html)
        assert result.score > 0
        assert "WebRTC leak" in result.libraries

    def test_getusermedia_detected(self):
        """getUserMedia pattern should be detected."""
        html = "<script>navigator.mediaDevices.getUserMedia({ audio: true });</script>"
        result = _detect_fingerprinting(html)
        assert any("WebRTC" in lib for lib in result.libraries)

    def test_createdatachannel_detected(self):
        """createDataChannel pattern should be detected."""
        html = "<script>peerConnection.createDataChannel('test');</script>"
        result = _detect_fingerprinting(html)
        assert any("WebRTC" in lib for lib in result.libraries)
