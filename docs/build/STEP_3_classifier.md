# STEP 3 — modules/classifier.py [CHECKPOINT]

**Importa desde:** `utils.http`, `models.schemas.ClassifierResult`

---

## Señales de detección

```python
# Content ratio
ratio = len(soup.get_text()) / max(len(html), 1)
# ratio < 0.15 → probable JS-rendered

FRAMEWORK_SIGNALS = {
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

CMS_SIGNALS = {
    # Genéricos
    "WordPress":   {"html": ["/wp-content/", "/wp-includes/", "wp-json"], "headers": []},
    "Shopify":     {"html": ["cdn.shopify.com", "Shopify.theme", "Shopify.theme.name"], "headers": []},
    "Drupal":      {"html": ["Drupal.settings"], "headers": ["x-drupal-cache"]},
    "Joomla":      {"html": ["/media/jui/"], "headers": []},
    "Wix":         {"html": [], "headers": ["x-wix-request-id"]},
    "Squarespace": {"html": ["squarespace.com"], "headers": []},
    "Webflow":     {"html": ["data-wf-"], "headers": []},
    # E-commerce platforms — prioridad alta en retail
    "WooCommerce":   {"html": ["woocommerce", "wc-cart-fragments", "WC.cart",
                               "woocommerce-js-cookie"], "headers": []},
    "Magento":       {"html": ["Mage.Cookies", "data-mage-init", "magentoSectionData",
                               "MAGE_", "mage/cookies"], "headers": ["x-magento-cache-id", "x-magento-tags"]},
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

# Plataformas que siempre son HYBRID (SSR product content + AJAX cart/price)
ECOMMERCE_PLATFORMS = {
    "Shopify", "WooCommerce", "Magento", "BigCommerce", "PrestaShop",
    "Salesforce CC", "SAP Hybris", "OpenCart", "VTEX",
}

# Señales de e-commerce por categoría — análisis puro sobre HTML ya fetcheado
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

CDN_SIGNALS = {
    "Cloudflare": ["CF-Ray", "__cf_bm"],
    "Vercel":     ["x-vercel-id"],
    "AWS":        ["x-amz-cf-id", "x-amz-request-id"],
    "Fastly":     ["x-served-by"],
    "Akamai":     ["x-check-cacheable"],
}
```

---

## DNS

Usar dnspython: resolver A, CNAME, NS, TXT. Si no disponible: `dns_signals={}`.

---

## Structured data

```python
SHORTCUT_SCHEMA_TYPES = {"Product", "Offer", "ItemList", "Article", "Review", "Event", "Recipe"}

# json_ld_found: '<script type="application/ld+json"' en HTML
# schema_types: extraer "@type" de cada bloque JSON-LD (puede ser lista o string)
# microdata_found: 'itemscope' en HTML
# opengraph_found: 'property="og:' en HTML
# scraping_shortcut: True si algún schema_type ∈ SHORTCUT_SCHEMA_TYPES
```

---

## Security headers

Leer directamente de los headers de la respuesta base (sin request adicional):
```python
security_headers = SecurityHeadersResult(
    csp="content-security-policy" in headers,
    hsts="strict-transport-security" in headers,
    x_frame_options="x-frame-options" in headers,
    x_content_type_options="x-content-type-options" in headers,
    csp_blocks_inline=(
        "content-security-policy" in headers
        and "unsafe-inline" not in headers["content-security-policy"]
    ),
)
```

---

## Content freshness

```python
cache_control = headers.get("cache-control")        # e.g. "max-age=3600, public"
last_modified = headers.get("last-modified")        # e.g. "Wed, 21 Oct 2024 07:28:00 GMT"
```

---

## Multi-locale

```python
# hreflang links
locales = [tag["hreflang"] for tag in soup.find_all("link", rel="alternate", hreflang=True)]
# Si vacío, buscar rutas con prefijo de idioma en <a href>
if not locales:
    import re
    locale_pattern = re.compile(r'^/(es|en|fr|de|pt|it|zh|ja|ko|ar|ru|nl|pl|tr)(/|$)')
    hrefs = [a.get("href", "") for a in soup.find_all("a", href=True)]
    locales = list({m.group(1) for h in hrefs if (m := locale_pattern.match(h))})
```

---

## Crawl scope

```python
from urllib.parse import urlparse

base_host = urlparse(url).netloc
internal_links = {
    a["href"] for a in soup.find_all("a", href=True)
    if urlparse(a["href"]).netloc in ("", base_host)
}
internal_link_count = len(internal_links)

estimated_pages = (
    "<50"       if internal_link_count < 20   else
    "50-500"    if internal_link_count < 100  else
    "500-5000"  if internal_link_count < 500  else
    ">5000"
)
```

---

## Mobile parity

Llamar a `compare_mobile_desktop(url, timeout)` de `utils.http`. Resultado popula `mobile_differs`. Usa 1 request adicional del budget.

---

## `_detect_ecommerce_signals(html, soup) -> EcommerceSignals`

Sin requests adicionales:
- Contar hits por categoría de `ECOMMERCE_SIGNALS`
- `price_mechanism`: si hay `data-price` attrs vacíos → `CLIENT_SIDE`; spans con precio en texto → `SERVER_SIDE`
- `cart_architecture`: detectar por patrones (`wc-cart-fragments` → `AJAX_FRAGMENTS`, `/cart.js` → `AJAX_API`, `magentoSectionData` → `SECTION_CACHE`)
- `is_ecommerce`: True si ≥1 hit en product_page, cart_signals, o price_signals

---

## Wiring en `classify_page()`

```python
ecommerce = _detect_ecommerce_signals(html, soup)
is_ecommerce_platform = cms in ECOMMERCE_PLATFORMS

page_type, confidence = _classify(content_ratio, js_frameworks, cms)

return ClassifierResult(
    ...,
    ecommerce=ecommerce,
    is_ecommerce_platform=is_ecommerce_platform,
)
```

---

## `_classify()` — reglas platform-aware

```python
# 1. API-driven (universal)
if content_ratio < 0.05:
    return "API_DRIVEN", "HIGH"

# 2. Headless commerce: Next.js/Nuxt SSR con __NEXT_DATA__ embebe producto en HTML
#    → HYBRID no DYNAMIC (los datos están en el blob, no requieren JS fetch)
HEADLESS_FRAMEWORKS = {"Next.js", "Nuxt", "Gatsby", "Remix"}
if js_frameworks and any(f in HEADLESS_FRAMEWORKS for f in js_frameworks):
    if content_ratio >= 0.10:
        return "HYBRID", "HIGH"
    return "DYNAMIC", "MEDIUM"

# 3. SSR e-commerce con cart AJAX: siempre HYBRID
SSR_ECOMMERCE = {"Magento", "WooCommerce", "PrestaShop", "OpenCart", "Sylius"}
if cms in SSR_ECOMMERCE:
    return "HYBRID", "HIGH" if content_ratio >= 0.15 else "HYBRID", "MEDIUM"

# 4. Plataformas Liquid/SSR + AJAX cart definitivo
if cms in {"Shopify", "BigCommerce", "VTEX"}:
    return "HYBRID", "HIGH"

# 5. Salesforce CC / SAP Hybris: SSR pesado
if cms in {"Salesforce CC", "SAP Hybris"}:
    return "HYBRID", "MEDIUM"

# 6. Frameworks JS genéricos sin CMS conocido
if js_frameworks:
    hydration = {"HTMX", "Astro"}
    if all(f in hydration for f in js_frameworks) and content_ratio >= 0.15:
        return "HYBRID", "MEDIUM"
    return "DYNAMIC", "HIGH" if content_ratio < 0.15 else "MEDIUM"

# 7. Estático puro
if content_ratio >= 0.15:
    return "STATIC", "HIGH"
if content_ratio >= 0.08:
    return "STATIC", "MEDIUM"

return "UNKNOWN", "LOW"
```

---

**[CHECKPOINT 3]** — Ejecuta:
```bash
python -c "
import asyncio
from modules.classifier import classify_page

async def test():
    tests = [
        ('https://example.com', 'STATIC', None),
        ('https://news.ycombinator.com', 'STATIC', None),
        ('https://www.buscalibre.cl', 'HYBRID', True),
    ]
    for url, expected_type, expected_ecom in tests:
        r = await classify_page(url, timeout=15)
        ok_type = r.type == expected_type
        ok_ecom = expected_ecom is None or r.is_ecommerce_platform == expected_ecom
        status = 'OK' if (ok_type and ok_ecom) else 'FAIL'
        print(f'{status} {url.split(\"/\")[2]}: type={r.type} cms={r.cms} is_ecommerce_platform={r.is_ecommerce_platform}')
        print(f'   ecommerce={r.ecommerce.model_dump()}')

asyncio.run(test())
"
```
Expected: `example.com → STATIC`, `ycombinator → STATIC`, `buscalibre.cl → HYBRID/is_ecommerce_platform=True`.
