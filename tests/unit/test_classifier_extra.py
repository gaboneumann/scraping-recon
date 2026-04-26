"""
tests/unit/test_classifier_extra.py
Additional pure-function coverage for modules/classifier.py.
Covers: _classify() SSR ecommerce branches, Shopify/BigCommerce, Salesforce CC,
_detect_infrastructure(), _detect_security_headers(), _detect_locales(),
_estimate_crawl_scope(), _detect_cdn().
"""
from __future__ import annotations

import pytest
from bs4 import BeautifulSoup

from modules.classifier import (
    _classify,
    _detect_cdn,
    _detect_ecommerce_signals,
    _detect_infrastructure,
    _detect_locales,
    _detect_security_headers,
    _estimate_crawl_scope,
    _detect_structured_data,
    _detect_cms,
    _compute_content_ratio,
)


# ─────────────────────────────────────────────
# _classify() — SSR e-commerce branches (lines 498-508)
# ─────────────────────────────────────────────

@pytest.mark.parametrize("cms, content_ratio, expected_type, expected_confidence", [
    ("WooCommerce", 0.20, "HYBRID", "HIGH"),
    ("WooCommerce", 0.10, "HYBRID", "MEDIUM"),
    ("Shopify",     0.10, "HYBRID", "HIGH"),
    ("BigCommerce", 0.10, "HYBRID", "HIGH"),
    ("Salesforce CC", 0.10, "HYBRID", "MEDIUM"),
])
def test_classify_ssr_ecommerce(cms, content_ratio, expected_type, expected_confidence) -> None:
    """SSR e-commerce / SaaS CMS platforms resolve to HYBRID."""
    result_type, confidence = _classify(content_ratio, [], cms)
    assert result_type == expected_type
    assert confidence == expected_confidence


def test_classify_headless_dynamic() -> None:
    """Next.js with ratio < 0.10 → DYNAMIC MEDIUM."""
    result_type, confidence = _classify(0.07, ["Next.js"], None)
    assert result_type == "DYNAMIC"
    assert confidence == "MEDIUM"


def test_classify_unknown_mid_range() -> None:
    """content_ratio between 0.05 and 0.08, no special signals → UNKNOWN."""
    result_type, _ = _classify(0.06, [], None)
    assert result_type == "UNKNOWN"


def test_classify_static_medium_confidence() -> None:
    """content_ratio 0.08-0.15, no frameworks → STATIC MEDIUM."""
    result_type, confidence = _classify(0.10, [], None)
    assert result_type == "STATIC"
    assert confidence == "MEDIUM"


# ─────────────────────────────────────────────
# _detect_cdn()
# ─────────────────────────────────────────────

def test_detect_cdn_fastly() -> None:
    """x-served-by header → Fastly CDN."""
    cdn = _detect_cdn({"X-Served-By": "cache-xyz"})
    assert cdn == "Fastly"


def test_detect_cdn_akamai() -> None:
    """x-check-cacheable header → Akamai."""
    cdn = _detect_cdn({"x-check-cacheable": "YES"})
    assert cdn == "Akamai"


def test_detect_cdn_aws() -> None:
    """x-amz-cf-id header → AWS."""
    cdn = _detect_cdn({"x-amz-cf-id": "abc123=="})
    assert cdn == "AWS"


def test_detect_cdn_none() -> None:
    """No known CDN headers → None."""
    cdn = _detect_cdn({"server": "nginx"})
    assert cdn is None


# ─────────────────────────────────────────────
# _detect_infrastructure()
# ─────────────────────────────────────────────

def test_detect_infrastructure_x_powered_by() -> None:
    """x-powered-by header → added to infra list."""
    infra = _detect_infrastructure({"X-Powered-By": "Express"})
    assert "Express" in infra


def test_detect_infrastructure_empty() -> None:
    """No infra headers → empty list."""
    infra = _detect_infrastructure({"content-type": "text/html"})
    assert infra == []


# ─────────────────────────────────────────────
# _detect_security_headers()
# ─────────────────────────────────────────────

def test_detect_security_headers_all_set() -> None:
    """All security headers present → all True."""
    headers = {
        "content-security-policy": "default-src 'self'",
        "strict-transport-security": "max-age=31536000",
        "x-frame-options": "DENY",
        "x-content-type-options": "nosniff",
    }
    result = _detect_security_headers(headers)
    assert result.csp is True
    assert result.hsts is True
    assert result.x_frame_options is True
    assert result.x_content_type_options is True
    assert result.csp_blocks_inline is True  # no unsafe-inline


def test_detect_security_headers_csp_unsafe_inline() -> None:
    """CSP with 'unsafe-inline' → csp_blocks_inline=False."""
    headers = {"content-security-policy": "default-src 'self' 'unsafe-inline'"}
    result = _detect_security_headers(headers)
    assert result.csp is True
    assert result.csp_blocks_inline is False


def test_detect_security_headers_none() -> None:
    """No security headers → all False."""
    result = _detect_security_headers({"content-type": "text/html"})
    assert result.csp is False
    assert result.hsts is False
    assert result.x_frame_options is False


# ─────────────────────────────────────────────
# _detect_locales()
# ─────────────────────────────────────────────

def test_detect_locales_hreflang() -> None:
    """hreflang alternate links → locales detected."""
    html = (
        '<html><head>'
        '<link rel="alternate" hreflang="en" href="/en/">'
        '<link rel="alternate" hreflang="fr" href="/fr/">'
        '</head></html>'
    )
    soup = BeautifulSoup(html, "lxml")
    locales = _detect_locales(soup)
    assert "en" in locales
    assert "fr" in locales


def test_detect_locales_url_path() -> None:
    """Links with /en/ /es/ path prefixes → locales from path."""
    html = (
        '<html><body>'
        '<a href="/en/about">About EN</a>'
        '<a href="/es/acerca">Acerca ES</a>'
        '</body></html>'
    )
    soup = BeautifulSoup(html, "lxml")
    locales = _detect_locales(soup)
    # Should detect en and es from URL path pattern
    assert len(locales) >= 1


def test_detect_locales_none() -> None:
    """No locale signals → empty list."""
    soup = BeautifulSoup("<html><body><p>Hello</p></body></html>", "lxml")
    locales = _detect_locales(soup)
    assert locales == []


# ─────────────────────────────────────────────
# _estimate_crawl_scope()
# ─────────────────────────────────────────────

def test_estimate_crawl_scope_small() -> None:
    """Fewer than 20 links → '<50'."""
    links = "".join(f'<a href="/page-{i}">Page {i}</a>' for i in range(5))
    soup = BeautifulSoup(f"<html><body>{links}</body></html>", "lxml")
    count, estimated = _estimate_crawl_scope(soup, "https://example.com")
    assert count == 5
    assert estimated == "<50"


def test_estimate_crawl_scope_medium() -> None:
    """50-499 links → '50-500'."""
    links = "".join(f'<a href="/page-{i}">Page {i}</a>' for i in range(60))
    soup = BeautifulSoup(f"<html><body>{links}</body></html>", "lxml")
    count, estimated = _estimate_crawl_scope(soup, "https://example.com")
    assert estimated == "50-500"


def test_estimate_crawl_scope_large() -> None:
    """100-499 links → '50-500' or '500-5000'."""
    links = "".join(f'<a href="/page-{i}">Page {i}</a>' for i in range(120))
    soup = BeautifulSoup(f"<html><body>{links}</body></html>", "lxml")
    count, estimated = _estimate_crawl_scope(soup, "https://example.com")
    assert estimated in ("50-500", "500-5000")


def test_estimate_crawl_scope_excludes_external() -> None:
    """External links excluded from count."""
    html = (
        '<html><body>'
        '<a href="/internal">Internal</a>'
        '<a href="https://other.com/page">External</a>'
        '</body></html>'
    )
    soup = BeautifulSoup(html, "lxml")
    count, _ = _estimate_crawl_scope(soup, "https://example.com")
    assert count == 1  # only /internal


# ─────────────────────────────────────────────
# _detect_ecommerce_signals() cart architecture branches
# ─────────────────────────────────────────────

def test_ecommerce_cart_woocommerce_fragments() -> None:
    """wc-cart-fragments in HTML → cart_architecture=AJAX_FRAGMENTS."""
    html = '<html><body><script>wc-cart-fragments</script></body></html>'
    soup = BeautifulSoup(html, "lxml")
    result = _detect_ecommerce_signals(html, soup, "WooCommerce")
    assert result.cart_architecture == "AJAX_FRAGMENTS"


def test_ecommerce_cart_shopify_api() -> None:
    """Shopify /cart.js → cart_architecture=AJAX_API."""
    html = '<html><body><script src="/cart.js"></script></body></html>'
    soup = BeautifulSoup(html, "lxml")
    result = _detect_ecommerce_signals(html, soup, "Shopify")
    assert result.cart_architecture == "AJAX_API"


def test_ecommerce_cart_magento_section() -> None:
    """magentoSectionData → cart_architecture=SECTION_CACHE."""
    html = '<html><body><script>var magentoSectionData = {};</script></body></html>'
    soup = BeautifulSoup(html, "lxml")
    result = _detect_ecommerce_signals(html, soup, "Magento")
    assert result.cart_architecture == "SECTION_CACHE"


def test_ecommerce_no_signals() -> None:
    """Clean blog page → is_ecommerce=False."""
    html = '<html><body><p>Hello world</p></body></html>'
    soup = BeautifulSoup(html, "lxml")
    result = _detect_ecommerce_signals(html, soup, None)
    assert result.is_ecommerce is False
    assert result.price_mechanism == "UNKNOWN"
    assert result.cart_architecture == "UNKNOWN"


# ─────────────────────────────────────────────
# _compute_content_ratio()
# ─────────────────────────────────────────────

def test_compute_content_ratio_high() -> None:
    """Mostly text → high ratio."""
    html = "<html><body>" + "Hello world. " * 100 + "</body></html>"
    soup = BeautifulSoup(html, "lxml")
    ratio = _compute_content_ratio(soup, html)
    assert ratio > 0.3


def test_compute_content_ratio_empty() -> None:
    """Empty html → no division by zero."""
    ratio = _compute_content_ratio(BeautifulSoup("", "lxml"), "")
    assert ratio == 0.0


# ─────────────────────────────────────────────
# _detect_structured_data() — list @type and list JSON-LD items
# ─────────────────────────────────────────────

def test_detect_structured_data_list_type() -> None:
    """JSON-LD with @type as list → all types captured."""
    import json
    data = {"@type": ["Person", "Author"], "name": "John"}
    html = f'<html><head><script type="application/ld+json">{json.dumps(data)}</script></head></html>'
    soup = BeautifulSoup(html, "lxml")
    result = _detect_structured_data(soup, html)
    assert "Person" in result.schema_types
    assert "Author" in result.schema_types


def test_detect_structured_data_list_items() -> None:
    """JSON-LD that is a list of objects → types from all items."""
    import json
    data = [{"@type": "Product", "name": "A"}, {"@type": "Offer", "name": "B"}]
    html = f'<html><head><script type="application/ld+json">{json.dumps(data)}</script></head></html>'
    soup = BeautifulSoup(html, "lxml")
    result = _detect_structured_data(soup, html)
    assert "Product" in result.schema_types
    assert "Offer" in result.schema_types


def test_detect_structured_data_opengraph() -> None:
    """og: property tag → opengraph_found=True."""
    html = '<html><head><meta property="og:title" content="Test"></head></html>'
    soup = BeautifulSoup(html, "lxml")
    result = _detect_structured_data(soup, html)
    assert result.opengraph_found is True


def test_detect_structured_data_microdata() -> None:
    """itemscope attribute → microdata_found=True."""
    html = '<html><body><div itemscope itemtype="http://schema.org/Person"></div></body></html>'
    soup = BeautifulSoup(html, "lxml")
    result = _detect_structured_data(soup, html)
    assert result.microdata_found is True


# ─────────────────────────────────────────────
# _detect_cms() — more CMS signals
# ─────────────────────────────────────────────

def test_detect_cms_wix_header() -> None:
    """x-wix-request-id header → Wix."""
    cms = _detect_cms("", {"x-wix-request-id": "abc-123"})
    assert cms == "Wix"


def test_detect_cms_shopify_html() -> None:
    """cdn.shopify.com in HTML → Shopify."""
    cms = _detect_cms('<script src="https://cdn.shopify.com/s/files/x.js"></script>', {})
    assert cms == "Shopify"


def test_detect_cms_none() -> None:
    """No CMS signals → None."""
    cms = _detect_cms("<html><body>Clean page</body></html>", {})
    assert cms is None
