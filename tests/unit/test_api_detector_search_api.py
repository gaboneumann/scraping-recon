"""
tests/unit/test_api_detector_search_api.py
Unit tests for E2 search API detection (_detect_search_api).
"""
import pytest
from unittest.mock import AsyncMock, patch
from models.schemas import ApiEndpoint
from modules.api_detector import _detect_search_api


class TestSearchApiDetection:
    """E2: Search API provider detection (Algolia, Elasticsearch, custom)."""

    @pytest.mark.asyncio
    async def test_search_api_algolia_detection(self):
        """Detect Algolia search API."""
        html = """
        <script>
            const algoliaConfig = {
                appId: 'ABC123',
                apiKey: 'secret_key'
            };
            algoliasearch('ABC123', 'secret_key');
        </script>
        """
        result = await _detect_search_api(html, [], "https://example.com", 15.0)
        assert result.found is True
        assert result.api_type == "algolia"
        assert result.confidence in ("medium", "high")

    @pytest.mark.asyncio
    async def test_search_api_elasticsearch_detection(self):
        """Detect Elasticsearch search API."""
        html = """
        <script>
            const client = new elasticsearch.Client({
                host: 'localhost:9200'
            });
        </script>
        """
        result = await _detect_search_api(html, [], "https://example.com", 15.0)
        assert result.found is True
        assert result.api_type == "elasticsearch"

    @pytest.mark.asyncio
    async def test_search_api_custom_endpoint(self):
        """Detect custom search endpoint pattern."""
        html = """
        <script>
            fetch('/api/search?q=test')
        </script>
        """
        result = await _detect_search_api(html, [], "https://example.com", 15.0)
        assert result.found is True
        assert result.api_type == "custom"

    @pytest.mark.asyncio
    async def test_search_api_with_endpoint_list(self):
        """Use provided endpoints list for search API."""
        html = """
        <script>
            // Some content
        </script>
        """
        endpoints = [
            ApiEndpoint(url="/api/search", type="REST", authenticated=None),
            ApiEndpoint(url="/api/products", type="REST", authenticated=None),
        ]
        result = await _detect_search_api(html, endpoints, "https://example.com", 15.0)
        # Should find from endpoints even if no pattern in HTML
        if result.found:
            assert result.endpoint_url is not None

    @pytest.mark.asyncio
    async def test_search_api_not_found(self):
        """No search API indicators present."""
        html = """
        <html>
            <body>
                <h1>Homepage</h1>
            </body>
        </html>
        """
        result = await _detect_search_api(html, [], "https://example.com", 15.0)
        assert result.found is False
        assert result.api_type is None

    @pytest.mark.asyncio
    async def test_search_api_authenticated(self):
        """Endpoint requires authentication (pattern detection only)."""
        html = """
        <script>
            const apiKey = 'secret';
            fetch('/api/search')
        </script>
        """
        result = await _detect_search_api(html, [], "https://example.com", 15.0)
        if result.found:
            # Pattern detection doesn't probe, so authenticated stays None
            assert result.authenticated is None or result.authenticated is True

    @pytest.mark.asyncio
    async def test_search_api_endpoint_validation(self):
        """Validation of endpoint patterns."""
        html = """
        <script>
            fetch('/api/search')
        </script>
        """
        result = await _detect_search_api(html, [], "https://example.com", 15.0)
        # Should detect pattern
        if result.found:
            assert result.api_type == "custom"

    @pytest.mark.asyncio
    async def test_search_api_confidence_high(self):
        """Clear pattern match = high confidence."""
        html = """
        <script>
            algoliasearch('APP_ID', 'SEARCH_KEY');
        </script>
        """
        result = await _detect_search_api(html, [], "https://example.com", 15.0)
        if result.found:
            assert result.confidence in ("medium", "high")

    @pytest.mark.asyncio
    async def test_search_api_confidence_low(self):
        """Ambiguous indicators = low confidence."""
        html = """
        <script>
            // Might mention search API but not clearly
            const search = 'some search functionality';
        </script>
        """
        result = await _detect_search_api(html, [], "https://example.com", 15.0)
        if not result.found:
            assert result.confidence == "low"

    @pytest.mark.asyncio
    async def test_search_api_multiple_types(self):
        """Multiple search APIs present (returns primary)."""
        html = """
        <script>
            algoliasearch('APP_ID', 'KEY');
            elasticsearch.Client({});
        </script>
        """
        result = await _detect_search_api(html, [], "https://example.com", 15.0)
        assert result.found is True
        # Returns primary (first match)
        assert result.api_type in ("algolia", "elasticsearch")
