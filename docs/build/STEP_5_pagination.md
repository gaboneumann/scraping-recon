# STEP 5 — modules/pagination.py [CHECKPOINT]

**Importa desde:** `utils.http`, `models.schemas.PaginationResult`

---

## Patrones

```python
QUERY_PARAM_PATTERNS = [
    # Genéricos
    "page", "p", "offset", "start", "pg",
    # E-commerce platform specific
    "currentPage",   # Magento GraphQL / SFCC
    "pageNumber",    # BigCommerce
    "pn",            # Retailer abreviación
    "cp",            # BigCommerce category page
    "sz",            # Salesforce CC (page size, paired with 'start')
]

PATH_PATTERNS = [
    r"/page/\d+",          # WordPress / WooCommerce
    r"/p/\d+",             # Forma corta
    r"/page-\d+",          # Variante con guion
    r"/[^/]+-\d+\.html$",  # Magento SEO URLs: /blue-shirts-2.html
]

CURSOR_PATTERNS    = ["cursor", "after", "before", "next_token"]
LOAD_MORE_PATTERNS = ["load-more", "btn-next", "ver más", "load_more", "loadmore"]

# Parámetros de faceted navigation — no paginación, pero crítico para e-commerce
FACETED_NAV_PARAMS = [
    "color", "size", "brand", "price", "rating", "sort", "sortBy",
    "sort_by", "orderBy", "refinementList", "filters", "facets",
]
FACETED_NAV_CLASSES = ["facet", "filter-panel", "refinement", "layered-nav", "plp-filters"]
```

---

## Orden de prioridad

1. `LINK_REL_NEXT`: `soup.find('link', rel='next')` — prioridad máxima
2. `QUERY_PARAM`: buscar en `<a href>` parámetros de la lista
3. `PATH`: regex contra todos los `<a href>`
4. **FACETED_NAV check** (paralelo, no exclusivo): si hay elementos con class en `FACETED_NAV_CLASSES` Y links con params de `FACETED_NAV_PARAMS` → setear `has_faceted_nav=True`. No cambia el `type` principal.
5. `CURSOR`: buscar en `<a href>` y JSON state blobs
6. `LOAD_MORE`: buscar class/id/text que coincidan
7. `INFINITE_SCROLL`: buscar `IntersectionObserver` o `scroll` event listeners en JS
8. `NONE`: ninguna señal

`requires_js=True` si el tipo es `LOAD_MORE` o `INFINITE_SCROLL`.
`has_faceted_nav` se evalúa siempre, independiente del tipo principal.

---

**[CHECKPOINT 5]** — Ejecuta:
```bash
python -c "
import asyncio
from modules.pagination import detect_pagination

async def test():
    for url in ['https://news.ycombinator.com', 'https://example.com']:
        r = await detect_pagination(url, timeout=10)
        print(url.split('/')[2], r.type, r.parameter, r.requires_js)

asyncio.run(test())
"
```
Expected HN: `QUERY_PARAM / p / False`.
