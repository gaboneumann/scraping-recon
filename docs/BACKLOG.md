# scraping_recon — Backlog de mejoras

Checklist de mejoras pendientes. Actualizar estado al implementar cada item.

---

## E-commerce / Retail

| ID | Estado | Descripción |
|----|--------|-------------|
| E1 | 🔲 | **Price reliability score** — distinguir JSON-LD vs HTML visible vs placeholder client-side vs inexistente estáticamente. Actualmente solo se detecta si hay señales de precio, no si el valor es scrapeble sin JS. |
| E2 | 🔲 | **Search API probe** — detectar si el sitio expone un endpoint de búsqueda (Algolia, Elasticsearch, custom) utilizable como catálogo alternativo sin scraping de HTML. |
| E3 | 🔲 | **Variantes de producto** — detectar si talla/color/SKU requieren requests AJAX adicionales y qué endpoint las sirve. Actualmente no se analiza. |
| E4 | 🔲 | **Múltiples PDP samples** — tomar 2-3 muestras en vez de 1 para mayor confianza estadística sobre consistencia de protección entre productos. |
| E5 | 🔲 | **Reviews API externa** — identificar si los ratings vienen de proveedores externos (Bazaarvoice, Yotpo, Trustpilot) vs HTML propio. APIs externas son scrapebles directamente sin tocar el sitio. |
| E6 | 🔲 | **Inventario estático vs dinámico** — distinguir si el valor de stock en HTML es real o un placeholder actualizado via AJAX post-load. |
| E7 | 🔲 | **Deep mode e-commerce** — lógica Playwright específica: observar requests JS de precio, paginado real en infinite scroll, y requests del carrito. Actualmente `--deep` no tiene lógica e-commerce específica. |

---

## Antibot

| ID | Estado | Descripción |
|----|--------|-------------|
| A1 | ✅ | **Gap 1** — Probar protecciones en API endpoints descubiertos, no solo en la URL principal. |
| A2 | ✅ | **Warning subestimación** — Alertar cuando el sitio es DYNAMIC/API_DRIVEN y el score antibot es bajo (protecciones runtime no visibles estáticamente). |
| A3 | ❌ | **Gap 3 — Cart/checkout probe** — Descartado: requiere sesión activa (cookies + cart token) para retornar datos significativos. Sin sesión, el servidor devuelve carritos vacíos o redirects. |
| B1 | 🔲 | **Vendors comportamentales** — Detectar scripts y cookies de DataDome, HUMAN/PerimeterX, Akamai Bot Manager. Son los vendors más agresivos y no están en la detección WAF actual. |
| B2 | 🔲 | **Hardware fingerprinting sin librería** — Buscar patrones directos en scripts inline: `toDataURL` (Canvas), `getChannelData` (AudioContext), `WEBGL_debug_renderer_info` (WebGL). Actualmente solo detectamos FingerprintJS. |
| B3 | 🔲 | **Headless browser checks en JS del sitio** — Detectar si el sitio busca activamente `navigator.webdriver`, `window.outerWidth`, `chrome.app` en sus scripts. Indica detección activa de automatización. |
| B4 | 🔲 | **Proof of Work (PoW)** — Detectar Turnstile widget y scripts de PoW custom en HTML. Observable estáticamente. Ampliar dimensión `captcha` o añadir señal en `waf`. |
| B5 | 🔲 | **Behavioral script detection** — Detectar event listeners de recolección biométrica (`mousemove`, `keydown`, `scroll`, `touchstart`) en scripts inline y firmas de vendors comportamentales. |
| B6 | 🔲 | **User journey probe** — Request directo a `/checkout` y `/cart` sin sesión y clasificar respuesta: challenge, redirect, 403, o abierto. Mismo patrón de probe que rate-limiting. |
| B7 | 🔲 | **WebRTC detection scripts** — Buscar `RTCPeerConnection` y patrones de WebRTC leak detection en el JS del sitio. Indica que el sitio intentará exponer la IP real detrás de VPN/proxy. |

---

## Classifier

| ID | Estado | Descripción |
|----|--------|-------------|
| C1 | ✅ | **EcommerceSignals** — Detección de plataforma, price_mechanism, cart_architecture, faceted_nav, product_schema desde HTML estático. |
| C2 | ✅ | **PDP sample** — Fetch de 1 PDP extraído del HTML de categoría. Compara render mode, precio, schema y protección. |
| C3 | ✅ | **Platform-aware classify** — Reglas HYBRID para plataformas SSR e-commerce (Magento, WooCommerce, etc.) y frameworks headless (Next.js, Nuxt). |
