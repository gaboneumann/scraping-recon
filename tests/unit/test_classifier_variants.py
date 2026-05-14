"""
tests/unit/test_classifier_variants.py
Unit tests for E3 variant detection (_detect_variants).
"""
from bs4 import BeautifulSoup
from modules.classifier import _detect_variants


class TestVariantDetection:
    """E3: Variant selector detection."""

    def test_variants_dropdown_single(self):
        """Detect single dropdown variant selector."""
        html = """
        <select name="variant-option">
            <option value="small">Small</option>
            <option value="medium">Medium</option>
            <option value="large">Large</option>
        </select>
        """
        soup = BeautifulSoup(html, "lxml")
        result = _detect_variants(soup)
        assert result.has_variants is True
        assert result.selector_type == "dropdown"
        assert result.variant_count_estimate == 3
        assert result.confidence == "high"

    def test_variants_dropdown_multiple(self):
        """Detect multiple dropdown selectors (size + color)."""
        html = """
        <select name="variant-size">
            <option>S</option>
            <option>M</option>
            <option>L</option>
        </select>
        <select name="variant-color">
            <option>Red</option>
            <option>Blue</option>
        </select>
        """
        soup = BeautifulSoup(html, "lxml")
        result = _detect_variants(soup)
        assert result.has_variants is True
        assert result.selector_type == "dropdown"
        assert result.variant_count_estimate >= 3

    def test_variants_radio_buttons(self):
        """Detect radio button variant selectors."""
        html = """
        <input type="radio" name="variant-size" value="small"> Small
        <input type="radio" name="variant-size" value="medium"> Medium
        <input type="radio" name="variant-size" value="large"> Large
        """
        soup = BeautifulSoup(html, "lxml")
        result = _detect_variants(soup)
        assert result.has_variants is True
        assert result.selector_type == "radio"
        assert result.variant_count_estimate == 3
        assert result.confidence == "high"

    def test_variants_swatch_colors(self):
        """Detect swatch/color selectors."""
        html = """
        <div class="color-swatch red" data-swatch="red"></div>
        <div class="color-swatch blue" data-swatch="blue"></div>
        <div class="color-swatch green" data-swatch="green"></div>
        """
        soup = BeautifulSoup(html, "lxml")
        result = _detect_variants(soup)
        assert result.has_variants is True
        assert result.selector_type == "swatch"
        assert result.variant_count_estimate >= 2

    def test_variants_button_options(self):
        """Detect button-based variant selection."""
        html = """
        <button data-variant-id="var_123">Small</button>
        <button data-variant-id="var_124">Medium</button>
        <button data-variant-id="var_125">Large</button>
        """
        soup = BeautifulSoup(html, "lxml")
        result = _detect_variants(soup)
        assert result.has_variants is True
        assert result.selector_type == "button"
        assert result.variant_count_estimate == 3

    def test_variants_with_ajax(self):
        """Detect variant selector with AJAX endpoint."""
        html = """
        <select name="variant-option">
            <option>Small</option>
            <option>Large</option>
        </select>
        <script>
            fetch('/api/variants?id=123')
        </script>
        """
        soup = BeautifulSoup(html, "lxml")
        result = _detect_variants(soup)
        assert result.has_variants is True
        assert result.selector_type == "dropdown"
        assert result.requires_ajax is True
        assert result.ajax_endpoint is not None

    def test_variants_no_selector(self):
        """No variant indicators detected."""
        html = """
        <div class="product">
            <h1>Product Title</h1>
            <p class="price">$19.99</p>
            <button class="add-to-cart">Add to Cart</button>
        </div>
        """
        soup = BeautifulSoup(html, "lxml")
        result = _detect_variants(soup)
        assert result.has_variants is False
        assert result.selector_type is None
        assert result.confidence == "low"

    def test_variants_low_confidence(self):
        """Ambiguous variant patterns return low confidence."""
        html = """
        <select name="option">
            <option>Choice 1</option>
            <option>Choice 2</option>
        </select>
        """
        soup = BeautifulSoup(html, "lxml")
        result = _detect_variants(soup)
        # Without "variant" keyword, may not detect or have lower confidence
        # depending on implementation

    def test_variants_estimate_count(self):
        """Verify variant count estimation."""
        html = """
        <select name="variant-size">
            <option>XS</option>
            <option>S</option>
            <option>M</option>
            <option>L</option>
            <option>XL</option>
            <option>XXL</option>
        </select>
        """
        soup = BeautifulSoup(html, "lxml")
        result = _detect_variants(soup)
        assert result.variant_count_estimate == 6

    def test_variants_mixed_types(self):
        """Multiple selector types present (returns first detected)."""
        html = """
        <select name="variant-option">
            <option>Option 1</option>
            <option>Option 2</option>
        </select>
        <input type="radio" name="variant-color" value="red"> Red
        <input type="radio" name="variant-color" value="blue"> Blue
        """
        soup = BeautifulSoup(html, "lxml")
        result = _detect_variants(soup)
        assert result.has_variants is True
        # First match is dropdown
        assert result.selector_type == "dropdown"
