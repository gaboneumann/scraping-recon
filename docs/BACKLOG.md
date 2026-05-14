# scraping_recon — Backlog de mejoras

Checklist de mejoras pendientes. Actualizar estado al implementar cada item.

---

## Estado del proyecto (May 14, 2026)

**Core: 100% implementado** — 7 módulos + utils + report + CLI operacional.  
**Tests:** 250 tests (unit + integration) · 86.22% coverage · `make test` ✅.  
**Gap crítico:** `--deep` acepta el flag pero no tiene implementación — cero código Playwright.

| Componente | Estado | Líneas | Notas |
|---|---|---|---|
| `classifier` | ✅ completo | 623 | EcommerceSignals + price_reliability_score (E1), PDP sample, platform-aware |
| `antibot` | ✅ completo | 652 | WAF, rate-limit, TLS, fingerprinting (B2/B3/B7), PoW (B4), behavioral listeners (B5), journey probes (B6), behavioral vendors (B1) |
| `recommender` | ✅ completo | 180 | Función pura, árbol de 5 ramas |
| `legal` | ✅ completo | 219 | robots.txt, sitemap, ToS |
| `auth_detector` | ✅ completo | 175 | login form, OAuth, paywall, cookie consent |
| `api_detector` | ✅ completo | 171 | XHR/fetch, GraphQL probe, state blobs |
| `pagination` | ✅ completo | 131 | link-rel, query param, cursor, infinite scroll |
| `utils` (http, tls_test, graceful) | ✅ completo | ~100 | |
| `report` (terminal + json_export) | ✅ completo | — | |
| `--deep` / Playwright | ❌ no implementado | 0 | Flag aceptado en config, nunca se usa en main.py |

### Prioridad de fases

| Fase | IDs | Estado | Criterio |
|---|---|---|---|
| **Phase 1 — Antibot avanzado** | B1–B7 | ✅ COMPLETE | Ampliación de detección antibot: vendors (B1), fingerprinting patterns (B2/B3/B7), PoW (B4), behavioral listeners (B5), journey probes (B6). 2 nuevas dimensiones. 9 total (era 7). |
| **Phase 2 — E-commerce depth** | E1–E6 | PARTIAL (E1 ✅) | Price reliability scoring (E1) implementado. E2-E6 pendientes. |
| **Phase 3 — Deep Mode / Playwright** | E7 + implementar `config.deep` | 🔲 | Desbloquea la recomendación `--deep flag` que ya aparece en output. Requiere Playwright. |
| **Phase 4 — Test coverage** | T2 + smoke suite | 🔲 | Validation continua de señales por plataforma. |

---

## E-commerce / Retail

| ID | Estado | Descripción |
|----|--------|-------------|
| E1 | ✅ | **Price reliability score** — Implementado en classifier.py `_compute_price_score()`. Distingue JSON-LD vs HTML visible vs placeholder client-side. Score 0-100 refleja confianza de scrapeabilidad sin JS. |
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
| B1 | ✅ | **Vendors comportamentales** — Detectar scripts y cookies de DataDome, HUMAN/PerimeterX, Akamai Bot Manager. Son los vendors más agresivos y no están en la detección WAF actual. |
| B2 | ✅ | **Hardware fingerprinting sin librería** — Detecta patrones Canvas.toDataURL, AudioContext.createDynamicsCompressor, WebGL.getParameter (0x846D, 0x9245). 23 unit tests + integration coverage. |
| B3 | ✅ | **Headless browser checks en JS del sitio** — Detecta navigator.webdriver, navigator.plugins, window.chrome/chrome.runtime en scripts. Score ponderado por cantidad de patrones detectados. |
| B4 | ✅ | **Proof of Work (PoW)** — Detecta Turnstile widget (challenges.cloudflare.com/turnstile) con score=3. Extendida CAPTCHA_SIGNALS; patrón prioritizado sobre reCAPTCHA v2. |
| B5 | ✅ | **Behavioral script detection** — Detecta ≥2 event listeners (mousemove, keydown, wheel, scroll, touchstart) con validación isTrusted. Nueva dimensión: BehavioralDetectionDimension (score 0-3). |
| B6 | ✅ | **User journey probe** — Probes /checkout, /cart sin sesión (max 2 requests). Condicional: solo si ecommerce_signals.is_ecommerce=true. Nueva dimensión: JourneyDimension (blocked_type: 403/challenge/redirect/rate_limit/none). |
| B7 | ✅ | **WebRTC detection scripts** — Detecta RTCPeerConnection, getUserMedia, createDataChannel patterns en scripts. Score 3 (alta prioridad). |

---

## Classifier

| ID | Estado | Descripción |
|----|--------|-------------|
| C1 | ✅ | **EcommerceSignals** — Detección de plataforma, price_mechanism, cart_architecture, faceted_nav, product_schema desde HTML estático. |
| C2 | ✅ | **PDP sample** — Fetch de 1 PDP extraído del HTML de categoría. Compara render mode, precio, schema y protección. |
| C3 | ✅ | **Platform-aware classify** — Reglas HYBRID para plataformas SSR e-commerce (Magento, WooCommerce, etc.) y frameworks headless (Next.js, Nuxt). |

---

## Testing / Validación real

| ID | Estado | Descripción |
|----|--------|-------------|
| T1 | ✅ | **Integration tests contra URLs reales** — 3 sitios: `books.toscrape.com` (estático, baseline), `buscalibre.cl/libros/computacion` (PrestaShop, API-driven), `mercadolibre.cl` (Cloudfront WAF, cookie consent). 36 assertions con skip automático ante challenge pages. `make test-real`. |
| T2 | 🔲 | **Señales faltantes por plataforma** — Mantener un log de falsos negativos: sitios reales donde el clasificador erró (e.g., WooCommerce sin `wc-cart-fragments`, Cloudflare con fingerprint no detectado). Cada caso real documentado se convierte en una fixture y un test. |
