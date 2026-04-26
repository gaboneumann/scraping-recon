# Recommender — Árbol de decisión completo

Referenciado desde `docs/build/STEP_7_recommender.md` y `modules/recommender.py`.

---

## Árbol de decisión (orden exacto)

```
1. Si antibot is None → primary="httpx", secondary=None, complejidad=3

2. Si antibot.overall_score >= 8 →
       primary="playwright + playwright-stealth"
       secondary="curl_cffi + residential proxy"
       managed_api_suggested=True
       managed_api_options=["ZenRows", "ScraperAPI", "Scrapfly"]

2.5. Si classifier.is_ecommerce_platform → rama e-commerce (ver abajo)

3. Si classifier.type == "STATIC":
     Si antibot.overall_score == 0 → primary="httpx + BeautifulSoup4", secondary="Scrapy"
     Sino → primary="curl_cffi + BeautifulSoup4", secondary="httpx rotating UA"

4. Si classifier.type in ["DYNAMIC", "API_DRIVEN"]:
     Si api_detector.internal_api_found →
         primary="httpx direct to API"
         secondary="curl_cffi si tls_score >= 2"
     Sino → primary="Playwright async", secondary="Selenium"

5. Si classifier.type == "HYBRID":
     primary="httpx SSR + Playwright opcional"
     secondary="Scrapy + Playwright plugin"
```

---

## Rama 2.5 — E-commerce platform (detalles)

> ⚠️ **NOT IMPLEMENTED** — Lógica pendiente. Ver BACKLOG E1–E7 para el roadmap de implementación.

```python
cms = classifier.cms

if cms == "Shopify":
    # Siempre tiene /products.json y cart API documentadas
    if api and any("graphql" in e.url for e in api.endpoints):
        primary = "httpx + gql (Shopify Storefront API)"
        complexity = 4
    else:
        primary = "httpx (Shopify AJAX: /products.json, /cart.js)"
        complexity = 3
    secondary = "curl_cffi" if antibot and antibot.dimensions.tls_fingerprint.score >= 2 else None
    dev_time = "1-2 days"

elif cms == "WooCommerce":
    primary = "httpx (WooCommerce REST: /wp-json/wc/v3/products)"
    secondary = "BeautifulSoup4 HTML fallback"
    complexity = 3; dev_time = "1-2 days"

elif cms == "Magento":
    if api and any("graphql" in e.url for e in api.endpoints):
        primary = "httpx + gql (Magento GraphQL)"
        secondary = "BeautifulSoup4 SSR fallback"
        complexity = 6; dev_time = "3-5 days"
    else:
        primary = "httpx + BeautifulSoup4 (SSR HTML)"
        secondary = "Playwright para /customer/section/load/ sections"
        complexity = 7; dev_time = "3-7 days"

elif cms == "BigCommerce":
    primary = "httpx (BigCommerce: /products.json, /api/storefront/)"
    secondary = "curl_cffi" if antibot and antibot.dimensions.tls_fingerprint.score >= 2 else None
    complexity = 4; dev_time = "2-3 days"

elif cms in ("Salesforce CC", "SAP Hybris"):
    primary = "httpx + BeautifulSoup4 (SSR)"
    secondary = "Playwright para contenido AJAX"
    complexity = 7; dev_time = "4-7 days"

else:  # VTEX, PrestaShop, OpenCart, etc.
    primary = "httpx + BeautifulSoup4"
    secondary = "Playwright para secciones dinámicas"
    complexity = 5; dev_time = "2-4 days"
```

---

## Flags adicionales (evaluar siempre)

> ⚠️ **NOT IMPLEMENTED** — Los campos de schema referenciados aquí no existen aún en `models/schemas.py`. Ver BACKLOG E1–E6.

```python
if antibot.dimensions.rate_limiting.score >= 2:
    flags.append("Exponential backoff + 2-8s random delays mandatory")
if antibot.dimensions.tls_fingerprint.score >= 2:
    flags.append("curl_cffi Chrome/Safari impersonation required")
if antibot.dimensions.captcha.score >= 2:
    flags.append("Consider 2Captcha or Anti-Captcha integration")
if antibot.dimensions.honeypots.count > 0:
    flags.append(f"Filter display:none anchors — {antibot.dimensions.honeypots.count} honeypots detected")
if antibot.dimensions.ip_reputation.geo_block:
    flags.append("Residential proxies in target country required")
if pagination.requires_js:
    flags.append("Browser automation mandatory for full crawl")
# Auth flags
if auth and auth.required:
    if auth.type == "FORM":
        flags.append("Session management required — login + persistent cookie jar")
    if auth.type == "OAUTH":
        flags.append("OAuth flow required — use Playwright to automate login")
    if auth.type == "API_KEY":
        flags.append("API key auth — pass via header or query param")
    if auth.paywall_type == "HARD":
        flags.append("Hard paywall — subscription account required")
    if auth.paywall_type == "METERED":
        flags.append("Metered paywall — rotate sessions or incognito profiles")
if auth and auth.cookie_consent_blocking:
    flags.append("Cookie consent wall — click accept before scraping content")
# Structured data shortcut
if classifier and classifier.structured_data.scraping_shortcut:
    types = ", ".join(classifier.structured_data.schema_types)
    flags.append(f"JSON-LD available ({types}) — parse structured data instead of HTML")
# Mobile content
if classifier and classifier.mobile_differs:
    flags.append("Mobile UA serves different content — test with UA_MOBILE for richer data")
# Crawl scope
if classifier and classifier.estimated_pages == ">5000":
    flags.append("Large site (>5000 pages estimated) — implement queue + deduplication layer")
# AJAX gap
if api_detector and api_detector.endpoints_may_be_incomplete:
    flags.append("DYNAMIC site — run with --deep flag (Playwright) for complete XHR endpoint map")
# E-commerce flags
if classifier and classifier.ecommerce.price_mechanism == "CLIENT_SIDE":
    flags.append("Prices rendered client-side — use Playwright or intercept XHR price API")
if classifier and classifier.ecommerce.cart_architecture in ("AJAX_FRAGMENTS", "AJAX_API", "SECTION_CACHE"):
    flags.append(f"Cart uses {classifier.ecommerce.cart_architecture} — do not scrape cart state from HTML")
if classifier and classifier.ecommerce.has_faceted_nav:
    flags.append("Faceted navigation detected — enumerate filter combinations for full catalog coverage")
if classifier and classifier.ecommerce.has_inventory_signals:
    flags.append("Inventory/stock data present — may change frequently, add TTL cache to pipeline")
if legal and legal.sitemap.product_sitemap_url:
    flags.append(f"Product sitemap available ({legal.sitemap.product_sitemap_url}) — use as URL source instead of crawling HTML")
# E-commerce structured data shortcut
if classifier and classifier.ecommerce.is_ecommerce and classifier.structured_data.scraping_shortcut:
    types = ", ".join(classifier.structured_data.schema_types)
    flags.append(f"JSON-LD Product schema available ({types}) — parse structured data for price/SKU/availability instead of DOM")
```
