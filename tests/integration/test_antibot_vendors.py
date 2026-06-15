"""Integration tests for behavioral vendor detection in the full antibot pipeline.

Detection logic itself is fully covered by tests/unit/test_antibot_vendors.py.
These tests assert only pipeline-level concerns the unit tests cannot: wiring
(detected vendors surface on the result), the score-independence invariant, and
JSON serialization.
"""
import pytest
import respx
from httpx import Response
from modules.antibot import analyze_antibot


class TestBehavioralVendorIntegration:
    """Pipeline-level behavioral vendor concerns (not detection logic)."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_analyze_antibot_with_datadome(self):
        """Wiring smoke: pipeline surfaces a detected vendor on result.behavioral_vendors."""
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
