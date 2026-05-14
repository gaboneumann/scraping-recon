"""
tests/unit/test_classifier_price_reliability.py
Unit tests for price reliability scoring functions in classifier.py
"""
import pytest

from modules.classifier import (
    _extract_json_ld_price,
    _is_placeholder_price,
    _compute_price_score,
)


class TestExtractJsonLdPrice:
    """Tests for _extract_json_ld_price() helper."""

    def test_single_offer_with_price(self):
        """JSON-LD Product with single offers.price → extract numeric price."""
        html = '''
        <script type="application/ld+json">
        {"@type": "Product", "name": "Widget", "offers": {"price": "49.99"}}
        </script>
        '''
        result = _extract_json_ld_price(html)
        assert result == 49.99

    def test_array_offers_first_price(self):
        """JSON-LD Product with array of offers → extract first valid price."""
        html = '''
        <script type="application/ld+json">
        {"@type": "Product", "offers": [{"price": "25.00"}, {"price": "30.00"}]}
        </script>
        '''
        result = _extract_json_ld_price(html)
        assert result == 25.00

    def test_invalid_json_returns_none(self):
        """Malformed JSON-LD → silently skip, return None."""
        html = '''
        <script type="application/ld+json">
        {"@type": "Product", "offers": {invalid json}
        </script>
        '''
        result = _extract_json_ld_price(html)
        assert result is None

    def test_no_product_type_returns_none(self):
        """JSON-LD without @type Product → return None."""
        html = '''
        <script type="application/ld+json">
        {"@type": "Organization", "name": "Acme"}
        </script>
        '''
        result = _extract_json_ld_price(html)
        assert result is None

    def test_no_json_ld_returns_none(self):
        """HTML with no JSON-LD tags → return None."""
        html = '<html><body>No structured data</body></html>'
        result = _extract_json_ld_price(html)
        assert result is None

    def test_numeric_price_as_int(self):
        """JSON-LD with numeric price (int) → convert to float."""
        html = '''
        <script type="application/ld+json">
        {"@type": "Product", "offers": {"price": 99}}
        </script>
        '''
        result = _extract_json_ld_price(html)
        assert result == 99.0


class TestIsPlaceholderPrice:
    """Tests for _is_placeholder_price() helper."""

    def test_zero_patterns_are_placeholder(self):
        """'0', '0.00', '0,00' → True."""
        assert _is_placeholder_price("0") is True
        assert _is_placeholder_price("0.00") is True
        assert _is_placeholder_price("0,00") is True
        assert _is_placeholder_price("00") is True

    def test_contact_call_patterns_are_placeholder(self):
        """'Contact', 'Call for price', 'Contact seller' → True."""
        assert _is_placeholder_price("contact") is True
        assert _is_placeholder_price("Contact") is True
        assert _is_placeholder_price("call for price") is True
        assert _is_placeholder_price("Call for Price") is True

    def test_unavailable_patterns_are_placeholder(self):
        """'TBD', 'N/A', 'NA', '--', '?' → True."""
        assert _is_placeholder_price("tbd") is True
        assert _is_placeholder_price("TBD") is True
        assert _is_placeholder_price("n/a") is True
        assert _is_placeholder_price("N/A") is True
        assert _is_placeholder_price("na") is True
        assert _is_placeholder_price("--") is True
        assert _is_placeholder_price("-") is False
        assert _is_placeholder_price("?") is True

    def test_whitespace_tolerance(self):
        """'  TBD  ', ' 0 ' → True (whitespace ignored)."""
        assert _is_placeholder_price("  tbd  ") is True
        assert _is_placeholder_price("  0  ") is True
        assert _is_placeholder_price(" call for price ") is True

    def test_real_prices_not_placeholder(self):
        """'29.99', '100', '$50.00', '€35,50' → False."""
        assert _is_placeholder_price("29.99") is False
        assert _is_placeholder_price("100") is False
        assert _is_placeholder_price("50.00") is False
        assert _is_placeholder_price("35,50") is False

    def test_empty_string_not_placeholder(self):
        """'' or None → False."""
        assert _is_placeholder_price("") is False

    def test_currency_symbols_with_real_price(self):
        """'$29.99', '€50' → False (real prices with currency)."""
        assert _is_placeholder_price("$29.99") is False
        assert _is_placeholder_price("€50") is False


class TestComputePriceScore:
    """Tests for _compute_price_score() helper."""

    def test_json_ld_real_price_returns_90(self):
        """JSON-LD with real price → 90."""
        score = _compute_price_score(
            json_ld_price=29.99,
            html_price_text=None,
            signal_count=1
        )
        assert score == 90

    def test_json_ld_placeholder_returns_30(self):
        """JSON-LD with placeholder price → 30."""
        score = _compute_price_score(
            json_ld_price=0.0,
            html_price_text=None,
            signal_count=1
        )
        assert score == 30

    def test_html_real_price_returns_80(self):
        """HTML visible price with real value → 80."""
        score = _compute_price_score(
            json_ld_price=None,
            html_price_text="$29.99",
            signal_count=1
        )
        assert score == 80

    def test_html_placeholder_returns_25(self):
        """HTML visible price but placeholder → 25."""
        score = _compute_price_score(
            json_ld_price=None,
            html_price_text="Contact seller",
            signal_count=1
        )
        assert score == 25

    def test_price_signals_only_returns_40(self):
        """Price signals detected but no actual price text → 40."""
        score = _compute_price_score(
            json_ld_price=None,
            html_price_text=None,
            signal_count=5
        )
        assert score == 40

    def test_no_price_signals_returns_none(self):
        """No price signals anywhere → None."""
        score = _compute_price_score(
            json_ld_price=None,
            html_price_text=None,
            signal_count=0
        )
        assert score is None

    def test_json_ld_takes_priority(self):
        """JSON-LD present → return JSON-LD score even if HTML also present."""
        score = _compute_price_score(
            json_ld_price=99.99,
            html_price_text="$29.99",
            signal_count=2
        )
        assert score == 90  # JSON-LD takes priority

    def test_html_empty_string_price_returns_40(self):
        """HTML price text is empty string → treat as no text, return 40."""
        score = _compute_price_score(
            json_ld_price=None,
            html_price_text="",
            signal_count=1
        )
        assert score == 40
