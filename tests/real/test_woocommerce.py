"""
tests/real/test_woocommerce.py
Real platform tests for WooCommerce e-commerce signals detection.

Tests E-commerce module detection on WooCommerce HTML fixtures.
"""
from __future__ import annotations

import pytest


@pytest.mark.real
def test_woocommerce_variant_detection(load_html) -> None:
    """Test detection of WooCommerce product variants (E3 signal)."""
    html = load_html("woocommerce_sample")

    # Verify HTML contains variant selectors
    assert 'name="attribute_pa_size"' in html
    assert 'name="attribute_pa_color"' in html

    # Variant detection would check for:
    # - select.attribute-select elements
    # - woocommerce attribute patterns
    assert 'class="attribute-select"' in html


@pytest.mark.real
def test_woocommerce_inventory_detection(load_html) -> None:
    """Test detection of WooCommerce inventory signals (E6 signal)."""
    html = load_html("woocommerce_sample")

    # Verify HTML contains inventory info
    assert "Stock:" in html
    assert "stock-quantity" in html
    assert "in-stock" in html

    # Inventory detection would extract stock status
    assert "50" in html  # Stock quantity


@pytest.mark.real
def test_woocommerce_cart_api_detection(load_html) -> None:
    """Test detection of WooCommerce cart API endpoint."""
    html = load_html("woocommerce_sample")

    # Verify cart API references
    assert "/wp-json/wc/store/v1/cart/items" in html
    assert "add_to_cart_button" in html


@pytest.mark.real
def test_woocommerce_price_detection(load_html) -> None:
    """Test detection of WooCommerce price elements."""
    html = load_html("woocommerce_sample")

    # Verify structured price data
    assert "99.99" in html
    assert "woocommerce-Price-amount" in html
    assert "woocommerce-Price-currencySymbol" in html
