# CLAUDE.md

---

## Project Overview

**Primary Goal**: Pre-scraping intelligence tool for **e-commerce/retail sites** (static, dynamic, hybrid). Analyzes a URL and returns **actionable recommendations** to minimize scraping development time.

**What It Does**: Reports on 7 dimensions (legal scope, site type, APIs, pagination, auth, antibot, e-commerce signals) so you can decide: *"Is it worth scraping? What library should I use? What complexity am I in for?"*

**What It Doesn't Do**: It's NOT a scraper. It doesn't execute complex anti-detection strategies—it *flags* them so you know what to implement in your own scraper.

- **Stack**: Python 3.12 · Typer · httpx + curl_cffi · BeautifulSoup4 · Pydantic · Rich · Playwright (--deep)
- **Architecture**: `main.py` → `modules/` (7 modules: 6 async + recommender sync) → `models/schemas.py` (source of truth) → `report/`
- **Environment**: Ubuntu 24.04 — primary dev
- **Scope**: E-commerce/retail sites across 3 render modes (SSR, CSR, SSR+CSR hybrid)
- **Target Users**: Scrapers building bots for new e-commerce targets (need fast reconnaissance)

---

## Commands Reference

```sh
source .venv/bin/activate

python main.py --url <url>                               # scan completo
python main.py --url <url> --module <name>               # módulo individual (smoke test)
python main.py --url <url> --skip antibot,legal          # saltar módulos
python main.py --url <url> --deep --json -o out.json     # --deep: flag aceptado, lógica Playwright pendiente (BACKLOG E7)
python main.py --help                                    # mostrar todas las opciones

# Testing
make test                                                # unit + integration + coverage
make test-smoke                                          # smoke tests (pipeline completo)
make update-snapshots                                    # regenerar snapshots
.venv/bin/pytest tests/unit/ -v                          # solo unit tests
```

---

## Mapeo Módulo → Decisión

Cada módulo responde una pregunta específica que necesitas antes de scrapear:

| Módulo | Pregunta | Output | Impacto en Decisión |
|--------|----------|--------|-----------------|
| **legal** | ¿Es legal scrapear? | robots.txt, sitemap, análisis ToS | **PARAR o CONTINUAR** |
| **classifier** | ¿Qué tipo de sitio? | SSR/CSR/Hybrid, CMS, frameworks, locales | **Elegir librería** (httpx vs Playwright) |
| **api_detector** | ¿Hay APIs internas? | Endpoints REST/GraphQL encontrados | **Usar API en lugar de HTML** |
| **auth_detector** | ¿Auth requerida? | Login form, OAuth, paywall detectados | **Complejidad de session management** |
| **pagination** | ¿Cómo iterar? | QUERY_PARAM, link-rel, cursor, infinite-scroll | **Estrategia de paginación** |
| **antibot** | ¿Qué protecciones? | WAF, TLS fingerprint, behavioral, rate-limit scores | **Selección de tools** (curl_cffi, proxy, Playwright) |
| **e-commerce** (E1-E6) | ¿Señales specifícas? | Price mechanism, cart, variants, reviews API, inventory | **Estrategia de scrape** (decisiones por producto) |
| **recommender** | ¿Qué debería hacer? | Lib primary, fallback, complejidad (1-10), flags | **Estimación de tiempo de desarrollo** |

Ver [docs/BACKLOG.md](docs/BACKLOG.md) para detalles de señales e-commerce (fases E1-E7).

---

## Development Workflow

1. Activar venv
2. Correr el módulo afectado con `--module <name>` como smoke test
3. Correr scan completo en un site conocido para regression check
4. Correr `make test` para verificar que no hay regresiones
5. No hay typecheck/lint automatizado — revisar manualmente antes de commit

---

## Execution Protocol (inmutable)

```
1. Lee la sección completa antes de escribir código
2. Implementa exactamente lo descrito — ni más, ni menos
3. Ejecuta y muestra el output real del terminal
4. Espera confirmación antes de continuar
5. Si una dependencia falla, reporta el error exacto y propón alternativa
6. Si encuentras ambigüedad, pregunta antes de asumir
```

**Reglas de código:**
- Imports relativos dentro del paquete siempre
- Type hints en todas las funciones
- Docstring en todos los módulos y funciones públicas
- Sin estado global — configuración siempre como parámetro explícito

---

## Plan Mode / Parallel Work / SDD

- Usar plan mode para cualquier cambio que toque más de 1 módulo
- Para mejoras del backlog: `/sdd-new → /sdd-ff → /sdd-apply`
- Subagentes para exploración paralela de módulos independientes
- Solo un agente edita un archivo a la vez

---

## Cómo Leer el Reporte

El output tiene 8 secciones. **Léelas en orden**:

1. **Legal Scope** — Detente aquí si ToS prohíbe scraping
2. **Page Classification** — Te dice: SSR/CSR/Hybrid, frameworks JS, CMS, infraestructura
3. **Auth & Access** — Te dice: login requerido, OAuth, paywall, cookie consent
4. **API Endpoints** — URLs de APIs internas (úsalas en lugar de HTML cuando sea posible)
5. **Pagination** — Cómo el sitio itera resultados (query param, link-rel, cursor, infinite scroll)
6. **Anti-Bot Protection** — Score 0-10 (LOW/MEDIUM/HIGH/EXTREME); qué librerías podrían fallar
7. **Recommendations** — Librería PRIMARY, fallback, estimación de complejidad (1-10), flags clave
8. **Modules Status** — Cuáles módulos exitosos/fallidos y por qué

**⚠️ Nota**: Si el sitio es dinámico (CSR/Hybrid), el score antibot **está probablemente subestimado** sin `--deep`. Ver [docs/BACKLOG.md](docs/BACKLOG.md) — Phase 3 (E7).

---

## Things Claude Should NOT Do

- No superar el budget HTTP por módulo (ver tabla abajo)
- No modificar `models/schemas.py` sin revisar todos los módulos que lo usan
- No hacer commit sin correr un smoke test (`--module <name>`)
- No implementar mejoras del backlog sin que el usuario lo indique explícitamente

---

## Project-Specific Patterns

- Todos los módulos async reciben `(url: str, timeout: float)` como mínimo; `auth_detector` también acepta `html`, `headers`, y `redirect_chain`. `recommender` es síncrono.
- `run_module()` en `utils/graceful.py` es el wrapper estándar para todos los módulos
- Backlog activo en `docs/BACKLOG.md` — consultarlo antes de proponer mejoras

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

> Si `import X` falla en runtime, reporta y aplica el fallback — nunca silencies el error.
> Playwright requiere dos pasos: primero el paquete Python, luego el binario del browser.

---

## HTTP Request Budget

**Máximo 27 requests por scan completo.**

| Módulo        | Max requests | Notas                                          |
|---------------|-------------|------------------------------------------------|
| legal         | 6           | 2 UAs robots.txt + hasta 5 sitemap probes + 1 ToS |
| classifier    | 3           | 1 fetch + 1 DNS + 1 mobile UA compare          |
| auth_detector | 2           | reutiliza fetch de classifier + 1 probe        |
| api_detector  | 3           | reutiliza fetch + hasta 2 GraphQL probes       |
| pagination    | 1           | reutilizar fetch de classifier                 |
| antibot       | 12          | 8 rate-limit + 3 TLS + 1 base                  |
| recommender   | 0           | función pura                                   |
| **Total**     | **≤ 27**    |                                                |

---

## Project Structure

```
scraping_recon/
├── main.py                  ← CLI entry point (Typer)
├── config.py                ← Settings, defaults, constants
├── models/
│   └── schemas.py           ← Pydantic models — fuente de verdad de todos los outputs
├── modules/
│   ├── legal.py · classifier.py · auth_detector.py
│   ├── antibot.py · api_detector.py · pagination.py · recommender.py
├── report/
│   ├── terminal.py · json_export.py
├── utils/
│   ├── http.py              ← HTTP client factory (httpx + curl_cffi)
│   ├── tls_test.py          ← TLS fingerprint comparison
│   └── graceful.py          ← Module runner con timeout + exception capture
└── docs/
    ├── BACKLOG.md           ← Mejoras pendientes — leer antes de proponer cambios
    ├── build/               ← Specs originales de cada STEP (referencia)
    └── modules/             ← Lógica extendida (recommender, etc.)
```
