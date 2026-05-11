"""Integration tests for behavioral vendor detection in full antibot pipeline."""
import pytest
import respx
from httpx import Response
from modules.antibot import analyze_antibot
from models.schemas import BehavioralVendor


class TestBehavioralVendorIntegration:
    """Test behavioral vendor detection in full antibot pipeline."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_analyze_antibot_with_datadome(self):
        """Test full antibot flow with DataDome detected."""
        html = '''
        <html>
        <head>
            <script src="https://cdn.datadome.com/tags.js"></script>
        </head>
        <body>Test</body>
        </html>
        '''
        respx.get("https://example.com/").mock(return_value=Response(200, text=html))

        result = await analyze_antibot("https://example.com/")

        assert result.behavioral_vendors is not None
        assert len(result.behavioral_vendors) >= 1
        vendors_by_name = {v.name: v for v in result.behavioral_vendors}
        assert "DataDome" in vendors_by_name
        datadome = vendors_by_name["DataDome"]
        assert datadome.confidence == "high"
        assert "script" in datadome.detected_via

    @pytest.mark.asyncio
    @respx.mock
    async def test_analyze_antibot_with_multiple_vendors(self):
        """Test full antibot flow with multiple vendors."""
        html = '''
        <html>
        <head>
            <script src="https://cdn.datadome.com/tags.js"></script>
            <script>var _pxAppId = "PX1234567890";</script>
            <script>var bmak = {config: {}};</script>
        </head>
        <body>Test</body>
        </html>
        '''
        respx.get("https://example.com/").mock(return_value=Response(200, text=html))

        result = await analyze_antibot("https://example.com/")

        assert result.behavioral_vendors is not None
        assert len(result.behavioral_vendors) == 3
        names = {v.name for v in result.behavioral_vendors}
        assert names == {"DataDome", "PerimeterX", "Akamai"}

    @pytest.mark.asyncio
    @respx.mock
    async def test_analyze_antibot_no_vendors(self):
        """Test full antibot flow with no vendors detected."""
        html = '''
        <html>
        <head>
            <script src="https://cdn.jquery.com/jquery.min.js"></script>
        </head>
        <body>Test</body>
        </html>
        '''
        respx.get("https://example.com/").mock(return_value=Response(200, text=html))

        result = await analyze_antibot("https://example.com/")

        assert result.behavioral_vendors is not None
        assert result.behavioral_vendors == []

    @pytest.mark.asyncio
    @respx.mock
    async def test_analyze_antibot_behavioral_vendors_do_not_affect_score(self):
        """Verify behavioral_vendors is informational only, does not affect score."""
        html_no_vendors = '<html><body>Test</body></html>'
        html_with_vendors = '''
        <html>
        <head><script src="https://cdn.datadome.com/tags.js"></script></head>
        <body>Test</body>
        </html>
        '''

        respx.get("https://example.com/base").mock(
            return_value=Response(200, text=html_no_vendors)
        )
        result_no_vendors = await analyze_antibot("https://example.com/base")

        respx.get("https://example.com/with-vendor").mock(
            return_value=Response(200, text=html_with_vendors)
        )
        result_with_vendors = await analyze_antibot("https://example.com/with-vendor")

        assert result_no_vendors.overall_score == result_with_vendors.overall_score
        assert result_no_vendors.overall_level == result_with_vendors.overall_level

    @pytest.mark.asyncio
    @respx.mock
    async def test_behavioral_vendors_serializes_to_json(self):
        """Verify behavioral_vendors serializes correctly in model_dump_json()."""
        html = '<script src="https://kasada.io/client.js"></script>'
        respx.get("https://example.com/").mock(return_value=Response(200, text=html))

        result = await analyze_antibot("https://example.com/")
        json_str = result.model_dump_json()

        assert "behavioral_vendors" in json_str
        assert "Kasada" in json_str
        assert "high" in json_str

    @pytest.mark.asyncio
    @respx.mock
    async def test_behavioral_vendors_sorted_by_confidence(self):
        """Verify vendors are sorted by confidence in result."""
        html = '''
        <html>
        <head>
            <script src="https://cdn.datadome.com/tags.js"></script>
        </head>
        <body></body>
        </html>
        '''
        # Add cookie header for medium confidence
        headers = {"set-cookie": "_pxAppId=PX1234; Path=/"}
        respx.get("https://example.com/").mock(
            return_value=Response(200, text=html, headers=headers)
        )

        result = await analyze_antibot("https://example.com/")

        confidences = [v.confidence for v in result.behavioral_vendors]
        confidence_order = {"high": 0, "medium": 1, "low": 2}
        scores = [confidence_order[c] for c in confidences]
        assert scores == sorted(scores)

    @pytest.mark.asyncio
    @respx.mock
    async def test_empty_html_returns_empty_vendors(self):
        """Test that empty HTML returns empty behavioral_vendors list."""
        respx.get("https://example.com/").mock(return_value=Response(200, text=""))

        result = await analyze_antibot("https://example.com/")

        assert result.behavioral_vendors == []

    @pytest.mark.asyncio
    @respx.mock
    async def test_malformed_html_handled_gracefully(self):
        """Test that malformed HTML does not crash."""
        html = '<script src="https://cdn.datadome.com/tags.js"'
        respx.get("https://example.com/").mock(return_value=Response(200, text=html))

        result = await analyze_antibot("https://example.com/")

        assert isinstance(result.behavioral_vendors, list)

    @pytest.mark.asyncio
    @respx.mock
    async def test_behavioral_vendors_detected_via_field_populated(self):
        """Verify detected_via field is populated correctly."""
        html = '<script src="https://px-cdn.net/bundle.js"></script>'
        respx.get("https://example.com/").mock(return_value=Response(200, text=html))

        result = await analyze_antibot("https://example.com/")

        assert len(result.behavioral_vendors) == 1
        vendor = result.behavioral_vendors[0]
        assert vendor.name == "PerimeterX"
        assert isinstance(vendor.detected_via, list)
        assert "script" in vendor.detected_via
