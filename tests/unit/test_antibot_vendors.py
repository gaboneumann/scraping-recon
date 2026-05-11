"""Unit tests for behavioral vendor detection functions."""
import pytest
from bs4 import BeautifulSoup
from modules.antibot import (
    _detect_akamai,
    _detect_behavioral_vendors,
    _detect_datadome,
    _detect_kasada,
    _detect_perimeterx,
    _extract_cookies,
    _extract_scripts,
)
from models.schemas import BehavioralVendor


class TestExtractScripts:
    """Test _extract_scripts helper."""

    def test_extract_inline_script(self):
        """Extract inline script body."""
        html = '<script>var x = 1;</script>'
        soup = BeautifulSoup(html, "lxml")
        scripts = _extract_scripts(html, soup)
        assert "var x = 1;" in scripts

    def test_extract_src_script(self):
        """Extract script src attribute."""
        html = '<script src="https://example.com/app.js"></script>'
        soup = BeautifulSoup(html, "lxml")
        scripts = _extract_scripts(html, soup)
        assert "https://example.com/app.js" in scripts

    def test_extract_mixed_scripts(self):
        """Extract both inline and src scripts."""
        html = '''
        <script src="https://cdn.example.com/lib.js"></script>
        <script>var config = {x: 1};</script>
        '''
        soup = BeautifulSoup(html, "lxml")
        scripts = _extract_scripts(html, soup)
        assert len(scripts) == 2
        assert any("lib.js" in s for s in scripts)
        assert any("config" in s for s in scripts)

    def test_empty_html(self):
        """Handle empty HTML."""
        soup = BeautifulSoup("", "lxml")
        scripts = _extract_scripts("", soup)
        assert scripts == []


class TestExtractCookies:
    """Test _extract_cookies helper."""

    def test_extract_single_cookie(self):
        """Extract single Set-Cookie."""
        headers = {"set-cookie": "session=abc123; Path=/"}
        cookies = _extract_cookies(headers)
        assert "session" in cookies

    def test_extract_multiple_cookies(self):
        """Extract multiple Set-Cookie headers."""
        headers = {
            "set-cookie": "session=abc123; Path=/",
            "set-cookie-2": "_pxAppId=PX1234; Path=/",
        }
        cookies = _extract_cookies(headers)
        assert "session" in cookies
        assert "_pxAppId" in cookies

    def test_empty_headers(self):
        """Handle empty headers."""
        cookies = _extract_cookies({})
        assert cookies == []


class TestDetectDataDome:
    """Test DataDome detection."""

    def test_detect_datadome_via_script_src(self):
        """Detect DataDome via script src."""
        html = '<script src="https://cdn.datadome.com/tags.js"></script>'
        soup = BeautifulSoup(html, "lxml")
        headers = {}
        result = _detect_datadome(html, headers, soup)
        assert result is not None
        assert result.name == "DataDome"
        assert result.confidence == "high"
        assert "script" in result.detected_via

    def test_detect_datadome_via_cookie(self):
        """Detect DataDome via cookie."""
        html = ""
        soup = BeautifulSoup(html, "lxml")
        headers = {"set-cookie": "px2=abcd; Path=/"}
        result = _detect_datadome(html, headers, soup)
        assert result is not None
        assert result.name == "DataDome"
        assert result.confidence == "medium"
        assert "cookie" in result.detected_via

    def test_detect_datadome_via_inline_script(self):
        """Detect DataDome via inline script pattern."""
        html = '<script>var _dd_rum = {init: function() {}};</script>'
        soup = BeautifulSoup(html, "lxml")
        headers = {}
        result = _detect_datadome(html, headers, soup)
        assert result is not None
        assert result.name == "DataDome"
        assert result.confidence == "high"

    def test_datadome_no_match(self):
        """Return None when DataDome not detected."""
        html = '<script src="https://cdn.jquery.com/jquery.min.js"></script>'
        soup = BeautifulSoup(html, "lxml")
        headers = {}
        result = _detect_datadome(html, headers, soup)
        assert result is None


class TestDetectPerimeterX:
    """Test PerimeterX detection."""

    def test_detect_perimeterx_via_script_src(self):
        """Detect PerimeterX via script src."""
        html = '<script src="https://px-cdn.net/bundle.js"></script>'
        soup = BeautifulSoup(html, "lxml")
        headers = {}
        result = _detect_perimeterx(html, headers, soup)
        assert result is not None
        assert result.name == "PerimeterX"
        assert result.confidence == "high"

    def test_detect_perimeterx_via_inline(self):
        """Detect PerimeterX via inline script."""
        html = '<script>var _pxAppId = "PX1234567890";</script>'
        soup = BeautifulSoup(html, "lxml")
        headers = {}
        result = _detect_perimeterx(html, headers, soup)
        assert result is not None
        assert result.name == "PerimeterX"
        assert result.confidence == "high"

    def test_detect_perimeterx_via_cookie(self):
        """Detect PerimeterX via cookie."""
        html = ""
        soup = BeautifulSoup(html, "lxml")
        headers = {"set-cookie": "_pxAppId=PX1234; Path=/"}
        result = _detect_perimeterx(html, headers, soup)
        assert result is not None
        assert result.name == "PerimeterX"
        assert result.confidence == "medium"

    def test_perimeterx_no_match(self):
        """Return None when PerimeterX not detected."""
        html = ""
        soup = BeautifulSoup(html, "lxml")
        headers = {}
        result = _detect_perimeterx(html, headers, soup)
        assert result is None


class TestDetectAkamai:
    """Test Akamai detection."""

    def test_detect_akamai_via_script_src(self):
        """Detect Akamai via script src."""
        html = '<script src="https://example.com/akam-sw.js"></script>'
        soup = BeautifulSoup(html, "lxml")
        headers = {}
        result = _detect_akamai(html, headers, soup)
        assert result is not None
        assert result.name == "Akamai"
        assert result.confidence == "high"

    def test_detect_akamai_via_inline(self):
        """Detect Akamai via inline script (bmak pattern)."""
        html = '<script>var bmak = {config: {}};</script>'
        soup = BeautifulSoup(html, "lxml")
        headers = {}
        result = _detect_akamai(html, headers, soup)
        assert result is not None
        assert result.name == "Akamai"
        assert result.confidence == "high"

    def test_detect_akamai_via_cookie(self):
        """Detect Akamai via cookie."""
        html = ""
        soup = BeautifulSoup(html, "lxml")
        headers = {"set-cookie": "abck=abcd1234; Path=/"}
        result = _detect_akamai(html, headers, soup)
        assert result is not None
        assert result.name == "Akamai"
        assert result.confidence == "medium"

    def test_akamai_no_match(self):
        """Return None when Akamai not detected."""
        html = ""
        soup = BeautifulSoup(html, "lxml")
        headers = {}
        result = _detect_akamai(html, headers, soup)
        assert result is None


class TestDetectKasada:
    """Test Kasada detection."""

    def test_detect_kasada_via_script_src(self):
        """Detect Kasada via script src."""
        html = '<script src="https://kasada.io/client.js"></script>'
        soup = BeautifulSoup(html, "lxml")
        headers = {}
        result = _detect_kasada(html, headers, soup)
        assert result is not None
        assert result.name == "Kasada"
        assert result.confidence == "high"

    def test_detect_kasada_via_inline(self):
        """Detect Kasada via inline script (kpsdk pattern)."""
        html = '<script>var kpsdk = {};</script>'
        soup = BeautifulSoup(html, "lxml")
        headers = {}
        result = _detect_kasada(html, headers, soup)
        assert result is not None
        assert result.name == "Kasada"
        assert result.confidence == "high"

    def test_kasada_no_match(self):
        """Return None when Kasada not detected."""
        html = ""
        soup = BeautifulSoup(html, "lxml")
        headers = {}
        result = _detect_kasada(html, headers, soup)
        assert result is None


class TestDetectBehavioralVendors:
    """Test orchestrator function."""

    def test_no_vendors_detected(self):
        """Return empty list when no vendors present."""
        html = '<script src="https://cdn.jquery.com/jquery.min.js"></script>'
        soup = BeautifulSoup(html, "lxml")
        headers = {}
        vendors = _detect_behavioral_vendors(html, headers, soup)
        assert vendors == []

    def test_single_vendor_detected(self):
        """Detect single vendor."""
        html = '<script src="https://cdn.datadome.com/tags.js"></script>'
        soup = BeautifulSoup(html, "lxml")
        headers = {}
        vendors = _detect_behavioral_vendors(html, headers, soup)
        assert len(vendors) == 1
        assert vendors[0].name == "DataDome"
        assert vendors[0].confidence == "high"

    def test_multiple_vendors_detected(self):
        """Detect multiple vendors and sort by confidence."""
        html = '''
        <script src="https://cdn.datadome.com/tags.js"></script>
        <script>var _pxAppId = "PX1234";</script>
        <script>var bmak = {};</script>
        '''
        soup = BeautifulSoup(html, "lxml")
        headers = {}
        vendors = _detect_behavioral_vendors(html, headers, soup)
        assert len(vendors) == 3
        names = [v.name for v in vendors]
        assert set(names) == {"DataDome", "PerimeterX", "Akamai"}

    def test_vendors_sorted_by_confidence(self):
        """Vendors are sorted: high > medium > low."""
        html = ''
        soup = BeautifulSoup(html, "lxml")
        headers = {
            "set-cookie": "px2=low_conf; Path=/",
        }
        vendors = _detect_behavioral_vendors(html, headers, soup)
        confidences = [v.confidence for v in vendors]
        assert confidences == sorted(confidences, key=lambda c: {"high": 0, "medium": 1, "low": 2}[c])

    def test_vendors_deduplicated(self):
        """Each vendor appears only once."""
        html = '''
        <script src="https://cdn.datadome.com/tags.js"></script>
        <script>var _dd_rum = {};</script>
        '''
        soup = BeautifulSoup(html, "lxml")
        headers = {}
        vendors = _detect_behavioral_vendors(html, headers, soup)
        assert len(vendors) == 1
        assert vendors[0].name == "DataDome"

    def test_malformed_html_gracefully_handled(self):
        """Malformed HTML does not raise exception."""
        html = '<script src="https://cdn.datadome.com/tags.js"'
        soup = BeautifulSoup(html, "lxml")
        headers = {}
        vendors = _detect_behavioral_vendors(html, headers, soup)
        assert isinstance(vendors, list)

    def test_empty_html(self):
        """Empty HTML returns empty list."""
        html = ""
        soup = BeautifulSoup(html, "lxml")
        headers = {}
        vendors = _detect_behavioral_vendors(html, headers, soup)
        assert vendors == []

    def test_case_insensitive_matching(self):
        """Patterns are case-insensitive."""
        html = '<script src="https://cdn.DATADOME.COM/tags.js"></script>'
        soup = BeautifulSoup(html, "lxml")
        headers = {}
        vendors = _detect_behavioral_vendors(html, headers, soup)
        assert len(vendors) == 1
        assert vendors[0].name == "DataDome"

    def test_return_type_is_list_of_behavioral_vendor(self):
        """Return type is list[BehavioralVendor]."""
        html = '<script src="https://cdn.datadome.com/tags.js"></script>'
        soup = BeautifulSoup(html, "lxml")
        headers = {}
        vendors = _detect_behavioral_vendors(html, headers, soup)
        assert isinstance(vendors, list)
        assert all(isinstance(v, BehavioralVendor) for v in vendors)
