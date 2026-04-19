# STEP 8 — main.py + report/ [CHECKPOINT]

**Implementa en este orden:** `report/terminal.py` → `report/json_export.py` → `main.py`

---

## CLI Interface

```bash
python main.py --url https://example.com
python main.py --url https://example.com --module legal
python main.py --url https://example.com --json
python main.py --url https://example.com --json --output report.json
# Flags: --timeout INT, --ua TEXT, --verbose, --no-color, --skip MODULE, --deep
```

---

## Orchestration

```python
results = await asyncio.gather(
    run_module("legal", analyze_legal(url, config)),
    run_module("classifier", classify_page(url, config)),
    run_module("auth_detector", detect_auth(url, config)),
    run_module("api_detector", detect_apis(url, config)),
    run_module("pagination", detect_pagination(url, config)),
    run_module("antibot", analyze_antibot(url, config)),
    return_exceptions=False,
)
# recommender corre al final con lo que hay
```

---

## Secciones del report terminal (en orden)

1. Header: URL | timestamp | duración total
2. Legal Scope — robots.txt | sitemap | ToS risk (GREEN=LOW, YELLOW=MEDIUM, RED=HIGH) | product_sitemap_url si existe
3. Page Classification — badge + frameworks + CMS + server + CDN + locales + `mobile_differs` + structured data types + `estimated_pages` + `internal_link_count`
4. **E-Commerce Signals** — visible solo si `classifier.ecommerce.is_ecommerce = True`:
   - Platform (CMS) | is_product_page | has_cart | has_price_signals | has_inventory_signals | has_review_signals
   - price_mechanism (GREEN si SERVER_SIDE, YELLOW si CLIENT_SIDE, DIM si UNKNOWN)
   - cart_architecture | has_faceted_nav
5. Security & Freshness — tabla de security headers + cache_control + last_modified
6. Auth & Access — type + paywall + cookie consent (YELLOW si required, RED si HARD paywall)
7. API Endpoints — tabla con type y auth status (incluir tipos e-commerce: WooCommerce-REST, Magento-REST, etc.)
8. Pagination — type + parameter + requires_js + `has_faceted_nav` badge si True
9. Anti-Bot Score — progress bar 0–10 + tabla de 7 dimensiones
10. Recommendations — lista rankeada + resumen + complejidad
11. Footer: `Modules completed: N/7 | Partial failures: [lista]`

---

**[CHECKPOINT 8]** — Ejecuta:
```bash
python main.py scan --url https://example.com
python main.py scan --url https://news.ycombinator.com
python main.py scan --url https://example.com --json | python -m json.tool | head -30
```
Las 3 deben completar sin excepción. El JSON debe ser válido.
