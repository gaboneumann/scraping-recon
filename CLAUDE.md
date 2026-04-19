# CLAUDE.md

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
├── utils/
│   ├── __init__.py
│   ├── http.py              ← HTTP client factory (httpx + curl_cffi)
│   ├── tls_test.py          ← TLS fingerprint comparison
│   └── graceful.py          ← Module runner con timeout + exception capture
└── docs/
    ├── build/               ← Specs de cada STEP (leer antes de implementar)
    └── modules/             ← Lógica extendida (recommender, etc.)
```

---

## HTTP Request Budget

**Máximo 25 requests por scan completo.**

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

## Build Steps

Lee el archivo de spec completo antes de implementar cada STEP.

| STEP | Archivo de spec | Qué implementa |
|------|----------------|----------------|
| 0 | [docs/build/STEP_0_schemas.md](docs/build/STEP_0_schemas.md) | `models/schemas.py` — Pydantic contracts |
| 1 | [docs/build/STEP_1_utils.md](docs/build/STEP_1_utils.md) | `utils/graceful.py` + `utils/http.py` |
| 2 | [docs/build/STEP_2_legal.md](docs/build/STEP_2_legal.md) | `modules/legal.py` |
| 3 | [docs/build/STEP_3_classifier.md](docs/build/STEP_3_classifier.md) | `modules/classifier.py` |
| 4 | [docs/build/STEP_4_api_detector.md](docs/build/STEP_4_api_detector.md) | `modules/api_detector.py` |
| 5 | [docs/build/STEP_5_pagination.md](docs/build/STEP_5_pagination.md) | `modules/pagination.py` |
| 5b | [docs/build/STEP_5b_auth_detector.md](docs/build/STEP_5b_auth_detector.md) | `modules/auth_detector.py` |
| 6 | [docs/build/STEP_6_antibot.md](docs/build/STEP_6_antibot.md) | `modules/antibot.py` |
| 7 | [docs/build/STEP_7_recommender.md](docs/build/STEP_7_recommender.md) | `modules/recommender.py` — ver también [docs/modules/recommender_logic.md](docs/modules/recommender_logic.md) |
| 8 | [docs/build/STEP_8_main.md](docs/build/STEP_8_main.md) | `main.py` + `report/` |
| 9 | [docs/build/STEP_9_requirements.md](docs/build/STEP_9_requirements.md) | `requirements.txt` |
