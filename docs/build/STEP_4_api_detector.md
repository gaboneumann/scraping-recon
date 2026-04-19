# STEP 4 — modules/api_detector.py [CHECKPOINT]

**Importa desde:** `utils.http`, `models.schemas.ApiDetectorResult`

---

## Patrones

```python
API_PATTERNS = [
    r'fetch\(["\']([^"\']+)["\']',
    r'axios\.(?:get|post|put|delete)\(["\']([^"\']+)["\']',
    r'XMLHttpRequest.*?\.open\(["\'](?:GET|POST)["\'],\s*["\']([^"\']+)["\']',
    r'\$\.ajax\(.*?url:\s*["\']([^"\']+)["\']',
    r'((?:/api/|/v\d+/|/graphql)[a-zA-Z0-9/_-]+)',
    r'(wss?://[^\s"\']+)',
    # E-commerce platform APIs documentadas
    r'(/api/\d{4}-\d{2}/graphql\.json)',              # Shopify Storefront API
    r'(/wp-json/wc/v\d+/[a-zA-Z0-9/_-]+)',           # WooCommerce REST
    r'(/rest/[^/]+/V\d+/[a-zA-Z0-9/_-]+)',           # Magento REST
    r'(/api/storefront/[a-zA-Z0-9/_-]+)',             # BigCommerce
    r'(/on/demandware\.store/[a-zA-Z0-9/_-]+)',       # Salesforce CC
    r'(/products?(?:/|\.json))',                       # Shopify /products.json
    r'(/cart\.js|/cart/add\.js|/cart/update\.js)',    # Shopify cart API
]

STATE_PATTERNS = [
    "__NEXT_DATA__",
    "window.__INITIAL_STATE__",
    "window.__REDUX_STATE__",
    "window.__PRELOADED_STATE__",
    # E-commerce state blobs
    "window.ShopifyAnalytics",    # Shopify: product/variant data en la página
    "window.__MAGENTO_INIT__",    # Magento 2 page config
    "var BCData",                  # BigCommerce customer/cart data
    "window.SiteGenesis",         # Salesforce CC
    "window.__WC_DATA__",         # WooCommerce block editor
]
```

---

## Clasificación de endpoints e-commerce

```python
ECOMMERCE_API_TYPE_MAP = {
    "/wp-json/wc/":        "WooCommerce-REST",
    "/rest/V":             "Magento-REST",
    "/api/storefront/":    "BigCommerce-REST",
    "/on/demandware":      "SFCC-REST",
    "graphql":             "GraphQL",
    "wss://": "WebSocket", "ws://": "WebSocket",
}
```
Extender `_classify_endpoint()` para usar este mapa antes del fallback genérico.

---

## GraphQL introspection

Si se encuentra `/graphql` o `/api/graphql`:
```python
INTROSPECTION_QUERY = '{"query":"{__typename}"}'
```
POST con `Content-Type: application/json`. Si retorna 200 con `data.__typename`: `introspection_enabled=True`.

---

## Reglas

- **Deduplicación:** URLs repetidas → una sola entrada. Excluir assets (`.js`, `.css`, `.png`, `.woff`).
- **AJAX/XHR limitation:** setear `endpoints_may_be_incomplete=True` cuando `ClassifierResult.type` sea `DYNAMIC` o `API_DRIVEN` y no se hayan encontrado endpoints. Agregar en `recommendation`: `"Site renders via JS — intercept XHR with Playwright (--deep) for complete endpoint map."` No silenciar este gap.

---

**[CHECKPOINT 4]** — Ejecuta:
```bash
python -c "
import asyncio
from modules.api_detector import detect_apis

async def test():
    r = await detect_apis('https://reddit.com', timeout=15)
    print('found:', r.internal_api_found)
    for ep in r.endpoints[:3]:
        print(' ', ep.type, ep.url[:60])

asyncio.run(test())
"
```
