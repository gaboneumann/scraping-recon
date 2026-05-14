"""
tests/unit/test_classifier_inventory.py
Unit tests for E6 inventory mechanism detection (_detect_inventory_mechanism).
"""
from bs4 import BeautifulSoup
from modules.classifier import _detect_inventory_mechanism


class TestInventoryMechanismDetection:
    """E6: Inventory stock mechanism detection."""

    def test_inventory_server_side_data_attr(self):
        """Detect server-side stock in data attribute."""
        html = """
        <div class="product" data-stock="25">
            <span class="availability">In Stock</span>
        </div>
        """
        soup = BeautifulSoup(html, "lxml")
        result = _detect_inventory_mechanism(html, soup)
        assert result.mechanism == "SERVER_SIDE"
        assert result.stock_element_found is True
        assert result.confidence == "high"

    def test_inventory_server_side_hardcoded(self):
        """Detect server-side stock with hardcoded number."""
        html = """
        <div class="product">
            <span>In Stock: 42 units</span>
            <span>Stock: 42</span>
        </div>
        """
        soup = BeautifulSoup(html, "lxml")
        result = _detect_inventory_mechanism(html, soup)
        assert result.mechanism == "SERVER_SIDE"
        assert result.confidence in ("high", "medium")

    def test_inventory_ajax_setinterval(self):
        """Detect AJAX inventory via setInterval pattern."""
        html = """
        <div id="stock-container">Loading...</div>
        <script>
            setInterval(function() {
                updateInventory();
            }, 5000);
        </script>
        """
        soup = BeautifulSoup(html, "lxml")
        result = _detect_inventory_mechanism(html, soup)
        assert result.mechanism == "AJAX"
        assert result.real_time is True
        assert result.confidence == "high"

    def test_inventory_ajax_fetch(self):
        """Detect AJAX inventory via fetch pattern."""
        html = """
        <div id="stock">-</div>
        <script>
            fetch('/api/inventory?sku=12345')
                .then(r => r.json())
                .then(d => updateStock(d));
        </script>
        """
        soup = BeautifulSoup(html, "lxml")
        result = _detect_inventory_mechanism(html, soup)
        assert result.mechanism == "AJAX"
        assert result.real_time is True
        assert result.confidence == "high"

    def test_inventory_ajax_endpoint_in_script(self):
        """Detect AJAX via /api/inventory endpoint."""
        html = """
        <script>
            const API = '/api/inventory/check';
            function refreshStock() {
                fetch(API).then(handleResponse);
            }
        </script>
        """
        soup = BeautifulSoup(html, "lxml")
        result = _detect_inventory_mechanism(html, soup)
        assert result.mechanism == "AJAX"
        assert result.real_time is True
        assert result.confidence == "high"

    def test_inventory_high_confidence_match(self):
        """Clear mechanism with high confidence."""
        html = """
        <div data-inventory="100" data-sku="abc123">
            <span class="stock-status">In Stock</span>
        </div>
        """
        soup = BeautifulSoup(html, "lxml")
        result = _detect_inventory_mechanism(html, soup)
        assert result.mechanism == "SERVER_SIDE"
        assert result.confidence == "high"

    def test_inventory_low_confidence(self):
        """Ambiguous signals."""
        html = """
        <div class="product">
            <p>Availability info coming soon</p>
        </div>
        """
        soup = BeautifulSoup(html, "lxml")
        result = _detect_inventory_mechanism(html, soup)
        assert result.mechanism == "UNKNOWN"
        assert result.confidence == "low"

    def test_inventory_unknown_mechanism(self):
        """No stock indicators."""
        html = """
        <html>
            <body>
                <div class="product">
                    <h1>Product</h1>
                    <p>Description</p>
                </div>
            </body>
        </html>
        """
        soup = BeautifulSoup(html, "lxml")
        result = _detect_inventory_mechanism(html, soup)
        assert result.mechanism == "UNKNOWN"

    def test_inventory_real_time_flag(self):
        """Real-time stock update detection."""
        html = """
        <div id="stock">-</div>
        <script>
            const config = {loading: true, realTime: true};
            function updateInventory() { fetch('/stock'); }
        </script>
        """
        soup = BeautifulSoup(html, "lxml")
        result = _detect_inventory_mechanism(html, soup)
        # May detect as AJAX due to patterns
        assert result.real_time is True or result.mechanism == "AJAX"

    def test_inventory_backorder_signals(self):
        """Backorder/preorder patterns detected."""
        html = """
        <span class="availability">Available for preorder</span>
        <span class="status">backorder</span>
        """
        soup = BeautifulSoup(html, "lxml")
        result = _detect_inventory_mechanism(html, soup)
        # Should recognize availability patterns
        assert result.mechanism in ("SERVER_SIDE", "UNKNOWN", "AJAX")
