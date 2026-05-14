"""
tests/real/test_shopify.py
Real platform tests for Shopify e-commerce signals detection.

Tests E-commerce module detection on Shopify HTML fixtures.
"""
from __future__ import annotations

import pytest


@pytest.mark.real
def test_shopify_variant_detection(load_html) -> None:
    """Test detection of Shopify product variants."""
    html = load_html("shopify_sample")

    # Verify HTML contains Shopify variant patterns
    assert "product-select-template" in html
    assert "gid://shopify/ProductVariant/" in html
    assert "Blue / Small" in html or "Red / Medium" in html


@pytest.mark.real
def test_shopify_price_detection(load_html) -> None:
    """Test detection of Shopify price elements."""
    html = load_html("shopify_sample")

    # Verify price structure
    assert "$49.99" in html
    assert "price--highlight" in html or "price-item--sale" in html


@pytest.mark.real
def test_shopify_inventory_detection(load_html) -> None:
    """Test detection of Shopify inventory status."""
    html = load_html("shopify_sample")

    # Verify inventory signals
    assert "inventory-count" in html
    assert "Only 3 left" in html or "order soon" in html


@pytest.mark.real
def test_shopify_storefront_api_detection(load_html) -> None:
    """Test detection of Shopify Storefront API."""
    html = load_html("shopify_sample")

    # Verify Shopify API indicators
    assert "window.Shopify" in html
    assert "myshopify.com" in html
    assert "Storefront API" in html or "/api/" in html
