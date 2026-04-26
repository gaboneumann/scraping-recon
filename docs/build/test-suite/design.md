# Technical Design — `test-suite`

## File layout

```
scraping_recon/
├── pyproject.toml                       ← NEW (pytest config + dev deps)
└── tests/
    ├── __init__.py
    ├── conftest.py                      ← shared fixtures, respx setup
    ├── unit/
    │   ├── test_schemas.py              ← Pydantic round-trip
    │   ├── test_recommender.py          ← pure logic, ReconReport factory
    │   ├── test_http_helpers.py         ← detect_block, UA constants
    │   └── test_classifier_pure.py      ← _parse_*, signal extractors
    ├── integration/
    │   ├── test_legal_respx.py
    │   ├── test_classifier_respx.py
    │   ├── test_api_detector_respx.py   ← needs nested respx for inline AsyncClient
    │   ├── test_pagination_respx.py
    │   ├── test_auth_detector_respx.py
    │   └── test_antibot_mocked.py       ← subprocess + run_tls_test patched
    ├── smoke/
    │   ├── test_recommender_snapshots.py
    │   └── snapshots/                   ← *.json baselines
    └── fixtures/
        └── html/                        ← 12 *.html files
```

## ADR-001 — Single respx fixture, function-scoped, with pass-through for unmocked hosts

**Context**: `make_request` opens a fresh `httpx.AsyncClient` per call; `api_detector` opens its own inline client. Both are intercepted by respx at the transport layer, so one `respx.mock` covers both.

**Decision**: `respx_mock` fixture is function-scoped (`assert_all_called=False`) and yields the router. Tests register routes per-case. No module scope — recommender snapshots and rate-limit tests need clean state per assertion.

**Consequence**: Tests that exercise both `make_request` and the inline `AsyncClient` in `api_detector` work without nesting; respx patches `httpx.AsyncHTTPTransport` globally for the test.

## ADR-002 — Subprocess + `run_tls_test` patched with `monkeypatch`, not decorators

**Context**: `antibot.py` calls `subprocess.run(["wafw00f", ...])` and imports `from utils.tls_test import run_tls_test`. Decorator stacking on async tests collides with `pytest-asyncio` ordering.

**Decision**: A `mock_antibot_externals` fixture uses `monkeypatch.setattr` to replace `modules.antibot.subprocess.run` and `modules.antibot.run_tls_test` with `AsyncMock`/`MagicMock`. `asyncio.sleep` is also patched here (`monkeypatch.setattr("modules.antibot.asyncio.sleep", AsyncMock())`) to collapse the 8 x 0.3 s rate-limit loop to ~0 ms.

**Consequence**: One opt-in fixture per antibot test; no decorator soup; deterministic rate-limit tests under 50 ms.

## ADR-003 — Hand-crafted minimal HTML fixtures, snapshot via JSON diff (no plugin)

**Context**: Real scraped HTML drifts and bloats the repo. pytest-snapshot adds a dep and inverts control flow.

**Decision**: 12 hand-crafted fixtures (≤2 KB each) covering the exact signals each parser checks. Recommender snapshots are `RecommenderResult.model_dump()` written to `snapshots/<case>.json`; comparison is `assert result.model_dump() == json.loads(path.read_text())`. Update via `UPDATE_SNAPSHOTS=1 pytest`.

### Fixture files (12)

| File | Used by | Signal exercised |
|------|---------|------------------|
| `static_blog.html` | classifier | no JS frameworks, JSON-LD Article |
| `react_spa.html` | classifier | `__NEXT_DATA__`, low content_ratio |
| `shopify_pdp.html` | classifier, api_detector | `Shopify.theme`, product schema |
| `woocommerce_category.html` | classifier | `wc-` classes, faceted nav |
| `graphql_app.html` | api_detector | `/graphql` endpoint in script |
| `paginated_query.html` | pagination | `?page=2` link |
| `paginated_path.html` | pagination | `/page/2/` link |
| `load_more.html` | pagination | button `data-load-more` |
| `login_form.html` | auth_detector | `<form action="/login">` |
| `paywall_metered.html` | auth_detector | NYT-style meter |
| `cf_blocked.html` | antibot | "Cloudflare" + Ray ID |
| `clean_response.html` | smoke | baseline for recommender |

## conftest.py — concrete code

```python
import json, pathlib, pytest, respx
from unittest.mock import AsyncMock, MagicMock
from bs4 import BeautifulSoup
from models.schemas import ReconReport, ModuleStatus

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "html"

@pytest.fixture
def html_fixture():
    def _load(name: str) -> str:
        return (FIXTURES / f"{name}.html").read_text(encoding="utf-8")
    return _load

@pytest.fixture
def soup_fixture(html_fixture):
    return lambda name: BeautifulSoup(html_fixture(name), "lxml")

@pytest.fixture
def respx_mock():
    with respx.mock(assert_all_called=False, assert_all_mocked=True) as router:
        yield router

@pytest.fixture
def make_report():
    def _factory(**overrides) -> ReconReport:
        base = dict(
            url="https://example.com", timestamp="2026-01-01T00:00:00Z",
            scan_duration_ms=0, modules_status=[],
            legal=None, classifier=None, auth=None, api_detector=None,
            pagination=None, antibot=None, recommender=None,
        )
        base.update(overrides)
        return ReconReport(**base)
    return _factory

@pytest.fixture
def mock_antibot_externals(monkeypatch):
    monkeypatch.setattr("modules.antibot.subprocess.run",
        MagicMock(return_value=MagicMock(returncode=0, stdout="{}")))
    monkeypatch.setattr("modules.antibot.run_tls_test",
        AsyncMock(return_value={"python_httpx": "OK", "curl_chrome": "OK"}))
    monkeypatch.setattr("modules.antibot.asyncio.sleep", AsyncMock())
```

## pyproject.toml additions

```toml
[project.optional-dependencies]
dev = ["pytest>=8", "pytest-asyncio>=0.24", "respx>=0.21", "pytest-cov>=5"]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
addopts = "-ra --strict-markers --cov=modules --cov=utils --cov-report=term-missing"
markers = ["smoke: snapshot-based smoke tests"]
```

## respx pattern (matches both `make_request` and inline client)

```python
async def test_classify_static(respx_mock, html_fixture):
    respx_mock.get("https://example.com").mock(
        return_value=httpx.Response(200, html=html_fixture("static_blog"),
                                    headers={"server": "nginx"}))
    respx_mock.get("https://example.com/").mock(pass_through=False,
        return_value=httpx.Response(200, html=html_fixture("static_blog")))
    result = await classify_page("https://example.com")
    assert result.type == "STATIC"
```

## Sequence — `classify_page` integration test

```
test → respx_mock.get(url).mock(200, html)
test → await classify_page(url)
classify_page → make_request(url) → httpx.AsyncClient.GET
                                  → respx transport intercepts → returns mock
classify_page → compare_mobile_desktop(url) → 2× make_request → respx (2 routes)
classify_page → returns ClassifierResult
test → assert result.type == "STATIC"
```

## Truly-optional `ReconReport` fields

`legal`, `classifier`, `auth`, `api_detector`, `pagination`, `antibot`, `recommender` all default `None`. Required: `url`, `timestamp`, `scan_duration_ms`, `modules_status` (factory passes `[]`). Recommender tests build only the sub-trees they need.
