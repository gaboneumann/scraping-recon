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


def _classify(
    content_ratio: float,
    js_frameworks: list[str],
    cms: str | None,
) -> tuple[str, str]:
    """Determine page type and confidence from collected signals."""
    hydration_frameworks = {"HTMX", "Astro"}

    if content_ratio < 0.05:
        return "API_DRIVEN", "HIGH"

    if js_frameworks:
        if all(f in hydration_frameworks for f in js_frameworks) and content_ratio >= 0.15:
            return "HYBRID", "MEDIUM"
        return "DYNAMIC", "HIGH" if content_ratio < 0.15 else "MEDIUM"

    if content_ratio >= 0.15:
        return "STATIC", "HIGH"

    if content_ratio >= 0.08:
        return "STATIC", "MEDIUM"

    return "UNKNOWN", "LOW"
