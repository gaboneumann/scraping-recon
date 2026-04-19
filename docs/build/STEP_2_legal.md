# STEP 2 — modules/legal.py [CHECKPOINT]

**Importa desde:** `utils.http`, `models.schemas.LegalResult`

---

## robots.txt

- Fetch con **2 UAs**: `UA_CHROME` y `UA_GOOGLEBOT` (eliminar `UA_PYTHON` — señal nula para e-commerce)
- Parsear con `urllib.robotparser.RobotFileParser`
- Si el contenido difiere entre UAs (comparar texto normalizado): `ua_specific=True`
- `target_path_allowed`: verificar si el path de la URL target está permitido para `UA_CHROME`
- Si retorna 404: `found=False`, campos en default permissivo
- Si retorna HTML: `found=False`, flag en error log
- El slot de request liberado (1 request) se usa para el cuarto path de sitemap

---

## Sitemap

Probar en orden — parar al primer 200:
```python
SITEMAP_PATHS = [
    "/sitemap.xml",
    "/sitemap_index.xml",
    "/sitemap_products.xml",       # Shopify — contiene todas las URLs de productos
    "/sitemap-products.xml",       # Magento / WooCommerce variante
    "/media/sitemap/sitemap.xml",  # Magento media path
]
```
- Si encuentra `<sitemapindex>`, contar `<sitemap>` children (solo primer nivel)
- `url_count`: contar `<url>` o `<sitemap>` según el tipo
- Si el path contiene "product": guardar URL en `SitemapResult.product_sitemap_url`

---

## ToS

- Probar paths: `/terms`, `/tos`, `/legal`, `/terms-of-service` (omitir `/privacy` — no contiene restricciones de scraping)
- Si ninguno existe, parsear footer con BS4 buscando links con texto "terms", "tos", "legal"
- Keywords (ampliados para e-commerce):
```python
TOS_KEYWORDS = [
    # Restricciones genéricas
    "scraping", "crawling", "automated", "bot", "robot",
    "data extraction", "commercial use", "prohibited",
    # Restricciones específicas de retail
    "price data", "product data", "price monitoring",
    "price comparison", "competitive intelligence",
    "resell", "redistribute", "bulk download",
    "systematic access", "screen scraping",
]
```
- Risk level: `HIGH` (≥2 keywords) | `MEDIUM` (1 keyword OR no ToS + robots restrictivo) | `LOW` (0 keywords) | `UNKNOWN` (nada encontrado)
- Si ToS está detrás de auth wall: `found=False`, `risk_level="UNKNOWN"`

---

**[CHECKPOINT 2]** — Ejecuta:
```bash
python -c "
import asyncio
from modules.legal import analyze_legal

async def test():
    result = await analyze_legal('https://example.com', timeout=10)
    print(result.model_dump_json(indent=2))

asyncio.run(test())
"
```
Expected: `robots_txt.found=True`, `sitemap.found=False`, `tos.found=False`.
