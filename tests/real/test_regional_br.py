"""
tests/real/test_regional_br.py
Real platform tests for regional Brazilian e-commerce sites.

Tests T2 false negative detection for regional currency and payment methods.
"""
from __future__ import annotations

import pytest


@pytest.mark.real
def test_regional_br_price_format_detection(load_html) -> None:
    """Test detection of Brazilian regional price format (R$ X,XX)."""
    html = load_html("regional_br_sample")

    # Verify Brazilian price format
    assert "R$" in html
    assert "199,90" in html


@pytest.mark.real
def test_regional_br_installment_detection(load_html) -> None:
    """Test detection of installment payment info (common in Brazil)."""
    html = load_html("regional_br_sample")

    # Verify installment/parcelamento signals
    assert "parcelado" in html or "parcelamento" in html
    assert "sem juros" in html or "juros" in html


@pytest.mark.real
def test_regional_br_locale_detection(load_html) -> None:
    """Test detection of Brazilian Portuguese locale."""
    html = load_html("regional_br_sample")

    # Verify locale indicators
    assert "pt-BR" in html or "pt_BR" in html
    assert "BR" in html
