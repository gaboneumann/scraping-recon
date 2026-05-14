"""
modules/classifier.py
Classifies a web page as STATIC, DYNAMIC, HYBRID, API_DRIVEN, or UNKNOWN.
Detects JS frameworks, CMS, CDN, structured data, security headers,
locales, mobile content parity, and crawl scope estimate.
"""
from __future__ import annotations

import json
import logging
import re
import time
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from models.schemas import (
    ClassifierResult,
    EcommerceSignals,
    PdpSampleResult,
    SecurityHeadersResult,
    StructuredDataResult,
)
from utils.http import UA_CHROME, make_request, compare_mobile_desktop

logger = logging.getLogger(__name__)

FRAMEWORK_SIGNALS: dict[str, list[str]] = {
    "React":   ["data-reactroot", "__REACT_QUERY_STATE__", "_next/"],
    "Next.js": ["__NEXT_DATA__", "/_next/static/"],
    "Vue":     ["data-v-", "__vue__", "vue.runtime"],
    "Angular": ["ng-version", "ng-app"],
    "Svelte":  ["__svelte", "svelte-"],
    "Nuxt":    ["__nuxt", "_nuxt/"],
    "Ember":   ["EmberENV"],
    "HTMX":    ["hx-get", "hx-post"],
    "Gatsby":  ["gatsby-focus-wrapper"],
    "Remix":   ["__remixContext"],
    "Astro":   ["data-astro-cid"],
}

CMS_SIGNALS: dict[str, dict[str, list[str]]] = {
    "WordPress":   {"html": ["/wp-content/", "/wp-includes/", "wp-json"], "headers": []},
    "Shopify":     {"html": ["cdn.shopify.com", "Shopify.theme"], "headers": []},
    "Drupal":      {"html": ["Drupal.settings"], "headers": ["x-drupal-cache"]},
    "Joomla":      {"html": ["/media/jui/"], "headers": []},
    "Wix":         {"html": [], "headers": ["x-wix-request-id"]},
    "Squarespace": {"html": ["squarespace.com"], "headers": []},
    "Webflow":     {"html": ["data-wf-"], "headers": []},
    # E-commerce platforms
    "WooCommerce":   {"html": ["woocommerce", "wc-cart-fragments", "WC.cart",
                               "woocommerce-js-cookie"], "headers": []},
    "Magento":       {"html": ["Mage.Cookies", "data-mage-init", "magentoSectionData",
                               "MAGE_", "mage/cookies"],
                      "headers": ["x-magento-cache-id", "x-magento-tags"]},
    "BigCommerce":   {"html": ["BCData", "bigcommerce", "bc-sf-filter"], "headers": []},
    "PrestaShop":    {"html": ["prestashop", "id_product", "id_category_default"],
                      "headers": ["x-prestashop"]},
    "Salesforce CC": {"html": ["SiteGenesis", "SFRA", "sfra", "dw.ac", "demandware"],
                      "headers": ["x-dw-request-id"]},
    "SAP Hybris":    {"html": ["hybris", "ACC.", "electronics/en/USD"], "headers": []},
    "OpenCart":      {"html": ["catalog/view/javascript/opencart"], "headers": []},
    "VTEX":          {"html": ["vtex.com", "__RUNTIME__", "vtex-render"],
                      "headers": ["x-vtex-cache-status"]},
}

ECOMMERCE_PLATFORMS: set[str] = {
    "Shopify", "WooCommerce", "Magento", "BigCommerce", "PrestaShop",
    "Salesforce CC", "SAP Hybris", "OpenCart", "VTEX",
}

ECOMMERCE_SIGNALS: dict[str, list[str]] = {
    "product_page": [
        'itemtype="http://schema.org/Product"',
        '"@type": "Product"', '"@type":"Product"',
        'data-product-id', 'data-sku', 'class="product-detail',
        'id="product-detail', 'class="pdp-',
    ],
    "cart_signals": [
        "add-to-cart", "addToCart", "add_to_cart",
        "atc-button", "mini-cart", "cart-count", "basket",
    ],
    "price_signals": [
        'class="price"', 'itemprop="price"', 'data-price',
        'class="product-price', "sale-price", "original-price",
        "special-price", "regular-price", "was-price",
    ],
    "inventory_signals": [
        "in-stock", "out-of-stock", "stock-status", "availability",
        "data-in-stock", '"availability"', "backorder", "preorder",
    ],
    "review_signals": [
        'itemprop="ratingValue"', 'itemprop="reviewCount"',
        "star-rating", "review-count", "product-reviews",
    ],
    "faceted_nav": [
        "facets", "filter-panel", "refinement", "plp-filters",
        "layered-navigation", "sidebar-filter", "active-filter",
    ],
}

CDN_SIGNALS: dict[str, list[str]] = {
    "Cloudflare": ["cf-ray", "__cf_bm"],
    "Vercel":     ["x-vercel-id"],
    "AWS":        ["x-amz-cf-id", "x-amz-request-id"],
    "Fastly":     ["x-served-by"],
    "Akamai":     ["x-check-cacheable"],
}

SHORTCUT_SCHEMA_TYPES = {
    "Product", "Offer", "ItemList", "Article",
    "Review", "Event", "Recipe", "NewsArticle",
}

LOCALE_PATTERN = re.compile(
    r'^/(es|en|fr|de|pt|it|zh|ja|ko|ar|ru|nl|pl|tr)(/|$)'
)


async def classify_page(url: str, timeout: float = 15.0) -> ClassifierResult:
    """
    Fetch and classify the target page. Returns a ClassifierResult.
    Uses 3 requests total: base fetch + DNS + mobile UA compare.
    """
    start_ms = int(time.monotonic() * 1000)

    status, headers, html, response_time_ms = await make_request(
        url, ua=UA_CHROME, timeout=timeout
    )

    soup = BeautifulSoup(html, "lxml")

    js_frameworks = _detect_frameworks(html)
    cms = _detect_cms(html, headers)
    cdn = _detect_cdn(headers)
    infrastructure = _detect_infrastructure(headers)
    content_ratio = _compute_content_ratio(soup, html)
    structured_data = _detect_structured_data(soup, html)
    security_headers = _detect_security_headers(headers)
    cache_control = headers.get("cache-control")
    last_modified = headers.get("last-modified")
    locales = _detect_locales(soup)
    internal_link_count, estimated_pages = _estimate_crawl_scope(soup, url)
    server = headers.get("server")

    dns_signals = await _dns_lookup(url)

    # Confirm CDN from DNS if not already detected
    cname = dns_signals.get("cname", "")
    if not cdn and "cloudflare" in cname:
        cdn = "Cloudflare"

    mobile_result = await compare_mobile_desktop(url, timeout=timeout)
    mobile_differs = mobile_result["content_differs"]

    # E-commerce detection (no extra requests)
    ecommerce = _detect_ecommerce_signals(html, soup, cms)
    is_ecommerce_platform = cms in ECOMMERCE_PLATFORMS

    # PDP fetch (1 extra request, only if e-commerce signals found)
    pdp_sample: PdpSampleResult | None = None
    if ecommerce.is_ecommerce:
        pdp_sample = await _fetch_pdp_sample(url, html, headers, timeout)

    # Classification logic
    page_type, confidence = _classify(
        content_ratio, js_frameworks, cms
    )

    return ClassifierResult(
        type=page_type,
        confidence=confidence,
        js_frameworks=js_frameworks,
        cms=cms,
        server=server,
        cdn=cdn,
        infrastructure=infrastructure,
        dns_signals=dns_signals,
        content_ratio=round(content_ratio, 3),
        response_time_ms=response_time_ms,
        structured_data=structured_data,
        security_headers=security_headers,
        cache_control=cache_control,
        last_modified=last_modified,
        locales=locales,
        mobile_differs=mobile_differs,
        internal_link_count=internal_link_count,
        estimated_pages=estimated_pages,
        ecommerce=ecommerce,
        is_ecommerce_platform=is_ecommerce_platform,
        pdp_sample=pdp_sample,
    )


def _detect_frameworks(html: str) -> list[str]:
    """Scan raw HTML for JS framework fingerprints."""
    found = []
    for name, signals in FRAMEWORK_SIGNALS.items():
        if any(sig in html for sig in signals):
            found.append(name)
    return found


def _detect_cms(html: str, headers: dict[str, str]) -> str | None:
    """Detect CMS from HTML content and response headers."""
    headers_lower = {k.lower(): v for k, v in headers.items()}
    for cms_name, signals in CMS_SIGNALS.items():
        if any(sig in html for sig in signals["html"]):
            return cms_name
        if any(sig in headers_lower for sig in signals["headers"]):
            return cms_name
    return None


def _detect_cdn(headers: dict[str, str]) -> str | None:
    """Detect CDN from response headers."""
    headers_lower = {k.lower(): v for k, v in headers.items()}
    for cdn_name, signals in CDN_SIGNALS.items():
        if any(sig.lower() in headers_lower for sig in signals):
            return cdn_name
    return None


def _detect_infrastructure(headers: dict[str, str]) -> list[str]:
    """Detect infrastructure signals from headers."""
    infra = []
    headers_lower = {k.lower(): v for k, v in headers.items()}
    if any("awsdns" in v for v in headers_lower.values()):
        infra.append("AWS Route53")
    if "x-powered-by" in headers_lower:
        infra.append(headers_lower["x-powered-by"])
    return infra


def _compute_content_ratio(soup: BeautifulSoup, html: str) -> float:
    """Ratio of visible text to total HTML length."""
    return len(soup.get_text()) / max(len(html), 1)


def _detect_structured_data(
    soup: BeautifulSoup, html: str
) -> StructuredDataResult:
    """Detect JSON-LD, microdata, and OpenGraph structured data."""
    json_ld_found = '<script type="application/ld+json"' in html
    microdata_found = "itemscope" in html
    opengraph_found = 'property="og:' in html or "property='og:" in html

    schema_types: list[str] = []
    if json_ld_found:
        for tag in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(tag.string or "")
                if isinstance(data, dict):
                    t = data.get("@type")
                    if isinstance(t, list):
                        schema_types.extend(t)
                    elif isinstance(t, str):
                        schema_types.append(t)
                elif isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict):
                            t = item.get("@type")
                            if t:
                                schema_types.append(t) if isinstance(t, str) else schema_types.extend(t)
            except (json.JSONDecodeError, TypeError):
                pass

    scraping_shortcut = bool(SHORTCUT_SCHEMA_TYPES & set(schema_types))

    return StructuredDataResult(
        json_ld_found=json_ld_found,
        schema_types=schema_types,
        microdata_found=microdata_found,
        opengraph_found=opengraph_found,
        scraping_shortcut=scraping_shortcut,
    )


def _detect_security_headers(headers: dict[str, str]) -> SecurityHeadersResult:
    """Read security headers from response."""
    h = {k.lower(): v for k, v in headers.items()}
    csp_value = h.get("content-security-policy", "")
    return SecurityHeadersResult(
        csp=bool(csp_value),
        hsts="strict-transport-security" in h,
        x_frame_options="x-frame-options" in h,
        x_content_type_options="x-content-type-options" in h,
        csp_blocks_inline=bool(csp_value) and "unsafe-inline" not in csp_value,
    )


def _detect_locales(soup: BeautifulSoup) -> list[str]:
    """Detect locales from hreflang tags or URL path prefixes."""
    locales = [
        tag.get("hreflang", "")
        for tag in soup.find_all("link", rel="alternate")
        if tag.get("hreflang")
    ]
    if not locales:
        hrefs = [a.get("href", "") for a in soup.find_all("a", href=True)]
        locales = list({
            m.group(1) for h in hrefs
            if (m := LOCALE_PATTERN.match(h))
        })
    return locales


def _estimate_crawl_scope(
    soup: BeautifulSoup, url: str
) -> tuple[int, str]:
    """Count unique internal links and estimate total page count."""
    base_host = urlparse(url).netloc
    internal_links = {
        a["href"] for a in soup.find_all("a", href=True)
        if urlparse(a["href"]).netloc in ("", base_host)
        and not a["href"].startswith(("#", "mailto:", "tel:"))
    }
    count = len(internal_links)
    estimated = (
        "<50"      if count < 20  else
        "50-500"   if count < 100 else
        "500-5000" if count < 500 else
        ">5000"
    )
    return count, estimated


async def _dns_lookup(url: str) -> dict[str, str]:
    """Resolve DNS records for the domain. Returns empty dict if unavailable."""
    try:
        import dns.resolver
        domain = urlparse(url).netloc
        signals: dict[str, str] = {}

        for rtype in ["A", "CNAME", "NS", "TXT"]:
            try:
                answers = dns.resolver.resolve(domain, rtype)
                values = [r.to_text() for r in answers]
                signals[rtype.lower()] = ", ".join(values[:3])
                if rtype == "CNAME":
                    for v in values:
                        if "cloudflare" in v:
                            signals["cname"] = v
            except Exception:
                pass

        # Check NS for AWS Route53
        ns_val = signals.get("ns", "")
        if "awsdns" in ns_val:
            signals["infrastructure"] = "AWS Route53"

        return signals
    except ImportError:
        logger.warning("dnspython not available — skipping DNS lookup")
        return {}


def _detect_ecommerce_signals(
    html: str, soup: BeautifulSoup, cms: str | None
) -> EcommerceSignals:
    """Detect e-commerce signals from HTML — no additional requests."""
    signal_counts: dict[str, int] = {}
    for category, signals in ECOMMERCE_SIGNALS.items():
        signal_counts[category] = sum(1 for sig in signals if sig in html)

    is_ecommerce = any(
        signal_counts.get(cat, 0) > 0
        for cat in ("product_page", "cart_signals", "price_signals")
    )
    has_product_schema = (
        '"@type": "Product"' in html or '"@type":"Product"' in html
    )
    has_faceted_nav = signal_counts.get("faceted_nav", 0) > 0

    # Price mechanism: empty data-price attr → client-side; text in price element → server-side
    if re.search(r'data-price=["\'][\s]*["\']', html):
        price_mechanism: str = "CLIENT_SIDE"
    elif signal_counts.get("price_signals", 0) > 0:
        price_mechanism = "SERVER_SIDE"
    else:
        price_mechanism = "UNKNOWN"

    # Cart architecture
    if "wc-cart-fragments" in html:
        cart_architecture: str = "AJAX_FRAGMENTS"
    elif "/cart.js" in html:
        cart_architecture = "AJAX_API"
    elif "magentoSectionData" in html:
        cart_architecture = "SECTION_CACHE"
    else:
        cart_architecture = "UNKNOWN"

    platform = cms if cms in ECOMMERCE_PLATFORMS else None

    # Price reliability scoring
    json_ld_price = _extract_json_ld_price(html)
    html_price_text: str | None = None
    for el in soup.find_all(class_=re.compile(r'price', re.I)):
        text = el.get_text(strip=True)
        if text and re.search(r'\d', text):
            html_price_text = text
            break
    price_reliability_score = _compute_price_score(
        json_ld_price,
        html_price_text,
        signal_counts.get("price_signals", 0)
    )

    return EcommerceSignals(
        is_ecommerce=is_ecommerce,
        platform=platform,
        price_mechanism=price_mechanism,  # type: ignore[arg-type]
        price_reliability_score=price_reliability_score,
        cart_architecture=cart_architecture,  # type: ignore[arg-type]
        has_faceted_nav=has_faceted_nav,
        has_product_schema=has_product_schema,
        signal_counts=signal_counts,
    )


def _extract_json_ld_price(html: str) -> float | None:
    """Extract numeric price from JSON-LD Product/Offer.
    Returns first valid numeric price found, or None."""
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")
        for tag in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(tag.string or "")
                if isinstance(data, dict):
                    if data.get("@type") == "Product" or "Product" in (data.get("@type") if isinstance(data.get("@type"), list) else []):
                        offers = data.get("offers")
                        if isinstance(offers, dict):
                            price = offers.get("price")
                            if isinstance(price, (int, float)):
                                return float(price)
                            if isinstance(price, str) and price:
                                try:
                                    return float(price)
                                except ValueError:
                                    pass
                        elif isinstance(offers, list):
                            for offer in offers:
                                if isinstance(offer, dict):
                                    price = offer.get("price")
                                    if isinstance(price, (int, float)):
                                        return float(price)
                                    if isinstance(price, str) and price:
                                        try:
                                            return float(price)
                                        except ValueError:
                                            pass
            except (json.JSONDecodeError, TypeError):
                pass
    except Exception:
        pass
    return None


def _is_placeholder_price(value: str) -> bool:
    """Detect placeholder/unavailable price patterns (case-insensitive, whitespace-tolerant).
    Patterns: 0, 0.00, 0,00, tbd, contact, call for, na, n/a, --, ?"""
    if not value:
        return False
    normalized = value.lower().strip()
    # Exact match patterns
    if normalized in ("tbd", "na", "n/a", "--", "?"):
        return True
    # Prefix patterns (allows words after the pattern)
    if normalized.startswith("contact") or normalized.startswith("call for"):
        return True
    # Numeric zero patterns (including comma as decimal separator)
    if re.match(r'^0+\.?0*$|^0+,?0*$', normalized):
        return True
    return False


def _compute_price_score(
    json_ld_price: float | None,
    html_price_text: str | None,
    signal_count: int
) -> int | None:
    """Compute price reliability score (0-100 or None).
    Decision table (first match wins):
    - JSON-LD price + real value → 90
    - JSON-LD price + placeholder → 30
    - HTML visible + real value → 80
    - HTML visible + placeholder → 25
    - Price signals present but no text → 40
    - No price signals → None"""
    if json_ld_price is not None:
        if _is_placeholder_price(str(json_ld_price)):
            return 30
        return 90

    if html_price_text is not None:
        if _is_placeholder_price(html_price_text):
            return 25
        if re.search(r'\d', html_price_text):
            return 80

    if signal_count > 0:
        return 40

    return None


async def _fetch_pdp_sample(
    category_url: str,
    html: str,
    category_headers: dict[str, str],
    timeout: float,
) -> PdpSampleResult | None:
    """Extract 1 PDP link from category HTML and fetch it. Returns None if no PDP found."""
    soup = BeautifulSoup(html, "lxml")
    base = urlparse(category_url)
    pdp_pattern = re.compile(
        r'/(p|product|item|producto|detalle|pdp)/|/[^/]+-\d+\.html$',
        re.IGNORECASE,
    )

    pdp_url: str | None = None
    for a in soup.find_all("a", href=True):
        href = a["href"]
        parsed = urlparse(href)
        # Resolve relative URLs
        if not parsed.scheme:
            href = f"{base.scheme}://{base.netloc}{href}" if href.startswith("/") else href
        if pdp_pattern.search(href):
            pdp_url = href
            break

    if not pdp_url:
        return None

    try:
        _, pdp_headers, pdp_html, pdp_ms = await make_request(
            pdp_url, ua=UA_CHROME, timeout=timeout
        )
    except Exception as exc:
        logger.warning("PDP fetch failed for %s: %s", pdp_url, exc)
        return None

    pdp_soup = BeautifulSoup(pdp_html, "lxml")
    pdp_ratio = _compute_content_ratio(pdp_soup, pdp_html)

    # Price in HTML: look for non-empty text in price-classed elements
    price_in_html = False
    for el in pdp_soup.find_all(class_=re.compile(r'price', re.I)):
        text = el.get_text(strip=True)
        if text and re.search(r'\d', text):
            price_in_html = True
            break

    product_schema_found = (
        '"@type": "Product"' in pdp_html or '"@type":"Product"' in pdp_html
    )

    # Compare bot-detection headers present in both responses
    bot_headers = {
        "cf-ray", "x-vtex-cache-status", "x-magento-cache-id",
        "x-dw-request-id", "x-prestashop", "__cf_bm",
    }
    cat_lower = {k.lower() for k in category_headers}
    pdp_lower = {k.lower() for k in pdp_headers}
    cat_bot = cat_lower & bot_headers
    pdp_bot = pdp_lower & bot_headers
    same_protection = cat_bot == pdp_bot

    return PdpSampleResult(
        url=pdp_url,
        renders_server_side=pdp_ratio >= 0.15,
        price_in_html=price_in_html,
        product_schema_found=product_schema_found,
        response_time_ms=pdp_ms,
        same_protection_as_category=same_protection,
    )


_HEADLESS_FRAMEWORKS = {"Next.js", "Nuxt", "Gatsby", "Remix"}
_SSR_ECOMMERCE = {"Magento", "WooCommerce", "PrestaShop", "OpenCart", "SAP Hybris"}


def _classify(
    content_ratio: float,
    js_frameworks: list[str],
    cms: str | None,
) -> tuple[str, str]:
    """Determine page type and confidence — platform-aware rules."""
    if content_ratio < 0.05:
        return "API_DRIVEN", "HIGH"

    # Headless commerce: SSR blob in HTML → HYBRID, not DYNAMIC
    if js_frameworks and any(f in _HEADLESS_FRAMEWORKS for f in js_frameworks):
        if content_ratio >= 0.10:
            return "HYBRID", "HIGH"
        return "DYNAMIC", "MEDIUM"

    # SSR e-commerce with AJAX cart
    if cms in _SSR_ECOMMERCE:
        if content_ratio >= 0.15:
            return "HYBRID", "HIGH"
        return "HYBRID", "MEDIUM"

    # Liquid/SaaS platforms: always HYBRID
    if cms in {"Shopify", "BigCommerce", "VTEX"}:
        return "HYBRID", "HIGH"

    if cms in {"Salesforce CC", "SAP Hybris"}:
        return "HYBRID", "MEDIUM"

    # Generic JS frameworks
    if js_frameworks:
        hydration = {"HTMX", "Astro"}
        if all(f in hydration for f in js_frameworks) and content_ratio >= 0.15:
            return "HYBRID", "MEDIUM"
        return "DYNAMIC", "HIGH" if content_ratio < 0.15 else "MEDIUM"

    if content_ratio >= 0.15:
        return "STATIC", "HIGH"
    if content_ratio >= 0.08:
        return "STATIC", "MEDIUM"
    return "UNKNOWN", "LOW"
