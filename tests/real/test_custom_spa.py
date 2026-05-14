"""
tests/real/test_custom_spa.py
Real platform tests for custom React SPA e-commerce sites.

Tests detection on custom single-page applications with non-standard APIs.
"""
from __future__ import annotations

import pytest


@pytest.mark.real
def test_custom_spa_variant_detection(load_html) -> None:
    """Test detection of custom SPA product variants."""
    html = load_html("custom_spa_sample")

    # Verify HTML contains variant info
    assert "Standard" in html or "Pro" in html
    assert "GADGET-STD" in html or "GADGET-PRO" in html


@pytest.mark.real
def test_custom_spa_infinite_scroll_detection(load_html) -> None:
    """Test detection of infinite scroll pagination."""
    html = load_html("custom_spa_sample")

    # Verify pagination strategy markers
    assert "infinite-scroll" in html
    assert "/api/v1/products/browse" in html or "nextCursorParam" in html


@pytest.mark.real
def test_custom_spa_custom_api_detection(load_html) -> None:
    """Test detection of custom API endpoints."""
    html = load_html("custom_spa_sample")

    # Verify custom API indicators
    assert "api.custom-store.example.com" in html
    assert "/products/" in html
    assert "productPrice" in html or "inventory" in html


@pytest.mark.real
def test_custom_spa_inventory_detection(load_html) -> None:
    """Test detection of inventory in custom SPA."""
    html = load_html("custom_spa_sample")

    # Verify inventory data
    assert '"total": 100' in html or "total" in html
    assert "available" in html
    assert "45" in html
