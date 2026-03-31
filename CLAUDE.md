# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> **Para el agente**: Este archivo es tu contrato de construcción.
> Sigue el orden exacto. No combines pasos. No implementes lo que no te pido.
> Cada sección termina con un [CHECKPOINT] — detente ahí y muestra output.

---

## Environment

- OS: Ubuntu 24 (WSL2) on Windows
- Python: 3.12.3
- Venv: `source venv/bin/activate` (ya creado)
- Working directory: `~/workspace/projects/web_scraping/scraping_recon`

---

## Execution Protocol (inmutable)

```
1. Lee la sección completa antes de escribir código
2. Implementa exactamente lo descrito — ni más, ni menos
3. Ejecuta y muestra el output real del terminal
4. Espera mi confirmación antes de continuar
5. Si una dependencia falla, reporta el error exacto y propón alternativa
6. Si encuentras ambigüedad, pregunta antes de asumir
```

**Reglas de código:**
- Imports relativos dentro del paquete siempre
- Type hints en todas las funciones
- Docstring en todos los módulos y funciones públicas
- Sin estado global — configuración siempre como parámetro explícito

---

## Dependency Matrix

Instala en este orden. Si falla, usa el fallback indicado.

| Package        | Install                           | Fallback si falla                               |
|----------------|-----------------------------------|-------------------------------------------------|
| httpx          | `pip install httpx[http2]`        | `pip install requests` + reportar              |
| curl_cffi      | `pip install curl_cffi`           | usar httpx puro + flag `TLS_IMPERSONATION=False` |
| beautifulsoup4 | `pip install beautifulsoup4 lxml` | `pip install beautifulsoup4 html.parser`        |
| dnspython      | `pip install dnspython`           | omitir DNS module + flag `DNS_UNAVAILABLE`      |
| rich           | `pip install rich`                | sin fallback — crítico para output              |
| typer          | `pip install typer`               | sin fallback — crítico para CLI                 |
| pydantic       | `pip install pydantic`            | sin fallback — crítico para schemas             |
| wafw00f        | `pip install wafw00f`             | usar header-based detection solamente           |
| playwright     | `pip install playwright` + `playwright install chromium` | sin fallback — requerido para `--deep` mode |

> Instala y verifica cada paquete antes de usarlo. Si `import X` falla en runtime, reporta y aplica el fallback — nunca silencies el error.
> Playwright requiere dos pasos: primero el paquete Python, luego el binario del browser (`playwright install chromium`).

---

## Project Structure

```
scraping_recon/
├── main.py                  ← CLI entry point (Typer)
├── config.py                ← Settings, defaults, constants
├── models/
│   ├── __init__.py
│   └── schemas.py           ← Pydantic models — fuente de verdad de todos los outputs
├── modules/
│   ├── __init__.py
│   ├── legal.py
│   ├── classifier.py
│   ├── auth_detector.py
│   ├── antibot.py
│   ├── api_detector.py
│   ├── pagination.py
│   └── recommender.py
├── report/
│   ├── __init__.py
│   ├── terminal.py
│   └── json_export.py
└── utils/
    ├── __init__.py
    ├── http.py              ← HTTP client factory (httpx + curl_cffi)
    ├── tls_test.py          ← TLS fingerprint comparison
    └── graceful.py          ← Module runner con timeout + exception capture
```

---

## HTTP Request Budget

**Máximo 25 requests por scan completo.** Si un módulo va a exceder su presupuesto, prioriza los requests de mayor señal y omite los marginales. Nunca superes 25 en total.

| Módulo        | Max requests | Notas                                          |
|---------------|-------------|------------------------------------------------|
| legal         | 6           | 3 UAs robots.txt + sitemap + 2 ToS             |
| classifier    | 3           | 1 fetch + 1 DNS + 1 mobile UA compare          |
| auth_detector | 2           | reutiliza fetch de classifier + 1 probe        |
| api_detector  | 3           | reutiliza fetch + hasta 2 GraphQL probes       |
| pagination    | 1           | reutilizar fetch de classifier                 |
| antibot       | 12          | 8 rate-limit + 3 TLS + 1 base                  |
| recommender   | 0           | función pura                                   |
| **Total**     | **≤ 27**    |                                                |

---

## STEP 0 — models/schemas.py [CHECKPOINT]

**Implementa primero. Todos los módulos importan desde aquí.**

Define los Pydantic models para cada módulo. Si los schemas cambian, actualiza este archivo y notifícame antes de continuar.

```python
"""
models/schemas.py
Pydantic contracts for all scraping_recon module outputs.
Import from here — never define inline schemas in modules.
"""
from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field


class RobotsTxtResult(BaseModel):
    found: bool
    ua_specific: bool
    crawl_delay_seconds: int | None
    target_path_allowed: bool
    blocked_paths: list[str]
    sitemap_declared: str | None


class SitemapResult(BaseModel):
    found: bool
    type: str
    url_count: int | None
    last_modified: str | None


class TosResult(BaseModel):
    found: bool
    url: str | None
    risk_level: Literal["LOW", "MEDIUM", "HIGH", "UNKNOWN"]
    flagged_keywords: list[str]


class LegalResult(BaseModel):
    robots_txt: RobotsTxtResult
    sitemap: SitemapResult
    tos: TosResult


class StructuredDataResult(BaseModel):
    json_ld_found: bool
    schema_types: list[str]        # e.g. ["Product", "BreadcrumbList"]
    microdata_found: bool
    opengraph_found: bool
    scraping_shortcut: bool        # True si JSON-LD cubre campos objetivo


class SecurityHeadersResult(BaseModel):
    csp: bool                      # Content-Security-Policy presente
    hsts: bool                     # Strict-Transport-Security presente
    x_frame_options: bool
    x_content_type_options: bool
    csp_blocks_inline: bool        # CSP contiene "unsafe-inline" ausente → scripts inline bloqueados


class ClassifierResult(BaseModel):
    type: Literal["STATIC", "DYNAMIC", "HYBRID", "API_DRIVEN", "UNKNOWN"]
    confidence: Literal["HIGH", "MEDIUM", "LOW"]
    js_frameworks: list[str]
    cms: str | None
    server: str | None
    cdn: str | None
    infrastructure: list[str]
    dns_signals: dict[str, str]
    content_ratio: float
    response_time_ms: int
    structured_data: StructuredDataResult
    security_headers: SecurityHeadersResult
    cache_control: str | None      # valor raw del header Cache-Control
    last_modified: str | None      # valor raw del header Last-Modified
    locales: list[str]             # códigos detectados vía hreflang o rutas (/es/, /en/)
    mobile_differs: bool           # True si mobile UA entrega contenido distinto
    internal_link_count: int       # links internos únicos en el homepage
    estimated_pages: Literal["<50", "50-500", "500-5000", ">5000", "UNKNOWN"]


class ApiEndpoint(BaseModel):
    url: str
    type: Literal["REST", "GraphQL", "WebSocket", "Unknown"]
    authenticated: bool | None


class ApiDetectorResult(BaseModel):
    internal_api_found: bool
    endpoints: list[ApiEndpoint]
    state_blobs_found: list[str]
    recommendation: str
    endpoints_may_be_incomplete: bool  # True si el sitio es DYNAMIC — endpoints JS no interceptables sin browser


class PaginationResult(BaseModel):
    type: Literal[
        "QUERY_PARAM", "PATH", "CURSOR", "LOAD_MORE",
        "INFINITE_SCROLL", "LINK_REL_NEXT", "NONE", "UNKNOWN"
    ]
    parameter: str | None
    example_next_url: str | None
    requires_js: bool


class WafDimension(BaseModel):
    score: int = Field(ge=0, le=3)
    vendor: str | None
    confidence: str


class TlsDimension(BaseModel):
    score: int = Field(ge=0, le=3)
    sensitivity: str
    client_results: dict[str, str]


class RateLimitDimension(BaseModel):
    score: int = Field(ge=0, le=3)
    triggered_at: int | None
    error_type: str | None


class CaptchaDimension(BaseModel):
    score: int = Field(ge=0, le=3)
    provider: str | None
    version: str | None


class FingerprintDimension(BaseModel):
    score: int = Field(ge=0, le=3)
    libraries: list[str]


class HoneypotDimension(BaseModel):
    score: int = Field(ge=0, le=3)
    count: int
    locations: list[str]


class IpRepDimension(BaseModel):
    score: int = Field(ge=0, le=3)
    geo_block: bool
    proxy_recommendation: str


class AntibotDimensions(BaseModel):
    waf: WafDimension
    tls_fingerprint: TlsDimension
    rate_limiting: RateLimitDimension
    captcha: CaptchaDimension
    browser_fingerprinting: FingerprintDimension
    honeypots: HoneypotDimension
    ip_reputation: IpRepDimension


class AntibotResult(BaseModel):
    overall_score: float = Field(ge=0.0, le=10.0)
    overall_level: Literal["NONE", "LOW", "MEDIUM", "HIGH", "EXTREME"]
    dimensions: AntibotDimensions


class RecommenderResult(BaseModel):
    primary_library: str
    secondary_library: str | None
    managed_api_suggested: bool
    managed_api_options: list[str]
    additional_flags: list[str]
    estimated_complexity: int = Field(ge=1, le=10)
    estimated_dev_time: str
    full_stack_recommendation: str


class AuthResult(BaseModel):
    required: bool
    type: Literal["NONE", "FORM", "OAUTH", "API_KEY", "PAYWALL", "COOKIE_CONSENT", "UNKNOWN"]
    login_url: str | None
    paywall_type: Literal["HARD", "METERED", "NONE"] | None
    cookie_consent_blocking: bool


class ModuleStatus(BaseModel):
    name: str
    status: Literal["OK", "INCOMPLETE", "BLOCKED", "SKIPPED"]
    error: str | None = None


class ReconReport(BaseModel):
    url: str
    timestamp: str
    scan_duration_ms: int
    modules_status: list[ModuleStatus]
    legal: LegalResult | None = None
    classifier: ClassifierResult | None = None
    auth: AuthResult | None = None
    api_detector: ApiDetectorResult | None = None
    pagination: PaginationResult | None = None
    antibot: AntibotResult | None = None
    recommender: RecommenderResult | None = None
```

**[CHECKPOINT 0]** — Ejecuta:
```bash
python -c "from models.schemas import ReconReport; print('schemas OK')"
```
Muéstrame el output. No continúes si hay errores de importación.

---

## STEP 1 — utils/graceful.py [CHECKPOINT]

Runner genérico que envuelve cada módulo con timeout de 20s, captura de excepción sin propagación, y retorno de `ModuleStatus` estructurado.

```python
"""
utils/graceful.py
Wraps async module coroutines with timeout and structured error capture.
All modules are invoked through run_module() — never called directly.
"""
import asyncio
import traceback
from typing import Any, Callable, Coroutine
from models.schemas import ModuleStatus


async def run_module(
    name: str,
    coro: Coroutine[Any, Any, Any],
    timeout: float = 20.0,
) -> tuple[Any | None, ModuleStatus]:
    """
    Execute a module coroutine with timeout and exception capture.

    Returns:
        (result, ModuleStatus) — result is None on failure.
    """
    try:
        result = await asyncio.wait_for(coro, timeout=timeout)
        return result, ModuleStatus(name=name, status="OK")
    except asyncio.TimeoutError:
        return None, ModuleStatus(
            name=name,
            status="INCOMPLETE",
            error=f"Timed out after {timeout}s",
        )
    except Exception:
        return None, ModuleStatus(
            name=name,
            status="INCOMPLETE",
            error=traceback.format_exc(limit=3),
        )
```

**[CHECKPOINT 1]** — Ejecuta:
```bash
python -c "
import asyncio
from utils.graceful import run_module

async def test():
    async def ok(): return 42
    async def boom(): raise ValueError('test error')
    async def slow():
        await asyncio.sleep(99)

    r1, s1 = await run_module('ok', ok())
    r2, s2 = await run_module('boom', boom())
    r3, s3 = await run_module('slow', slow(), timeout=0.1)
    print(s1.status, r1)           # OK 42
    print(s2.status, s2.error[:30])  # INCOMPLETE ...
    print(s3.status, s3.error)     # INCOMPLETE Timed out...

asyncio.run(test())
"
```

---

## STEP 2 — utils/http.py [CHECKPOINT]

HTTP client factory. Centraliza toda la lógica de requests. Sin estado global — cada llamada recibe config explícita.

**Funciones a implementar:**
1. `make_request(url, ua, timeout, verify_ssl, impersonate)` → `(status_code, headers, text, response_time_ms)`
2. `try_with_fallback_uas(url, config)` → prueba 3 UAs en secuencia, retorna el primero exitoso
3. `detect_block(status, text)` → `bool` — detecta 403/503 con body de WAF

**UAs:**
```python
UA_PYTHON    = "python-httpx/0.27"
UA_GOOGLEBOT = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
UA_CHROME    = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
UA_MOBILE    = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
```

**Funciones adicionales:**
4. `compare_mobile_desktop(url, timeout)` → `dict` con `content_differs: bool, size_diff_pct: float`
   - Fetch con `UA_CHROME` y luego con `UA_MOBILE`
   - `size_diff_pct = abs(len(desktop) - len(mobile)) / max(len(desktop), 1)`
   - `content_differs=True` si `size_diff_pct > 0.15` o si los títulos `<h1>` difieren

**Reglas:**
- Timeout default: `config.timeout` (no hardcodear)
- Retry: 2 intentos con 1s backoff en `ConnectionError` y `TimeoutError`
- SSL error: retry con `verify=False` + loguea el warning
- Máximo 5MB de contenido (stream con límite)
- Seguir redirects hasta 10, loguear la cadena completa
- Si `curl_cffi` no está instalado: usar `httpx` solamente, setear `TLS_IMPERSONATION_AVAILABLE = False`

**[CHECKPOINT 2]** — Ejecuta:
```bash
python -c "
import asyncio
from utils.http import make_request

async def test():
    status, headers, text, ms = await make_request('https://httpbin.org/get', timeout=10)
    print(f'status={status} time={ms}ms len={len(text)}')
    print('server:', headers.get('server', 'n/a'))

asyncio.run(test())
"
```

---

## STEP 3 — modules/legal.py [CHECKPOINT]

**Importa desde:** `utils.http`, `models.schemas.LegalResult`

### robots.txt
- Fetch con los 3 UAs de `utils/http.py`
- Parsear con `urllib.robotparser.RobotFileParser`
- Si el contenido difiere entre UAs (comparar texto normalizado): `ua_specific=True`
- `target_path_allowed`: verificar si el path de la URL target está permitido para `UA_CHROME`
- Si retorna 404: `found=False`, campos en default permissivo
- Si retorna HTML: `found=False`, flag en error log

### Sitemap
- Probar `/sitemap.xml` primero, luego `/sitemap_index.xml`
- Si encuentra `<sitemapindex>`, contar `<sitemap>` children (solo primer nivel)
- `url_count`: contar `<url>` o `<sitemap>` según el tipo

### ToS
- Probar paths: `/terms`, `/tos`, `/legal`, `/terms-of-service`, `/privacy`
- Si ninguno existe, parsear footer con BS4 buscando links con texto "terms", "tos", "legal"
- Keywords: `scraping`, `crawling`, `automated`, `bot`, `robot`, `data extraction`, `commercial use`, `prohibited`
- Risk level: `HIGH` (≥2 keywords) | `MEDIUM` (1 keyword OR no ToS + robots restrictivo) | `LOW` (0 keywords) | `UNKNOWN` (nada encontrado)
- Si ToS está detrás de auth wall: `found=False`, `risk_level="UNKNOWN"`

**[CHECKPOINT 3]** — Ejecuta:
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

---

## STEP 4 — modules/classifier.py [CHECKPOINT]

**Importa desde:** `utils.http`, `models.schemas.ClassifierResult`

### Señales de detección

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
    "WordPress":   {"html": ["/wp-content/", "/wp-includes/", "wp-json"], "headers": []},
    "Shopify":     {"html": ["cdn.shopify.com", "Shopify.theme"], "headers": []},
    "Drupal":      {"html": ["Drupal.settings"], "headers": ["x-drupal-cache"]},
    "Joomla":      {"html": ["/media/jui/"], "headers": []},
    "Wix":         {"html": [], "headers": ["x-wix-request-id"]},
    "Squarespace": {"html": ["squarespace.com"], "headers": []},
    "Webflow":     {"html": ["data-wf-"], "headers": []},
}

CDN_SIGNALS = {
    "Cloudflare": ["CF-Ray", "__cf_bm"],
    "Vercel":     ["x-vercel-id"],
    "AWS":        ["x-amz-cf-id", "x-amz-request-id"],
    "Fastly":     ["x-served-by"],
    "Akamai":     ["x-check-cacheable"],
}
```

**DNS** — usar dnspython: resolver A, CNAME, NS, TXT. Si no disponible: `dns_signals={}`.

**Structured data** — buscar en HTML raw y parsear:
```python
SHORTCUT_SCHEMA_TYPES = {"Product", "Offer", "ItemList", "Article", "Review", "Event", "Recipe"}

# json_ld_found: '<script type="application/ld+json"' en HTML
# schema_types: extraer "@type" de cada bloque JSON-LD (puede ser lista o string)
# microdata_found: 'itemscope' en HTML
# opengraph_found: 'property="og:' en HTML
# scraping_shortcut: True si algún schema_type ∈ SHORTCUT_SCHEMA_TYPES
```

**Security headers** — leer directamente de los headers de la respuesta base (sin request adicional):
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

**Content freshness** — leer de headers de la respuesta base (sin request adicional):
```python
cache_control = headers.get("cache-control")        # e.g. "max-age=3600, public"
last_modified = headers.get("last-modified")        # e.g. "Wed, 21 Oct 2024 07:28:00 GMT"
```

**Multi-locale** — buscar en HTML ya parseado:
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

**Crawl scope** — estimar desde el HTML ya parseado (sin requests adicionales):
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

**Mobile parity** — llamar a `compare_mobile_desktop(url, timeout)` de `utils.http`:
- Resultado popula `mobile_differs` en `ClassifierResult`
- Usa 1 request adicional del budget

**Clasificación final:**
```
STATIC:     content_ratio ≥ 0.15 AND no JS frameworks
DYNAMIC:    JS frameworks detectados OR content_ratio < 0.15
API_DRIVEN: content_ratio < 0.05 AND body sin estructuras HTML normales
HYBRID:     STATIC + frameworks de hidratación (HTMX, Astro)
UNKNOWN:    ninguna señal suficiente
```

**[CHECKPOINT 4]** — Ejecuta:
```bash
python -c "
import asyncio
from modules.classifier import classify_page

async def test():
    for url in ['https://example.com', 'https://news.ycombinator.com']:
        r = await classify_page(url, timeout=10)
        print(url.split('/')[2], r.type, r.confidence, r.js_frameworks)

asyncio.run(test())
"
```
Expected: `example.com → STATIC/HIGH`, `news.ycombinator.com → STATIC/HIGH`.

---

## STEP 5 — modules/api_detector.py [CHECKPOINT]

**Importa desde:** `utils.http`, `models.schemas.ApiDetectorResult`

```python
API_PATTERNS = [
    r'fetch\(["\']([^"\']+)["\']',
    r'axios\.(?:get|post|put|delete)\(["\']([^"\']+)["\']',
    r'XMLHttpRequest.*?\.open\(["\'](?:GET|POST)["\'],\s*["\']([^"\']+)["\']',
    r'\$\.ajax\(.*?url:\s*["\']([^"\']+)["\']',
    r'((?:/api/|/v\d+/|/graphql)[a-zA-Z0-9/_-]+)',
    r'(wss?://[^\s"\']+)',
]

STATE_PATTERNS = [
    "__NEXT_DATA__",
    "window.__INITIAL_STATE__",
    "window.__REDUX_STATE__",
    "window.__PRELOADED_STATE__",
]
```

**GraphQL introspection** — si se encuentra `/graphql` o `/api/graphql`:
```python
INTROSPECTION_QUERY = '{"query":"{__typename}"}'
```
POST con `Content-Type: application/json`. Si retorna 200 con `data.__typename`: `introspection_enabled=True`.

**Deduplicación:** URLs repetidas → una sola entrada. Excluir assets (`.js`, `.css`, `.png`, `.woff`).

**AJAX/XHR limitation** — setear `endpoints_may_be_incomplete=True` cuando el `ClassifierResult.type` sea `DYNAMIC` o `API_DRIVEN` y no se hayan encontrado endpoints. Agregar en `recommendation`: `"Site renders via JS — intercept XHR with Playwright (--deep) for complete endpoint map."`. No silenciar este gap.

**[CHECKPOINT 5]** — Ejecuta:
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

---

## STEP 6 — modules/pagination.py [CHECKPOINT]

**Importa desde:** `utils.http`, `models.schemas.PaginationResult`

```python
QUERY_PARAM_PATTERNS = ["page", "p", "offset", "start", "pg"]
PATH_PATTERNS         = [r"/page/\d+", r"/p/\d+"]
CURSOR_PATTERNS       = ["cursor", "after", "before", "next_token"]
LOAD_MORE_PATTERNS    = ["load-more", "btn-next", "ver más", "load_more", "loadmore"]
```

**Orden de prioridad:**
1. `LINK_REL_NEXT`: `soup.find('link', rel='next')` — prioridad máxima
2. `QUERY_PARAM`: buscar en `<a href>` parámetros de la lista
3. `PATH`: regex contra todos los `<a href>`
4. `CURSOR`: buscar en `<a href>` y JSON state blobs
5. `LOAD_MORE`: buscar class/id/text que coincidan
6. `INFINITE_SCROLL`: buscar `IntersectionObserver` o `scroll` event listeners en JS
7. `NONE`: ninguna señal

`requires_js=True` si el tipo es `LOAD_MORE` o `INFINITE_SCROLL`.

**[CHECKPOINT 6]** — Ejecuta:
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

---

## STEP 6b — modules/auth_detector.py [CHECKPOINT]

**Importa desde:** `utils.http`, `models.schemas.AuthResult`
**Reutiliza el HTML ya fetcheado por classifier — solo añade 1 request de probe si es necesario.**

### Detección de login wall

```python
LOGIN_FORM_SELECTORS = [
    'input[type="password"]',
    'form[action*="login"]',
    'form[action*="signin"]',
    'form[action*="session"]',
]

LOGIN_LINK_SELECTORS = [
    'a[href*="/login"]',
    'a[href*="/signin"]',
    'a[href*="/auth"]',
    'a[href*="/account"]',
]

OAUTH_DOMAINS = [
    "accounts.google.com",
    "facebook.com/login",
    "twitter.com/oauth",
    "github.com/login/oauth",
    "login.microsoftonline.com",
    "appleid.apple.com",
]
```

- Si `input[type=password]` en DOM: `type="FORM"`, `login_url` = `form[action]`
- Si redirect chain (de `make_request`) pasa por un `OAUTH_DOMAIN`: `type="OAUTH"`
- Si response inicial es 401 con header `WWW-Authenticate`: `type="API_KEY"`
- Si solo hay links de login (no form): `type="FORM"`, `required=True`
- Si ninguna señal: `required=False`, `type="NONE"`

### Detección de paywall

```python
PAYWALL_HARD_SIGNALS = [
    "subscribe to read", "subscribers only", "sign up to continue",
    "create an account to", "members only", "premium content",
]
PAYWALL_METERED_SIGNALS = [
    "articles remaining", "free articles left", "monthly limit",
    "you have read", "stories this month",
]
```

- Si señales HARD Y `<article>` o `<main>` tiene menos de 200 palabras visibles: `paywall_type="HARD"`
- Si señales METERED: `paywall_type="METERED"`
- Sino: `paywall_type="NONE"`

### Detección de cookie consent wall

```python
CONSENT_SIGNALS = {
    "OneTrust":  ["onetrust-banner-sdk", "onetrust-accept-btn-handler"],
    "Cookiebot": ["CybotCookiebotDialog"],
    "TrustArc":  ["truste-consent-track"],
    "Quantcast": ["qc-cmp2-ui"],
    "Generic":   ["cookie-consent", "cookie-banner", "gdpr-banner"],
}
```

`cookie_consent_blocking=True` si se detecta alguna señal Y el `<body>` tiene `overflow:hidden` o el banner tiene `position:fixed` con `z-index` alto (> 999).

**[CHECKPOINT 6b]** — Ejecuta:
```bash
python -c "
import asyncio
from modules.auth_detector import detect_auth

async def test():
    for url in ['https://example.com', 'https://quotes.toscrape.com']:
        r = await detect_auth(url, timeout=10)
        print(url.split('/')[2], r.required, r.type, r.cookie_consent_blocking)

asyncio.run(test())
"
```
Expected: ambos `required=False`, `type=NONE`, `cookie_consent_blocking=False`.

---

## STEP 7 — modules/antibot.py [CHECKPOINT]

**Importa desde:** `utils.http`, `utils.tls_test`, `models.schemas.AntibotResult`

### Dimension 1: WAF
```python
# Primero: subprocess wafw00f
result = subprocess.run(
    ["wafw00f", url, "-o", "/tmp/wafw00f.json", "-f", "json"],
    capture_output=True, timeout=15
)
# Si falla: header detection como fallback

WAF_HEADER_SIGNALS = {
    "Cloudflare":  (3, ["CF-Ray", "__cf_bm"]),
    "DataDome":    (3, ["x-datadome"]),
    "PerimeterX":  (3, ["_px2", "pxCaptcha"]),
    "Akamai":      (3, ["x-akamai-transformed"]),
    "Kasada":      (3, ["x-kasada-info"]),
    "Imperva":     (2, ["incap_ses"]),
    "Sucuri":      (2, ["x-sucuri-id"]),
}
```

### Dimension 2: TLS
Delegar a `utils/tls_test.py`. Comparar `httpx` vs `curl_cffi chrome110` vs `curl_cffi safari17_0`. Métrica: `(status_code, len(body))` — si difiere entre clientes → TLS sensitivity detectada.

### Dimension 3: Rate Limiting
**⚠️ Delay mínimo entre requests: 0.3s. No reducir.**
```python
for i in range(8):
    status, _, _, _ = await make_request(url, ...)
    await asyncio.sleep(0.3)
    if status == 429: triggered_at = i; score = 3; break
    if status in (503, 520): score = 2; break
# Si response_time_ms último ≥ 3x primero: score=1
```

### Dimensions 4–7 (sobre HTML ya fetcheado — sin requests adicionales)
```python
CAPTCHA_SIGNALS = {
    "reCAPTCHA v2": (2, ["data-sitekey"]),
    "reCAPTCHA v3": (3, ["render="]),
    "hCaptcha":     (2, ["hcaptcha.com"]),
    "Turnstile":    (3, ["challenges.cloudflare.com/turnstile"]),
    "FunCaptcha":   (3, ["funcaptcha.com"]),
}

FINGERPRINT_SIGNALS = {
    "FingerprintJS":   (2, ["fpjs.io", "fingerprint.com"]),
    "Canvas FP":       (2, ["toDataURL", "getImageData"]),
    "AudioContext FP": (2, ["AudioContext", "AnalyserNode"]),
    "Webdriver check": (3, ["navigator.webdriver"]),
}

HONEYPOT_SELECTORS = [
    "[style*='display:none'] a",
    "[style*='visibility:hidden'] a",
    "[style*='left:-9999'] a",
    "[style*='left: -9999'] a",
]
```

### Score final
```python
score = sum([waf.score, tls.score, rate_limit.score, captcha.score,
             fingerprint.score, honeypot.score, ip_rep.score])
overall_score = round((score / 21) * 10, 2)

level = (
    "NONE"    if overall_score == 0   else
    "LOW"     if overall_score < 3    else
    "MEDIUM"  if overall_score < 5    else
    "HIGH"    if overall_score < 8    else
    "EXTREME"
)
```

**[CHECKPOINT 7]** — Ejecuta:
```bash
python -c "
import asyncio
from modules.antibot import analyze_antibot

async def test():
    r = await analyze_antibot('https://news.ycombinator.com', timeout=30)
    print(f'score={r.overall_score} level={r.overall_level}')
    for dim, val in r.dimensions.model_dump().items():
        print(f'  {dim}: {val[\"score\"]}')

asyncio.run(test())
"
```
Expected HN: score < 3, level=LOW o NONE.

---

## STEP 8 — modules/recommender.py [CHECKPOINT]

**No hace requests.** Recibe el `ReconReport` parcial y produce `RecommenderResult`. Cada campo puede ser `None` — manejar sin excepción.

```python
def build_recommendation(report: ReconReport) -> RecommenderResult:
    """Pure function. No I/O. Returns RecommenderResult."""
```

**Árbol de decisión (orden exacto):**
```
1. Si antibot is None → primary="httpx", secondary=None, complejidad=3
2. Si antibot.overall_score >= 8 →
       primary="playwright + playwright-stealth"
       secondary="curl_cffi + residential proxy"
       managed_api_suggested=True
       managed_api_options=["ZenRows", "ScraperAPI", "Scrapfly"]
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

**Flags adicionales (evaluar siempre):**
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
```

**[CHECKPOINT 8]** — Test unitario puro:
```bash
python -c "
from models.schemas import ReconReport, ModuleStatus
from modules.recommender import build_recommendation
from datetime import datetime

report = ReconReport(
    url='https://test.com',
    timestamp=datetime.now().isoformat(),
    scan_duration_ms=0,
    modules_status=[],
)
r = build_recommendation(report)
print(r.primary_library)
print(r.estimated_complexity)
"
```

---

## STEP 9 — main.py + report/ [CHECKPOINT]

**Implementa en este orden:** `report/terminal.py` → `report/json_export.py` → `main.py`

### CLI Interface
```bash
python main.py --url https://example.com
python main.py --url https://example.com --module legal
python main.py --url https://example.com --json
python main.py --url https://example.com --json --output report.json
# Flags: --timeout INT, --ua TEXT, --verbose, --no-color, --skip MODULE, --deep
```

### Orchestration
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

### Secciones del report terminal (en orden):
1. Header: URL | timestamp | duración total
2. Legal Scope — robots.txt | sitemap | ToS risk (GREEN=LOW, YELLOW=MEDIUM, RED=HIGH)
3. Page Classification — badge + frameworks + CMS + server + CDN + locales + `mobile_differs` + structured data types + `estimated_pages` + `internal_link_count`
4. Security & Freshness — tabla de security headers + cache_control + last_modified
5. Auth & Access — type + paywall + cookie consent (YELLOW si required, RED si HARD paywall)
6. API Endpoints — tabla con type y auth status
7. Pagination — type + parameter + requires_js
8. Anti-Bot Score — progress bar 0–10 + tabla de 7 dimensiones
9. Recommendations — lista rankeada + resumen + complejidad
10. Footer: `Modules completed: N/7 | Partial failures: [lista]`

**[CHECKPOINT 9]** — Ejecuta:
```bash
python main.py scan --url https://example.com
python main.py scan --url https://news.ycombinator.com
python main.py scan --url https://example.com --json | python -m json.tool | head -30
```
Las 3 deben completar sin excepción. El JSON debe ser válido.

---

## STEP 10 — requirements.txt [CHECKPOINT FINAL]

Solo después de que todos los módulos pasen sus checkpoints:
```bash
pip freeze > requirements.txt
pip install -r requirements.txt --dry-run
```
