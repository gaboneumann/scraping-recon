"""
tests/unit/test_classifier_reviews.py
Unit tests for E5 reviews provider detection (_detect_reviews_provider).
"""
from bs4 import BeautifulSoup
from modules.classifier import _detect_reviews_provider


class TestReviewsProviderDetection:
    """E5: External reviews provider detection."""

    def test_reviews_bazaarvoice(self):
        """Detect Bazaarvoice reviews widget."""
        html = """
        <script>
            window.BV = window.BV || {};
            BV.ui('rr', 'show_reviews', {
                productId: '123456'
            });
        </script>
        <div id="BVRRContainer"></div>
        """
        soup = BeautifulSoup(html, "lxml")
        result = _detect_reviews_provider(soup, html)
        assert result.found is True
        assert result.provider == "bazaarvoice"
        assert result.confidence in ("high", "medium")

    def test_reviews_yotpo(self):
        """Detect Yotpo reviews widget."""
        html = """
        <script>
            window.yotpo = yotpo;
            yotpoElement.init({merchantId: 'abc123'});
        </script>
        <div id="yotpo-reviews"></div>
        """
        soup = BeautifulSoup(html, "lxml")
        result = _detect_reviews_provider(soup, html)
        assert result.found is True
        assert result.provider == "yotpo"
        assert result.confidence in ("high", "medium")

    def test_reviews_trustpilot(self):
        """Detect Trustpilot reviews widget."""
        html = """
        <script>
            (function(w,d,s,r,h){
                w.TrustboxAPI=r;
                h=d.createElement(s);
                h.async=!0;
            })(window,document,'script',{},document.head);
        </script>
        <div class="trustbox">
            <iframe src="https://widget.trustpilot.com/..."></iframe>
        </div>
        """
        soup = BeautifulSoup(html, "lxml")
        result = _detect_reviews_provider(soup, html)
        assert result.found is True
        assert result.provider == "trustpilot"

    def test_reviews_ekomi(self):
        """Detect eKomi reviews widget."""
        html = """
        <script>
            window.eKomiIntegrationScript = {
                merchantId: '123456'
            };
        </script>
        <div id="ekomi-reviews"></div>
        """
        soup = BeautifulSoup(html, "lxml")
        result = _detect_reviews_provider(soup, html)
        assert result.found is True
        assert result.provider == "ekomi"

    def test_reviews_google(self):
        """Detect Google Customer Reviews widget."""
        html = """
        <script>
            window.GoogleCustomerReviews = {
                merchantId: '123456789'
            };
        </script>
        <div id="google-customer-reviews"></div>
        """
        soup = BeautifulSoup(html, "lxml")
        result = _detect_reviews_provider(soup, html)
        assert result.found is True
        assert result.provider == "google"
        assert result.confidence == "high"

    def test_reviews_internal(self):
        """Detect internal/native reviews section."""
        html = """
        <section class="reviews">
            <div class="review">
                <div class="rating">★★★★★</div>
                <p>Great product!</p>
            </div>
        </section>
        """
        soup = BeautifulSoup(html, "lxml")
        result = _detect_reviews_provider(soup, html)
        assert result.found is True
        assert result.provider == "internal"

    def test_reviews_no_provider(self):
        """Page with no reviews detected."""
        html = """
        <html>
            <body>
                <h1>Product</h1>
                <p>Description</p>
            </body>
        </html>
        """
        soup = BeautifulSoup(html, "lxml")
        result = _detect_reviews_provider(soup, html)
        assert result.found is False
        assert result.provider is None

    def test_reviews_multiple_providers(self):
        """Multiple widgets present (returns primary)."""
        html = """
        <script>
            window.BV = window.BV || {};
            window.yotpo = yotpo;
        </script>
        """
        soup = BeautifulSoup(html, "lxml")
        result = _detect_reviews_provider(soup, html)
        assert result.found is True
        assert result.provider in ("bazaarvoice", "yotpo")
