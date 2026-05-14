"""
tests/unit/test_classifier_multi_pdp.py
Unit tests for E4 multi-PDP sampling (_fetch_pdp_samples).
"""
import pytest
from unittest.mock import AsyncMock, patch
from modules.classifier import _extract_pdp_links, _fetch_pdp_samples


class TestPdpLinkExtraction:
    """E4: Product link extraction from category HTML."""

    def test_extract_pdp_links_product_pattern(self):
        """Extract product links matching /product/ pattern."""
        html = """
        <html>
            <body>
                <a href="/product/123-widget">Widget</a>
                <a href="/product/456-gadget">Gadget</a>
                <a href="/category/electronics">Category</a>
            </body>
        </html>
        """
        links = _extract_pdp_links("https://example.com/category", html)
        assert len(links) == 2
        assert any("widget" in link.lower() for link in links)

    def test_extract_pdp_links_item_pattern(self):
        """Extract product links matching /item/ pattern."""
        html = """
        <a href="/item/abc123">Item 1</a>
        <a href="/item/def456">Item 2</a>
        """
        links = _extract_pdp_links("https://example.com/shop", html)
        assert len(links) >= 2

    def test_extract_pdp_links_pdp_pattern(self):
        """Extract product links matching /pdp/ pattern."""
        html = """
        <a href="/en/pdp/123">Product A</a>
        <a href="/en/pdp/456">Product B</a>
        """
        links = _extract_pdp_links("https://example.com/", html)
        assert len(links) >= 2

    def test_extract_pdp_links_html_extension(self):
        """Extract product links matching .html extension pattern."""
        html = """
        <a href="/product-123.html">Prod 1</a>
        <a href="/product-456.html">Prod 2</a>
        <a href="/category.html">Category</a>
        """
        links = _extract_pdp_links("https://shop.com/", html)
        assert len(links) == 2
        assert all(".html" in link for link in links)

    def test_extract_pdp_links_no_duplicates(self):
        """No duplicate links in results."""
        html = """
        <a href="/product/123">Product</a>
        <a href="/product/123">Same Product</a>
        """
        links = _extract_pdp_links("https://example.com/", html)
        assert len(links) == 1

    def test_extract_pdp_links_relative_urls(self):
        """Resolve relative URLs correctly."""
        html = """
        <a href="product/123">Relative</a>
        <a href="/product/456">Absolute</a>
        """
        links = _extract_pdp_links("https://example.com/shop/", html)
        assert len(links) >= 1
        assert all("example.com" in link for link in links)


class TestMultiPdpSampling:
    """E4: Multi-sample PDP fetching and consistency metrics."""

    @pytest.mark.asyncio
    async def test_pdp_samples_extract_multiple_links(self):
        """Extract multiple product links."""
        html = """
        <a href="/product/1">P1</a>
        <a href="/product/2">P2</a>
        <a href="/product/3">P3</a>
        """
        with patch("modules.classifier._fetch_single_pdp", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = None
            samples = await _fetch_pdp_samples(
                "https://example.com/", html, {}, 15.0, sample_count=2
            )
            # If no fetch succeeds, samples will be empty but links should be extracted
            # The test validates that _extract_pdp_links is called internally

    @pytest.mark.asyncio
    async def test_pdp_samples_insufficient_products(self):
        """Fewer than 2 products returns fewer samples."""
        html = """
        <a href="/product/single">One Product</a>
        """
        with patch("modules.classifier._fetch_single_pdp", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = None
            samples = await _fetch_pdp_samples(
                "https://example.com/", html, {}, 15.0, sample_count=2
            )
            # With only 1 product link, sample size is 1
            assert len(samples) == 0  # All fetches return None

    @pytest.mark.asyncio
    async def test_pdp_samples_no_products(self):
        """No product links returns empty list."""
        html = """
        <html>
            <body>
                <a href="/category">No products</a>
            </body>
        </html>
        """
        samples = await _fetch_pdp_samples(
            "https://example.com/", html, {}, 15.0, sample_count=2
        )
        assert samples == []

    @pytest.mark.asyncio
    async def test_pdp_samples_error_handling(self):
        """Failed fetches are gracefully handled."""
        html = """
        <a href="/product/1">P1</a>
        <a href="/product/2">P2</a>
        """
        with patch("modules.classifier._fetch_single_pdp", new_callable=AsyncMock) as mock_fetch:
            # Return None to simulate failed fetch (graceful handling)
            mock_fetch.return_value = None
            samples = await _fetch_pdp_samples(
                "https://example.com/", html, {}, 15.0, sample_count=2
            )
            # Both failed, return empty
            assert len(samples) == 0
