# Scraping Recon

> Pre-scraping intelligence for e-commerce and retail sites — scans a URL across 7 dimensions and tells you *what scraper to build before you build it*, without ever scraping the data itself.

![Python](https://img.shields.io/badge/Python-3.12+-3776AB?logo=python&logoColor=white)
![Typer](https://img.shields.io/badge/Typer-CLI-white?logo=typer&logoColor=3776AB)
![httpx + curl_cffi](https://img.shields.io/badge/httpx%20%2B%20curl_cffi-HTTP%2F2%20%2B%20TLS-black)
![Playwright](https://img.shields.io/badge/Playwright---deep%20mode-45ba4b?logo=playwright&logoColor=white)
![Tests](https://img.shields.io/badge/Tests-370%2B%20pytest-brightgreen?logo=pytest&logoColor=white)

---

## The Problem

You find a new e-commerce target. Before sinking hours into a scraper, you need answers that decide the whole approach:

- **Is it legal?** — robots.txt rules + ToS keyword risk
- **What's the render mode?** — STATIC (SSR), DYNAMIC (CSR), HYBRID, or API_DRIVEN → which HTTP library even works
- **Are there internal APIs?** — REST/GraphQL endpoints you can hit instead of parsing HTML
- **Is auth required?** — login form, OAuth, paywall, cookie-consent walls → session complexity
- **How do I paginate?** — query param, path, cursor, link-rel, load-more, infinite scroll
- **What antibot defenses exist?** — WAF, TLS fingerprinting, rate-limits, behavioral, CAPTCHA
- **What e-commerce signals matter?** — price mechanism, cart architecture, variants, reviews, inventory

Building a scraper blind means discovering each of these the hard way, mid-development. Generic site profilers don't speak the language of scraping decisions (library choice, proxy tier, effort estimate).

**Solution:** one command scans the URL across 7 dimensions in **≤ 27 HTTP requests**, then a pure-function recommender turns the findings into a concrete build plan — primary library, fallback, complexity score, and flags. It flags protections; it does **not** scrape data or run evasion.

---

## Results

| Metric | Value |
| :------ | ----: |
| Recon dimensions | **7** (6 async modules + 1 sync recommender) |
| HTTP requests per full scan | **≤ 27** |
| E-commerce signals | **E1–E6** static + **E7** runtime (`--deep`) |
| Output formats | Terminal (Rich) + JSON |
| Antibot scoring | 9 weighted dimensions → 0–10 score |
| Tests | **370+** (unit · integration · smoke snapshots) |

---

## Capability

**One pipeline, every render mode.** The same scan handles STATIC (SSR), DYNAMIC (CSR), HYBRID, and API_DRIVEN e-commerce sites — the classifier detects the mode and the rest of the pipeline adapts. For JS-heavy sites, the optional `--deep` flag swaps in Playwright XHR interception to catch runtime-only signals (JS-injected prices, infinite scroll, cart endpoints) that static analysis can't see.

---

## Stack

- **Typer** — CLI with explicit option validation
- **httpx + curl_cffi** — HTTP/2 client with browser TLS impersonation (Chrome/Safari) for antibot probing
- **BeautifulSoup4 + lxml** — HTML parsing
- **Pydantic** — schema validation; `models/schemas.py` is the single source of truth for every output
- **Rich** — formatted terminal report
- **Playwright** — optional `--deep` mode for runtime XHR interception on CSR/Hybrid sites
- **dnspython / wafw00f** — DNS signals and WAF fingerprinting
- **pytest** (+ pytest-asyncio, respx, pytest-cov) — async test suite with snapshot smoke tests

---

## Project Architecture

```
scraping_recon/
├── main.py                  # CLI entry point (Typer) — two-phase async orchestration
├── config.py                # Config dataclass (passed explicitly, no global state)
├── models/
│   └── schemas.py           # Pydantic models — single source of truth for all outputs
├── modules/
│   ├── legal.py             # robots.txt, sitemap, ToS keyword risk
│   ├── classifier.py        # render mode, frameworks, CMS, e-commerce signals (E1–E7)
│   ├── api_detector.py      # REST/GraphQL endpoints + state blobs
│   ├── auth_detector.py     # login form, OAuth, paywall, cookie consent
│   ├── pagination.py        # iteration strategy
│   ├── antibot.py           # WAF / TLS / rate-limit / behavioral scoring
│   └── recommender.py       # pure function → library choice, complexity, flags
├── report/
│   ├── terminal.py          # Rich-formatted output
│   └── json_export.py       # JSON serialization
├── utils/
│   ├── http.py              # httpx + curl_cffi client factory
│   ├── tls_test.py          # TLS fingerprint comparison
│   └── graceful.py          # run_module() — timeout + exception capture wrapper
├── tests/                   # unit · integration · smoke · real (+ fixtures)
└── docs/
    ├── BACKLOG.md           # roadmap, e-commerce signal definitions (E1–E7)
    └── modules/             # extended module logic (recommender)
```

---

## Quick Start

```bash
git clone https://github.com/gaboneumann/scraping-recon.git
cd scraping-recon

# Setup
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt          # for tests (optional)
playwright install chromium                   # only needed for --deep mode

# Verify
python main.py --help
python main.py --url https://example.com --module legal   # single-module smoke test

# Run a full scan
python main.py --url https://example-ecommerce.com

# JSON export for downstream tooling
python main.py --url https://example-ecommerce.com --json -o report.json
```

**Output:** a Rich-formatted terminal report with 8 sections (Legal → Classification → Auth → API → Pagination → Antibot → Recommendations → Module Status), or a JSON document with the same data when `--json` / `-o` is used.

**Fields / shape (JSON top level):** `url`, `timestamp`, `scan_duration_ms`, `modules_status[]`, `legal`, `classifier` (with nested `ecommerce`), `auth`, `api_detector`, `pagination`, `antibot`, `recommender`. Any module can be `null` if skipped or failed — check `modules_status[]`.

---

## Configuration

There is **no config file** — configuration is passed per-scan via CLI flags (mapped onto the `Config` dataclass). JSON is an *output* format, not an input.

### Defaults (`config.py`)
```python
@dataclass
class Config:
    timeout: float = 15.0      # per-request timeout (seconds)
    ua: str | None = None      # override User-Agent (None = built-in Chrome UA)
    verbose: bool = False
    no_color: bool = False
    skip_modules: list[str] = []
    deep: bool = False         # enable Playwright XHR interception
    output: str | None = None  # JSON output file path
```

### CLI flags
```
Usage: main.py [OPTIONS]

  --url,    -u  TEXT     Target URL to scan (required)
  --module, -m  TEXT     Run a single module: legal | classifier | api_detector
                         | auth_detector | pagination | antibot | recommender
  --skip        TEXT     Comma-separated modules to skip (e.g. antibot,api_detector)
  --deep                 Enable Playwright XHR interception (CSR/Hybrid e-commerce)
  --json                 Print JSON instead of the terminal report
  --output, -o  TEXT     Write JSON to a file (e.g. -o report.json)
  --timeout     FLOAT    Per-request timeout in seconds (default: 15)
  --ua          TEXT     Override the User-Agent string
  --verbose, -v          Show raw HTTP details
  --no-color             Disable Rich colors
  --help                 Show all options
```

```bash
# skip the expensive antibot probe (saves up to 12 requests)
python main.py --url <url> --skip antibot,api_detector

# deep scan a CSR/Hybrid e-commerce site
python main.py --url <url> --deep --json -o deep_report.json
```

---

## Core Mechanism

The scan is a **two-phase async orchestration**: independent modules run concurrently, then a decision gate and the antibot probe run with the context they produced, and finally a pure-function recommender turns everything into a build plan.

```
                         URL
                          │
        ┌─────────────────┴─────────────────┐
        │  PHASE 1 — concurrent (asyncio)    │
        │  legal · classifier · auth         │
        │  api_detector · pagination         │
        └─────────────────┬─────────────────┘
                          │  classifier result + API endpoints
            ┌─────────────┴─────────────┐
            │  DECISION GATE             │
            │  if --deep AND CSR/Hybrid  │
            │  AND e-commerce → E7       │  ← Playwright XHR interception
            └─────────────┬─────────────┘
                          │
        ┌─────────────────┴─────────────────┐
        │  PHASE 2 — antibot                 │  ← probes with API-endpoint context
        └─────────────────┬─────────────────┘
                          │
                  recommender (pure fn)
                          │
              ReconReport → terminal | JSON
```

### Key Components
- **`utils/graceful.run_module()`** — every module runs through this wrapper, which enforces a timeout and captures exceptions so one failing module never aborts the scan (it lands as `INCOMPLETE`/`BLOCKED` in `modules_status`).
- **`models/schemas.py`** — Pydantic contracts shared by every module and both report renderers; nothing defines schemas inline.
- **`modules/recommender.py`** — a pure, request-free function: it reads the assembled report and emits library choice, complexity, and flags. Deterministic and unit-testable.
- **`utils/http.py`** — client factory that switches between httpx and curl_cffi (TLS impersonation) for the antibot fingerprint comparison.

---

## Key Strategies / Modules

The 6 async modules + recommender map one-to-one onto a scraping decision. E-commerce signals (E1–E7) live **inside** the classifier module, not as a standalone CLI module.

| # | Module | Question it answers | Decision it drives |
|---|--------|---------------------|--------------------|
| 1 | **legal** | Is scraping permitted? | robots.txt path rules + ToS risk → **stop or continue** |
| 2 | **classifier** | What render mode / platform? | STATIC/DYNAMIC/HYBRID/API_DRIVEN → **httpx vs Playwright** |
| 3 | **api_detector** | Are there internal APIs? | REST/GraphQL endpoints → **hit the API instead of HTML** |
| 4 | **auth_detector** | Is auth required? | form/OAuth/paywall/consent → **session complexity** |
| 5 | **pagination** | How do results iterate? | query/path/cursor/link-rel/scroll → **pagination strategy** |
| 6 | **antibot** | What protections exist? | 9 dimensions → 0–10 score → **tool & proxy tier** |
| — | *e-commerce (E1–E7)* | *Product-level signals?* | *price / cart / variants / reviews / inventory* — *runs within classifier* |
| 7 | **recommender** | What should I build? | library, fallback, complexity, flags → **effort estimate** |

---

## Testing

```bash
make test              # unit + integration + coverage (term-missing)
make test-unit         # unit tests only
make test-integration  # integration tests only
make test-smoke        # full-pipeline snapshot smoke tests
make update-snapshots  # regenerate smoke snapshots after intentional output changes
```

**Coverage:** module logic (scoring, classification, schema mapping, recommender rules) is covered by deterministic unit and integration tests using fixtures and `respx`-mocked HTTP. Smoke tests assert the full pipeline against JSON snapshots. Tests requiring a live network are marked `real` and excluded from the default run.

---

## Design Principles

- **It's a profiler, not a scraper.** It reports protections and signals so you can plan your own scraper — it never extracts product data or runs evasion.
- **No global state.** `Config` is constructed once and passed explicitly to every module; nothing reads ambient settings.
- **Single source of truth.** All outputs are Pydantic models in `schemas.py`; modules and renderers import from there.
- **Graceful degradation.** A module failing or timing out yields a partial report, not a crash — `modules_status[]` records what happened.
- **Bounded cost.** The full scan is capped at ≤ 27 HTTP requests, budgeted per module, so reconnaissance stays cheap and polite.

---

## Documentation

- **[CLAUDE.md](CLAUDE.md)** — project spec: commands, module→decision map, HTTP budget table, dependency matrix, patterns
- **[docs/BACKLOG.md](docs/BACKLOG.md)** — roadmap and e-commerce signal definitions (phases E1–E7)
- **[docs/modules/recommender_logic.md](docs/modules/recommender_logic.md)** — how the recommender maps findings to library/complexity

---

## Usage Examples

### Recommended workflow

```bash
# 1. Legal first — stop if the target path is disallowed or ToS risk is HIGH
python main.py --url <url> --module legal

# 2. Classify — STATIC (httpx) vs DYNAMIC (Playwright) vs HYBRID vs API_DRIVEN
python main.py --url <url> --module classifier      # also reports e-commerce signals

# 3. APIs — if internal endpoints exist, skip HTML parsing
python main.py --url <url> --module api_detector

# 4. Auth + pagination — session needs & iteration strategy
python main.py --url <url> --module auth_detector
python main.py --url <url> --module pagination

# 5. Antibot — drives library and proxy tier
python main.py --url <url> --module antibot

# 6. Full scan + JSON for downstream tooling
python main.py --url <url> --json -o report.json
```

### Reading the JSON (real field paths)

```bash
jq '.recommender.primary_library'          report.json   # "httpx direct to API"
jq '.recommender.estimated_complexity'     report.json   # 5
jq '.antibot.overall_score'                report.json   # 2.22
jq '.classifier.type'                      report.json   # "API_DRIVEN"
jq '.classifier.ecommerce.price_mechanism' report.json   # "SERVER_SIDE" | "CLIENT_SIDE" | "UNKNOWN"
```

### Interpreting the report

**Legal** — there is no single ALLOWED/PROHIBITED verdict; read these together:
```
legal.robots_txt.target_path_allowed : true/false   → does robots.txt allow the target path
legal.tos.risk_level                 : LOW/MEDIUM/HIGH/UNKNOWN
legal.tos.flagged_keywords           : [...]         → anti-scraping terms found in the ToS
```

**Page classification** (`classifier.type`):
```
STATIC      (≈ SSR)   → httpx + BeautifulSoup4
DYNAMIC     (≈ CSR)   → Playwright (or --deep to confirm)
HYBRID                → httpx first, Playwright fallback
API_DRIVEN            → hit the JSON API directly (see api_detector)
```

**E-commerce signals** (`classifier.ecommerce`):
```
price_mechanism: SERVER_SIDE   → prices rendered in HTML, scrape directly
price_mechanism: CLIENT_SIDE   → prices injected by JS, use --deep / Playwright
cart_architecture: AJAX_API    → cart hits a JSON endpoint (vs AJAX_FRAGMENTS / SECTION_CACHE)
```

**Anti-bot score** (`antibot.overall_score`, 0–10 from 9 weighted dimensions):
```
0       NONE      → no detectable protection
0–3     LOW       → httpx + basic headers likely works
3–5     MEDIUM    → curl_cffi + rotating UA / datacenter proxy
5–8     HIGH      → Playwright + residential proxy
8–10    EXTREME   → DataDome/PerimeterX/Akamai-class → managed scraping API
```

**Recommendation** (`recommender`):
```
primary_library      → what to build first   (e.g. "httpx + BeautifulSoup4")
secondary_library    → fallback if primary fails
estimated_complexity → 1 (trivial) … 10 (months)
estimated_dev_time   → rough estimate (e.g. "2-4 days")
additional_flags     → e.g. "curl_cffi Chrome/Safari impersonation required"
```

> ⚠️ For DYNAMIC/HYBRID sites, the antibot score is **likely underestimated** without `--deep` — runtime protections (fingerprinting, CAPTCHA, behavioral) aren't visible to static analysis. The recommender flags this when it applies.

### Troubleshooting

| Issue | Cause | Fix |
|-------|-------|-----|
| `Connection timeout` | Target unreachable or blocking | Verify URL, increase `--timeout`, try a proxy/VPN |
| `Playwright unavailable` (with `--deep`) | Browser not installed | `playwright install chromium` |
| A module shows `INCOMPLETE`/`BLOCKED` | Network issue or malformed HTML | Re-run with `--verbose`; other modules still report |
| JSON missing a top-level field | Module skipped or failed | Check `modules_status[]` |
| `price_mechanism: UNKNOWN` on a JS site | Static HTML insufficient | Re-run with `--deep` to capture runtime price loading |

---

## Ethical Use / Disclaimers

Scraping Recon is a reconnaissance and planning tool: it analyzes publicly reachable pages, reports protections, and recommends an approach. It does **not** scrape product data, bypass authentication, or execute anti-detection evasion. The antibot module sends a small, bounded number of probe requests (within the ≤ 27 budget) — run it only against sites you are authorized to assess. Always verify compliance with local law and the target's Terms of Service before building any scraper.

---

## Author

**Gabriel Neumann**
[![LinkedIn](https://img.shields.io/badge/LinkedIn-Connect-0A66C2?logo=linkedin&logoColor=white)](https://www.linkedin.com/in/gaboneumann/)
[![GitHub](https://img.shields.io/badge/GitHub-Follow-181717?logo=github&logoColor=white)](https://github.com/gaboneumann)

---

## License

Distributed under the MIT license. See [`LICENSE`](LICENSE) for details.
