# STEP 10 — Test Suite

> Spec for adding a pytest-based test suite to scraping_recon.
> No tests exist today. Three phases: infrastructure, HTTP-mocked integration, fixture smoke tests.
> RFC 2119 keywords apply throughout.

---

## REQ-1: Test Infrastructure

### Configuration

`pyproject.toml` MUST include:

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

`pytest-asyncio`, `respx`, and `pytest-cov` MUST be added to `requirements.txt` (or `requirements-dev.txt`).

### conftest.py fixtures

`tests/conftest.py` MUST provide:

- **`html_fixture(name: str) -> str`** — reads `tests/fixtures/html/<name>.html` and returns content as `str`.
- **`make_report(**kwargs) -> ReconReport`** — factory that builds a `ReconReport` with all module fields defaulting to `None`; caller passes only the fields under test.
- **`soup_from(html: str) -> BeautifulSoup`** — wraps `BeautifulSoup(html, "lxml")`.

### Performance

The full test suite MUST complete in under 10 seconds on a cold run (no network, patched I/O). Async sleep calls inside modules MUST be patched at the test boundary.

---

## REQ-2: Recommender Unit Tests (≥ 95% branch coverage)

File: `tests/unit/test_recommender.py`

**S-R-01 — No antibot data**
- Given: `ReconReport` with `antibot=None`, all other fields `None`
- When: `build_recommendation(report)` called
- Then: `primary_library == "httpx"`, `secondary_library is None`, `estimated_complexity == 3`

**S-R-02 — Extreme protection**
- Given: `antibot.overall_score = 8.0`
- When: called
- Then: `primary_library == "playwright + playwright-stealth"`, `managed_api_suggested is True`, `managed_api_options` contains `"ZenRows"`

**S-R-03 — Classifier None, antibot score < 8 (silent fallthrough)**
- Given: `antibot.overall_score = 4.0`, `classifier=None`
- When: called
- Then: falls through to `else` branch → `primary_library == "httpx + BeautifulSoup4"`, `estimated_complexity == 3`

**S-R-04 — STATIC + score 0**
- Given: `classifier.type = "STATIC"`, `antibot.overall_score = 0`
- When: called
- Then: `primary_library == "httpx + BeautifulSoup4"`, `secondary_library == "Scrapy"`, `estimated_complexity == 2`

**S-R-05 — DYNAMIC + internal API + TLS score ≥ 2**
- Given: `classifier.type = "DYNAMIC"`, `api.internal_api_found = True`, `antibot.dimensions.tls_fingerprint.score = 2`
- When: called
- Then: `primary_library == "httpx direct to API"`, `secondary_library == "curl_cffi"`

**S-R-06 — HYBRID**
- Given: `classifier.type = "HYBRID"`, `antibot.overall_score = 3.0`
- When: called
- Then: `primary_library == "httpx SSR + Playwright opcional"`, `secondary_library == "Scrapy + Playwright plugin"`, `estimated_complexity == 6`

**S-R-07 — Flag truncation in summary**
- Given: report that produces ≥ 5 flags (e.g. rate_limiting.score=3, tls_fingerprint.score=2, captcha.score=2, honeypots.count=2, ip_reputation.geo_block=True)
- When: called
- Then: `full_stack_recommendation` contains exactly 3 flags (semicolon-delimited); `additional_flags` contains all flags (≥ 5)

---

## REQ-3: Classifier Pure Function Tests

File: `tests/unit/test_classifier.py`

**S-C-01 — `_classify()` threshold boundaries**

| content_ratio | js_frameworks | cms   | Expected type | Expected confidence |
|--------------|---------------|-------|--------------|---------------------|
| 0.049        | []            | None  | `API_DRIVEN` | `HIGH`              |
| 0.051        | []            | None  | `UNKNOWN`    | `LOW`               |
| 0.099        | []            | None  | `UNKNOWN`    | `LOW`               |
| 0.101        | []            | None  | `STATIC`     | `MEDIUM`            |
| 0.149        | []            | None  | `STATIC`     | `MEDIUM`            |
| 0.151        | []            | None  | `STATIC`     | `HIGH`              |

Each row MUST be a parametrized test case.

**S-C-02 — `_detect_ecommerce_signals()` price mechanism**
- Given: HTML with `data-price=""` (empty attribute)
- Then: `price_mechanism == "CLIENT_SIDE"`
- Given: HTML with `data-price="0"` (zero value, no empty-string pattern match)
- Then: `price_mechanism == "SERVER_SIDE"` (falls through to non-zero price signal)

**S-C-03 — `_detect_structured_data()` malformed JSON-LD**
- Given: HTML containing `<script type="application/ld+json">{ broken json </script>`
- When: `_detect_structured_data(soup, html)` called
- Then: no exception raised; `schema_types == []`; `json_ld_found is True`

**S-C-04 — `_detect_cms()` header case-insensitivity**
- Given: headers `{"X-Drupal-Cache": "HIT"}` (mixed case)
- When: `_detect_cms("", headers)` called
- Then: returns `"Drupal"`

---

## REQ-4: Antibot + Auth Pure Function Tests

File: `tests/unit/test_antibot.py` and `tests/unit/test_auth.py`

**S-A-01 — WAF: cf-ray header → Cloudflare**
- Given: `headers = {"cf-ray": "abc123"}`, no wafw00f (subprocess patched to raise)
- When: `_detect_waf(url, headers, "")`
- Then: `score == 3`, `vendor == "Cloudflare"`, `confidence == "MEDIUM"`

**S-A-02 — Captcha: Turnstile → score 3; reCAPTCHA v2 → score 2**
- Given: HTML containing `"challenges.cloudflare.com/turnstile"`
- Then: `score == 3`, `provider == "Turnstile"`
- Given: HTML containing `data-sitekey`
- Then: `score == 2`, `provider == "reCAPTCHA"`

**S-A-03 — Fingerprinting: multiple libraries → max score**
- Given: HTML containing both `"fpjs.io"` (score 2) and `"navigator.webdriver"` (score 3)
- When: `_detect_fingerprinting(html)`
- Then: `score == 3`, `len(libraries) == 2`

**S-A-04 — Honeypots: count boundaries**

| count | expected score |
|-------|---------------|
| 0     | 0             |
| 1     | 1             |
| 2     | 1             |
| 3     | 2             |
| 5     | 2             |
| 6     | 3             |

Each row MUST be a parametrized test case using a fabricated `BeautifulSoup` object.

**S-A-05 — Consent detection**
- Given: HTML with `onetrust-banner-sdk` and `<body style="overflow: hidden">`
- Then: `_detect_consent(soup, html) is True`
- Given: HTML with `onetrust-banner-sdk`, fixed element `style="position:fixed; z-index: 1000"`
- Then: `True` (z-index > 999)
- Given: HTML with `onetrust-banner-sdk`, fixed element `style="position:fixed; z-index: 100"`
- Then: `True` (OneTrust present → assume blocking as final fallback)
- Given: HTML with no consent signals
- Then: `False`

---

## REQ-5: HTTP-Mocked Integration Tests

File: `tests/integration/test_modules_mocked.py`

- Every public module entry point (`classify_page`, `analyze_antibot`, `detect_auth`, `analyze_legal`, `detect_api`, `analyze_pagination`) MUST have at least 1 `respx`-mocked test.
- `analyze_antibot` rate-limit test MUST patch `asyncio.sleep` (via `unittest.mock.patch`) to avoid the 2.4-second real delay from 8×0.3s intervals.
- `detect_auth` SHOULD be tested by passing `html=` and `headers=` directly (no respx mock required for that path).
- Each test MUST assert that the return value validates as its declared Pydantic model (instantiation without `ValidationError`).
- `run_tls_test` MUST be patched to return a `TlsDimension(score=0, sensitivity="NONE", client_results={})` stub.
- `subprocess.run` (wafw00f) MUST be patched to raise `FileNotFoundError` to force the header-fallback path.

---

## REQ-6: Fixture Smoke Tests

File: `tests/smoke/test_pipeline_fixtures.py`

### Fixture archetypes

`tests/fixtures/html/` MUST contain 12 `.html` files named by archetype:

```
static_blog.html          shopify_pdp.html
woocommerce_category.html  nextjs_spa.html
cloudflare_gated.html      magento_category.html
vtex_pdp.html              nuxt_hybrid.html
react_api_driven.html      drupal_static.html
paywall_hard.html          consent_onetrust.html
```

Supporting fixtures MUST exist under `tests/fixtures/robots/` and `tests/fixtures/sitemaps/` for each archetype that exercises `legal.py`.

### Parametrized smoke test

Each archetype MUST have a parametrized test that:
1. Loads HTML via `html_fixture`
2. Builds a `ReconReport` from module outputs (all I/O patched)
3. Calls `build_recommendation(report)`
4. Asserts the result matches a known-good snapshot in `tests/fixtures/snapshots/<archetype>.json`

Snapshots MUST be stored as serialized `RecommenderResult.model_dump()` JSON. On first run (snapshot absent), the test MUST write the snapshot and pass. On subsequent runs, it MUST diff and fail on divergence.

---

## REQ-7: Coverage

- `modules/` and `models/`: line coverage MUST be ≥ 80%.
- `modules/recommender.py`: line coverage MUST be ≥ 95%.
- Excluded from coverage: `main.py`, `report/terminal.py`, `utils/tls_test.py`.
- Coverage MUST be reported via:
  ```
  pytest --cov=. --cov-omit="main.py,report/terminal.py,utils/tls_test.py,venv/*" --cov-report=term-missing
  ```
- CI (if added later) MUST fail the build if coverage drops below these thresholds.

---

## File Tree Delta

```
tests/
├── conftest.py
├── unit/
│   ├── test_recommender.py
│   ├── test_classifier.py
│   ├── test_antibot.py
│   └── test_auth.py
├── integration/
│   └── test_modules_mocked.py
├── smoke/
│   └── test_pipeline_fixtures.py
└── fixtures/
    ├── html/          ← 12 archetype .html files
    ├── robots/        ← robots.txt stubs per archetype
    ├── sitemaps/      ← sitemap.xml stubs per archetype
    └── snapshots/     ← RecommenderResult JSON snapshots
```

`pyproject.toml` MUST be created (or updated if it exists) with the `[tool.pytest.ini_options]` block above.

---

## Out of Scope

- `main.py` Typer wiring
- `report/terminal.py` Rich rendering
- `utils/tls_test.py` (system-level TLS tool)
- Live network calls
- CI pipeline configuration
