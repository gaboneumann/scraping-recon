# Design: Phase 4 — Test Coverage T2 Smoke Suite

**Change**: Phase 4 — Test Coverage T2 Smoke Suite  
**Status**: Design phase  
**Date**: 2026-05-14  

---

## Technical Approach

Phase 4 addresses **testing gaps discovered in Phase 3 deployment**. The phase establishes continuous platform-specific signal validation to prevent regressions and closes coverage gaps:

1. **Fix snapshot test failures** (4 tests failing): Add missing `BehavioralDetectionDimension` and `JourneyDimension` to `AntibotDimensions` fixture definitions in `_make_antibot()` factory
2. **Establish T2 false negative log system**: CSV-based log (platform, url, signal, expected, actual, date, status) with auto-fixture generator
3. **Expand real-world platform coverage**: Add 4 new platform fixtures (WooCommerce, Shopify, custom, regional) to existing `tests/real/` tree
4. **Improve E7 coverage** (currently 12%): Add 8-10 integration tests for `playwright_helper` functions (timeout handling, XHR capture, cart detection, error recovery)
5. **Improve api_detector coverage** (currently 77%): Add 5 edge case tests for search API edge cases (Elasticsearch variants, custom API patterns, auth requirements)

**Why this approach?**

- **Snapshot fix**: Unblocks smoke suite validation immediately; prevents false CI failures
- **T2 log system**: Prevents recurring signal regressions; avoids manual test duplication; scales platform support
- **Auto-fixture generator**: Converts observed failures (CSV rows) directly into pytest test cases; reduces time-to-test
- **Platform expansion**: Covers 4 major e-commerce archetypes (WooCommerce, Shopify, custom/SPA, regional locale variants)
- **E7 integration tests**: Validates Playwright reliability in production; tests timeout handling, XHR pattern matching, cart button detection
- **api_detector edge cases**: Addresses real-world search API patterns (Elasticsearch variants, header-based auth, custom endpoints)

---

## Architecture Decisions

### Decision 1: T2 False Negative Log Format (CSV-based with auto-discovery)

**Choice**: CSV document with platform, url, signal, expected, actual, discovered_date, status columns.

**CSV Schema**:
```csv
platform,url,signal,expected,actual,discovered_date,status
WooCommerce,https://example-woo.com/shop,E6_inventory,"AJAX","SERVER_SIDE (bug)",2026-05-14,open
Shopify,https://shop.example.myshopify.com/products/widget,E3_variants,"dropdown + swatch","button only",2026-05-14,open
Custom SPA,https://custom-app.example.com/products,E2_search_api,"Algolia endpoint","not detected",2026-05-14,open
Regional,https://shop.example.br/produtos,E1_price,"JSON-LD in HTML","dynamic JS only",2026-05-14,open
```

**Column Meanings**:
- `platform` — e-commerce platform or site category (WooCommerce, Shopify, custom SPA, regional, etc.)
- `url` — live URL or representative domain where the issue was found
- `signal` — signal ID or name (e.g., E1_price, E3_variants, E6_inventory)
- `expected` — what signal detection should return (per specification)
- `actual` — what was actually detected (or "not detected")
- `discovered_date` — ISO 8601 date when bug/gap was identified (YYYY-MM-DD)
- `status` — "open" (unresolved) | "resolved" (test added or fix deployed)

**Location**: `docs/T2_false_negative_log.csv`

**Rationale**:
- CSV is human-readable and directly auditable (not opaque database)
- Platform-aware grouping helps identify patterns (e.g., "all Shopify stores miss swatch variants")
- Status field prevents test duplication (check before auto-generating)
- Simple to extend (add columns like "assigned_to", "fix_deployed_date" later)
- Can be imported into GitHub Issues, dashboards, or reporting tools

---

### Decision 2: Fixture Generator Script Design

**Choice**: Standalone Python script (`scripts/csv_to_fixture.py`) that converts CSV rows → pytest test case code.

**Usage**:
```bash
# Generate fixture file from T2 log filtered by platform
python scripts/csv_to_fixture.py docs/T2_false_negative_log.csv --platform woocommerce

# Output: tests/real/test_woocommerce_t2_fixtures.py (3-5 test cases)
# Each row becomes one test function
```

**Script Pseudocode**:
```python
def csv_to_pytest_case(csv_row: dict) -> str:
    """Convert T2 CSV row to pytest async test case code."""
    platform = csv_row['platform']
    url = csv_row['url']
    signal = csv_row['signal']
    expected = csv_row['expected']
    
    # Map signal ID (e.g., "E6_inventory") to check logic
    check_logic = map_signal_to_assertion(signal)
    
    return f'''
@pytest.mark.real
@pytest.mark.asyncio
async def test_t2_{platform.lower().replace(' ', '_')}_{signal.lower()}():
    """T2 false negative: {platform} {signal} detection (discovered {csv_row['discovered_date']})"""
    url = "{url}"
    result = await classify_page(url, timeout=15.0)
    
    # Auto-generated assertion
    {check_logic}
'''
```

**Behavior**:
- Reads CSV and iterates over `status == "open"` rows
- For each row, generates a valid pytest async test function
- Skips if test already exists (checks for same signal + platform in target file)
- Writes output to `tests/real/test_{platform_slug}_t2_fixtures.py`
- Can be run on-demand or in CI/CD pipeline

**Rationale**:
- Separates log management (CSV) from test code (pytest)
- Allows manual review of generated test before commit
- Prevents test duplication automatically
- Output is executable Python (no code generation tricks)
- Can be integrated into nightly CI/CD

---

### Decision 3: Snapshot Test Organization

**Choice**: Keep snapshot tests in `tests/smoke/`, add schema versioning, fix factory to include Phase 3 fields.

**Structure**:
```
tests/smoke/
├── test_pipeline_smoke.py          (4 archetypes: static, shopify, cloudflare, consent)
├── fixtures/
│   ├── html/                       (archetype HTML fixtures)
│   └── snapshots/
│       ├── v1/                     (legacy Phase 1-2 snapshots, archived)
│       └── v2/                     (current Phase 3 snapshots — all dimensions)
└── conftest.py                     (shared snapshot utilities)
```

**Snapshot Version v2 Schema** (Phase 3 complete):
- All AntibotDimensions fields present (9 dimensions: waf, tls, rate_limit, captcha, fingerprinting, honeypots, ip_rep, behavioral_detection, journey_probes)
- E7Result structure (if deep mode enabled)
- Full RecommenderResult

**Key Change**: Update `_make_antibot()` factory to populate:
```python
def _make_antibot(
    overall_score: float,
    waf_score: int = 0,
    waf_vendor: str | None = None,
    tls_score: int = 0,
    rate_score: int = 0,
    captcha_score: int = 0,
    fp_score: int = 0,
    honeypot_count: int = 0,
    geo_block: bool = False,
    behavioral_score: int = 0,              # NEW
    journey_blocked_type: str = "none",     # NEW
) -> AntibotResult:
    # ... existing logic ...
    return AntibotResult(
        overall_score=score,
        overall_level=level,
        dimensions=AntibotDimensions(
            # ... existing dimensions ...
            behavioral_detection=BehavioralDetectionDimension(
                score=behavioral_score,
                listener_count=3 if behavioral_score > 0 else 0,
                listener_types=["mousemove", "keydown", "wheel"] if behavioral_score > 0 else [],
                confidence="HIGH" if behavioral_score > 0 else "NONE",
            ),
            journey_probes=JourneyDimension(
                score=1 if journey_blocked_type != "none" else 0,
                blocked_at_url=None,
                blocked_type=journey_blocked_type,
                probes_sent=2 if journey_blocked_type != "none" else 0,
            ),
        ),
    )
```

**Rationale**:
- Snapshot versioning allows schema evolution without breaking old tests
- v2 is self-documenting (all Phase 1-3 fields present)
- Clear test names indicate what's being validated
- Can archive v1 for reference without confusion

---

### Decision 4: Platform Fixture Organization

**Choice**: Separate test files per platform, shared fixture data directory.

**Structure**:
```
tests/real/
├── fixtures/
│   ├── woocommerce_sample.html     (cached HTML or representative response)
│   ├── shopify_sample.html
│   ├── custom_spa_sample.html
│   ├── regional_br_sample.html
│   └── README.md                   (notes on fixture sources)
├── test_woocommerce.py             (3-5 tests per platform)
├── test_shopify.py
├── test_custom_spa.py
├── test_regional_br.py
├── test_woocommerce_t2_fixtures.py (auto-generated from T2 CSV)
├── test_shopify_t2_fixtures.py     (auto-generated)
├── conftest.py                     (shared fixtures + mark registration)
└── __init__.py
```

**Test Template** (per platform):
```python
# tests/real/test_woocommerce.py
import pytest
from modules.classifier import classify_page

@pytest.mark.real
@pytest.mark.woocommerce
@pytest.mark.asyncio
async def test_woocommerce_cart_mechanism_ajax():
    """E6: Validate cart AJAX detection on WooCommerce platform"""
    url = "https://example-woocommerce.com/shop/products"
    result = await classify_page(url, timeout=15.0)
    
    assert result.classifier is not None
    assert result.classifier.ecommerce is not None
    assert result.classifier.ecommerce.is_ecommerce is True
    assert result.classifier.ecommerce.inventory is not None
    assert result.classifier.ecommerce.inventory.mechanism == "AJAX"

@pytest.mark.real
@pytest.mark.woocommerce
@pytest.mark.asyncio
async def test_woocommerce_product_variants():
    """E3: Validate variant detection on WooCommerce"""
    url = "https://example-woocommerce.com/shop/products/variable-product"
    result = await classify_page(url, timeout=15.0)
    
    assert result.classifier.ecommerce.variants is not None
    assert result.classifier.ecommerce.variants.has_variants is True
```

**Rationale**:
- Grouped by platform → easy to debug platform-specific patterns
- Shared fixture data (HTML cache) speeds up tests
- Marks (`@pytest.mark.real`, `@pytest.mark.woocommerce`) allow filtering:
  - `pytest -m real` — run only real platform tests
  - `pytest -m "not real"` — skip real platform tests (CI pipeline)
  - `pytest -m woocommerce` — run only WooCommerce tests
- Auto-generated T2 tests live in separate files (`test_*_t2_fixtures.py`) to distinguish from baseline fixtures

---

### Decision 5: E7 Coverage Improvement Strategy

**Choice**: Mock-based integration tests for most helpers, optional real Playwright test for critical path.

**New Test File**: `tests/integration/test_e7_helpers.py`

**Test Categories** (8-10 tests total):

```python
# 1. XHR Pattern Setup (2 tests)
@pytest.mark.asyncio
async def test_setup_xhr_interception_price_pattern():
    """E7: Validate price XHR pattern setup and capture"""
    # Mock Playwright page + context
    # Verify price patterns registered (e.g., /api/prices, /cart/add)
    # Verify listener captures requests with correct headers/body

@pytest.mark.asyncio
async def test_setup_xhr_interception_pagination_pattern():
    """E7: Validate pagination XHR pattern setup"""
    # Verify infinite scroll patterns registered
    # Test offset/cursor pattern detection

# 2. Scroll Helper (2 tests)
@pytest.mark.asyncio
async def test_scroll_page_to_bottom_triggers_requests():
    """E7: Scroll should trigger pending XHR requests"""
    # Mock page with scroll listener
    # Verify scroll_page() captures XHR events

@pytest.mark.asyncio
async def test_scroll_page_timeout_returns_zero():
    """E7: Timeout on scroll returns zero products (no infinite scroll)"""
    # Mock timeout scenario
    # Verify graceful return

# 3. Cart Button Detection (2 tests)
@pytest.mark.asyncio
async def test_find_and_click_cart_button_hovers():
    """E7: Cart button detection tolerates hidden buttons (hover reveals)"""
    # Mock page with CSS-hidden cart button
    # Verify hover/visibility check works

@pytest.mark.asyncio
async def test_find_and_click_cart_timeout():
    """E7: Cart button search timeout returns None gracefully"""
    # Verify timeout handling

# 4. Browser Context Management (2 tests)
@pytest.mark.asyncio
async def test_playwright_context_cleanup_on_error():
    """E7: Context cleanup even if XHR capture fails"""
    # Mock browser context error
    # Verify cleanup happens

@pytest.mark.asyncio
async def test_playwright_browser_launch_failure_handled():
    """E7: Graceful return None if Playwright unavailable"""
    # Mock missing Playwright
    # Verify function returns None, not exception

# 5. Integration (1-2 tests, optional)
@pytest.mark.asyncio
@pytest.mark.skipif(not PLAYWRIGHT_AVAILABLE, reason="Playwright not installed")
async def test_detect_deep_ecommerce_real_shopify(real_url="https://shop.example.com"):
    """E7: End-to-end integration test (optional, skipped in CI)"""
    # Real browser, real site
    # Validates full XHR capture flow
```

**Mock Strategy**:
- Use `unittest.mock.AsyncMock` for Playwright page/context/browser
- Mock XHR listener events (inject captured requests)
- No real browser needed for most tests

**Rationale**:
- Mock-based tests are fast (no browser startup)
- Cover critical paths: timeout handling, error recovery, pattern matching
- Real site test validates actual Playwright interaction (optional for local development)
- Tests can run in CI/CD without Playwright binary

---

### Decision 6: api_detector Coverage Closure (77% → 80%+)

**Choice**: Add 5 edge case tests to existing `tests/unit/test_api_detector_*.py` files.

**New Tests** (added to existing test files):

```python
# tests/unit/test_api_detector_search_api.py (expand from 10 → 15 tests)

@pytest.mark.asyncio
async def test_elasticsearch_variant_urls_custom_path():
    """E2: Detect Elasticsearch API on custom path (e.g., /search/api)"""
    html = '<script src="/search/api/v1/search.js"></script>'
    result = await _detect_search_api(html)
    assert result.found is True
    assert result.api_type == "elasticsearch"

@pytest.mark.asyncio
async def test_custom_api_patterns_with_bearer_token():
    """E2: Detect custom API with Bearer token requirement"""
    html = 'fetch("/custom/search", {headers: {"Authorization": "Bearer token"}})'
    result = await _detect_search_api(html)
    assert result.found is True
    assert result.authenticated is True

@pytest.mark.asyncio
async def test_graphql_endpoint_with_bearer_token():
    """E2: Detect GraphQL endpoints with auth (e.g., Shopify Storefront API)"""
    html = 'fetch("https://example.myshopify.com/api/2024-01/graphql.json", {"headers": {"X-Shopify-Storefront-Access-Token": "abc"}})'
    result = await _detect_search_api(html)
    assert result.found is True
    assert result.authenticated is True

@pytest.mark.asyncio
async def test_search_api_not_found_returns_none():
    """E2: No API detected returns None gracefully"""
    html = '<html><body>No API here</body></html>'
    result = await _detect_search_api(html)
    assert result.found is False

@pytest.mark.asyncio
async def test_search_api_timeout_graceful():
    """E2: Search API probe timeout handled gracefully (no exception)"""
    # Mock httpx timeout
    result = await _detect_search_api(html, probe_timeout=0.001)
    assert result.found is False
```

**Rationale**:
- Addresses real-world patterns: Elasticsearch variants, auth requirements, custom paths
- Minimal file sprawl (expand existing tests, don't create new files)
- Brings coverage from 77% → 80%+ (estimated +5 tests with ~30 lines each = ~150 lines covered)
- Tests can be run in isolation without external dependencies

---

## Data Flow

```
┌─────────────────────────────────────────────────────────────┐
│ User discovers signal mismatch on real e-commerce site      │
│ Example: WooCommerce site shows cart as SERVER_SIDE,        │
│          but actual detection says AJAX                     │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ Manual log entry in docs/T2_false_negative_log.csv          │
│ platform: WooCommerce                                       │
│ url: https://example.com                                    │
│ signal: E6_inventory                                        │
│ expected: AJAX                                              │
│ actual: SERVER_SIDE (incorrect detection)                   │
│ discovered_date: 2026-05-14                                 │
│ status: open                                                │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ Run fixture generator (on-demand or scheduled)              │
│ python scripts/csv_to_fixture.py docs/T2_false_negative... │
│   --platform woocommerce                                    │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ Generate test case code                                     │
│ tests/real/test_woocommerce_t2_fixtures.py                 │
│ (3-5 new test functions, one per CSV row)                  │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ pytest discovers test cases (pytest --collect-only)         │
│ Tests run in nightly smoke suite or CI/CD                  │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ Test fails (validates the bug still exists)                 │
│ OR                                                           │
│ Test passes (if signal detection was fixed)                 │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ Once fixed: update CSV status from "open" → "resolved"     │
│ Keep test in suite (prevents regression)                    │
└─────────────────────────────────────────────────────────────┘
```

---

## File Changes (Concrete Paths & What Each Does)

| File Path | Action | What & Why |
|-----------|--------|-----------|
| `tests/smoke/test_pipeline_smoke.py` | **Modify** | Fix `_make_antibot()` factory: add `behavioral_score` and `journey_blocked_type` parameters; populate `BehavioralDetectionDimension` and `JourneyDimension` in returned `AntibotResult.dimensions`. Unblocks all 4 snapshot tests. |
| `tests/smoke/fixtures/snapshots/v2/` | **Create** (dir) | New versioned snapshot directory. Move existing snapshots here or regenerate with `UPDATE_SNAPSHOTS=1` after factory fix. |
| `tests/smoke/fixtures/snapshots/v2/static_blog.json` | **Create** | Snapshot for static blog archetype (Article JSON-LD, no JS, no antibot). |
| `tests/smoke/fixtures/snapshots/v2/shopify_pdp.json` | **Create** | Snapshot for Shopify PDP (Product JSON-LD, HYBRID, low antibot). |
| `tests/smoke/fixtures/snapshots/v2/cloudflare_gated.json` | **Create** | Snapshot for Cloudflare challenge page (HIGH antibot score). |
| `tests/smoke/fixtures/snapshots/v2/consent_onetrust.json` | **Create** | Snapshot for OneTrust consent banner (low antibot, COOKIE_CONSENT blocking). |
| `tests/integration/test_e7_helpers.py` | **Create** | 8-10 integration tests for playwright_helper: XHR pattern setup (2), scroll/pagination (2), cart button (2), context cleanup (2), integration (1-2). Mock-based, no real browser needed. |
| `tests/real/fixtures/woocommerce_sample.html` | **Create** | Sample HTML fixture for WooCommerce (cached response or live endpoint capture). Used by WooCommerce platform tests. |
| `tests/real/fixtures/shopify_sample.html` | **Create** | Sample HTML fixture for Shopify storefront. |
| `tests/real/fixtures/custom_spa_sample.html` | **Create** | Sample HTML fixture for custom SPA (headless framework, no CMS). |
| `tests/real/fixtures/regional_br_sample.html` | **Create** | Sample HTML fixture for regional variant (e.g., Portuguese locale, Brazil-specific platform). |
| `tests/real/test_woocommerce.py` | **Create** | 3-5 baseline tests for WooCommerce platform: cart mechanism (E6), variants (E3), product schema (C1), price reliability (E1). |
| `tests/real/test_shopify.py` | **Create** | 3-5 baseline tests for Shopify: same signal suite as WooCommerce. |
| `tests/real/test_custom_spa.py` | **Create** | 3-5 baseline tests for custom SPA: focus on CSR rendering, API detection, no CMS framework. |
| `tests/real/test_regional_br.py` | **Create** | 3-5 baseline tests for regional variant: focus on locale-aware signal detection, currency/language handling. |
| `tests/real/test_woocommerce_t2_fixtures.py` | **Create** (auto-gen) | Auto-generated test file from fixture generator script. Each row in T2 CSV becomes one test. File regenerated on each run of `scripts/csv_to_fixture.py`. |
| `tests/real/conftest.py` | **Create** | Shared pytest fixtures for real tests: live URL resolution, timeout defaults, mark registration (@pytest.mark.real, @pytest.mark.woocommerce, etc.). |
| `tests/unit/test_api_detector_search_api.py` | **Modify** | Add 5 edge case tests (Elasticsearch variants, auth patterns, custom paths, timeout handling). Expand from 10 → 15 tests. |
| `docs/T2_false_negative_log.csv` | **Create** | CSV log of discovered false negatives. Columns: platform, url, signal, expected, actual, discovered_date, status. Maintained by team; read by fixture generator. |
| `docs/build/phase4_t2_design.md` | **Create** | This design document (for reference). |
| `scripts/csv_to_fixture.py` | **Create** | Fixture generator script. Reads T2 CSV, generates pytest test case code. Usage: `python scripts/csv_to_fixture.py <csv_path> --platform <name>`. |
| `docs/BACKLOG.md` | **Modify** | Document Phase 4 completion: snapshot fix (section Snapshot Tests), T2 system (section Testing / Validación real), platform fixtures added, E7/api_detector coverage improvements. Update coverage metrics. |

**Total Changes**: 3 files modified, 20 files created (includes auto-gen + fixtures).

---

## Interfaces / Contracts

### T2 CSV Format (`docs/T2_false_negative_log.csv`)

**CSV Header**:
```csv
platform,url,signal,expected,actual,discovered_date,status
```

**Example Rows**:
```csv
WooCommerce,https://shop.example.com/product/widget,E6_inventory,"AJAX","SERVER_SIDE (incorrect)",2026-05-14,open
Shopify,https://shop.example.myshopify.com/products/widget,E3_variants,"dropdown, swatch","button only",2026-05-14,open
Custom SPA,https://app.example.com/products/widget,E2_search_api,"Algolia endpoint","not detected",2026-05-14,open
Regional (PT-BR),https://loja.example.com.br/produtos,E1_price,"JSON-LD in HTML","dynamic JS only (R$ currency)",2026-05-14,open
```

**Constraints**:
- `platform`: Required, free text (enables grouping)
- `url`: Required, valid URL or domain
- `signal`: Required, must match signal ID (E1-E7, or dimension like "E6_inventory")
- `expected`: Required, human-readable description of expected detection
- `actual`: Required, what was actually detected (or "not detected")
- `discovered_date`: Required, ISO 8601 format (YYYY-MM-DD)
- `status`: Required, one of: "open" | "resolved" | "wontfix"

---

### Fixture Generator Script (`scripts/csv_to_fixture.py`)

**Input**: CSV file path, optional `--platform` filter

```bash
python scripts/csv_to_fixture.py docs/T2_false_negative_log.csv --platform woocommerce
```

**Output**: Generated pytest test file (written to `tests/real/test_{platform_slug}_t2_fixtures.py`)

**Generated Test Template**:
```python
import pytest
from modules.classifier import classify_page

@pytest.mark.real
@pytest.mark.asyncio
async def test_t2_woocommerce_e6_inventory():
    """T2: WooCommerce E6 inventory detection (discovered 2026-05-14)"""
    url = "https://shop.example.com/product/widget"
    result = await classify_page(url, timeout=15.0)
    
    # Auto-generated assertion based on signal ID
    assert result.classifier.ecommerce is not None
    assert result.classifier.ecommerce.inventory is not None
    assert result.classifier.ecommerce.inventory.mechanism == "AJAX"
```

**Behavior**:
- Reads CSV row, maps signal ID to assertion logic
- Generates valid, runnable pytest code
- Checks for existing test with same signal + platform (skips if found)
- Writes to file; overwrites on re-run
- Return code 0 on success, 1 on parse error

**Signal → Assertion Mapping**:
| Signal | Assertion |
|--------|-----------|
| E1_price | `result.classifier.ecommerce.price_reliability_score` exists and matches expected |
| E2_search_api | `result.classifier.ecommerce.search_api.found` and `.api_type` match |
| E3_variants | `result.classifier.ecommerce.variants.has_variants` and `.selector_type` match |
| E4_pdp_samples | `result.classifier.pdp_samples` length ≥ 2 |
| E5_reviews | `result.classifier.ecommerce.reviews_provider.provider` matches |
| E6_inventory | `result.classifier.ecommerce.inventory.mechanism` matches |
| E7_deep_mode | `result.classifier.ecommerce.e7_deep_mode` is populated |

---

### Platform Fixture Test Structure

**Test File Pattern** (per platform):

```python
# tests/real/test_{platform_slug}.py
import pytest
from modules.classifier import classify_page

@pytest.mark.real
@pytest.mark.{platform_slug}
@pytest.mark.asyncio
async def test_{platform_slug}_{signal_id}():
    """T1: Baseline {platform} {signal_id} detection"""
    url = "https://real-{platform}-site.com"
    result = await classify_page(url, timeout=15.0)
    
    # Signal-specific assertion
    assert result.classifier.ecommerce is not None
    assert getattr(result.classifier.ecommerce, '{signal_field}') is not None
```

**Fixture HTML Storage** (cached):

```
tests/real/fixtures/
├── woocommerce_sample.html         (1-5 KB HTML cache)
├── shopify_sample.html
├── custom_spa_sample.html
├── regional_br_sample.html
└── README.md (notes on fixture sources, refresh dates, etc.)
```

**Marks for Test Filtering**:
- `@pytest.mark.real` — all real-platform tests
- `@pytest.mark.woocommerce` — WooCommerce specific
- `@pytest.mark.shopify` — Shopify specific
- (similar for custom, regional)

---

### E7 Integration Test Structure

**Test File**: `tests/integration/test_e7_helpers.py`

**Test Template** (mock-based):

```python
import pytest
from unittest.mock import AsyncMock, MagicMock
from utils.playwright_helper import setup_xhr_interception, scroll_page, find_and_click_cart_button

@pytest.mark.asyncio
async def test_setup_xhr_interception_price_pattern():
    """E7: XHR pattern setup captures price requests"""
    # Mock Playwright page + context
    page = AsyncMock()
    context = AsyncMock()
    
    # Call function
    await setup_xhr_interception(page, context, patterns=["price"])
    
    # Verify pattern was registered
    page.on.assert_called()  # Listener registered
```

**Critical Paths to Test**:
1. XHR pattern registration and capture
2. Timeout handling (no hang, returns gracefully)
3. Error recovery (missing Playwright, context errors)
4. Cart button detection (hidden elements, visibility checks)

---

## Testing Strategy

| Layer | What to Test | Approach | Notes |
|-------|------------|----------|-------|
| **Unit** | CSV parsing, fixture generation logic | Mock file I/O; verify Python syntax of output | No external deps |
| **Unit** | T2 CSV schema validation | Pydantic model or regex; ensure all required columns | Simple CLI test |
| **Unit** | api_detector edge cases (5 new tests) | Existing unit test pattern; mock httpx responses | Fast, no network |
| **Integration** | E7 playwright_helper (8-10 tests) | Mock Playwright page/context; test XHR capture, timeout, cleanup | Fast, no browser needed |
| **Integration** | E7 graceful None return if Playwright unavailable | Skip or mock `get_browser_context()` | Validates production fallback |
| **Smoke** | Snapshot stability (4 tests) | Run snapshot test after factory fix; verify no regressions | Self-documenting |
| **Real** | Platform fixtures (4 platforms × 3-5 signals each) | Live URL or cached HTML; validate signal detection | Marked @pytest.mark.real; skip in CI if needed |
| **Real** | T2 auto-generated fixtures | Run on nightly; validate test auto-generation and execution | Optional in CI |

**Test Execution Strategy**:

```bash
# Unit + integration (fast, no real network)
make test                                  # All tests including E7 integration

# Smoke tests (validation)
pytest tests/smoke/ -v                     # Snapshot tests (4 tests)

# Real platform tests (optional in CI, run on-demand)
pytest tests/real/ -m real -v              # All real platform tests
pytest tests/real/ -m woocommerce -v       # WooCommerce only

# T2 fixture auto-generation (on-demand)
python scripts/csv_to_fixture.py docs/T2_false_negative_log.csv --platform woocommerce
pytest tests/real/test_woocommerce_t2_fixtures.py -v

# Full nightly suite (including real tests)
pytest tests/ -v --tb=short
```

**TDD Strategy** (per project guidance):

- **Fixture generator**: ❌ **NO TDD** — infrastructure; build script first, test after manual validation
- **Snapshot tests**: ✅ **Manual validation** — fixtures are self-documenting; verify snapshots match expected structure
- **Platform fixtures**: ✅ **Tests alongside fixtures** — fixture HTML drives test expectations
- **E7 helpers**: ⚠️ **Minimal TDD** — mocks acceptable; focus on critical paths (timeout, error recovery)
- **api_detector edge cases**: ✅ **Unit tests** — standard pytest pattern; test-first for edge cases

---

## Open Questions

1. **T2 log refresh cadence**: How often should teams update T2 log? Weekly? Per-sprint? On-demand?
   - **Recommendation**: Weekly audit of known platforms; on-demand when new site discovered

2. **T2 log governance**: Who owns the T2 CSV? How to prevent stale entries?
   - **Recommendation**: Add "reviewed_date" column; auto-flag entries older than 30 days

3. **Regional fixture selection**: Which regions/locales to prioritize?
   - **Recommendation**: Start with PT-BR (large market, distinct patterns); add ES-MX, DE, FR later

4. **Real test timeout**: Should live tests have different timeout than scan (15s vs 10s)?
   - **Recommendation**: 15s for real tests (may include network delays); 5-10s for scan mode

5. **E7 deep mode snapshot**: Should snapshot tests include E7 results?
   - **Recommendation**: Defer; add E7 snapshot test in Phase 5 (after deep mode GA)

6. **Fixture generator dry-run**: Should script have `--dry-run` flag?
   - **Recommendation**: Yes; allows preview before writing to disk

---

## Risk Mitigation

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Snapshot test migration (4 tests failing during fix) | Blocks smoke suite | Fix factory + regenerate snapshots in single PR; test locally first |
| T2 CSV with stale entries (false negatives) | Misleading test results | Add "reviewed_date" field; auto-flag old entries; document refresh SLA |
| Fixture generator produces invalid Python | CI breaks | Validate output syntax before writing; add `--dry-run` for preview |
| Real platform tests flaky (network timeouts) | Intermittent failures | Use cached HTML fixtures; skip real tests in CI by default (@pytest.mark.real) |
| E7 helper tests insufficient (coverage stays low) | Low confidence in Playwright | Focus on critical paths: timeout, error recovery; add real Playwright test in Phase 5 |

---

## Phase 4 Success Criteria

✅ **Snapshot tests**: 4/4 passing (AntibotDimensions fields populated)  
✅ **Smoke suite**: All archetypes validate without regression  
✅ **T2 system**: CSV log established, fixture generator working, example entries documented  
✅ **Platform fixtures**: WooCommerce, Shopify, custom, regional baseline tests added  
✅ **E7 coverage**: 12% → 60%+ (8-10 new integration tests)  
✅ **api_detector coverage**: 77% → 80%+ (5 new edge case tests)  
✅ **Documentation**: BACKLOG updated, design archived, T2 system documented  

---

## Implementation Order (Recommended)

1. **Fix snapshot tests** (20 min): Update `_make_antibot()` factory, regenerate snapshots
2. **Create T2 system** (60 min): CSV template, fixture generator script, README
3. **Add E7 integration tests** (90 min): Mock playwright_helper, test timeout/error paths
4. **Expand platform fixtures** (120 min): Add 4 platform files + baseline tests
5. **Improve api_detector coverage** (40 min): Add 5 edge case tests
6. **Document and test** (30 min): Update BACKLOG, run `make test`, verify CI passes

**Total Estimated Time**: ~5 hours for full implementation + testing

---

## Archive & Handoff

**This design** → Stored in `docs/build/phase4_t2_design.md` (reference)  
**Task breakdown** → Generated by `sdd-tasks` (implementation checklist)  
**Implementation** → Delegated to `sdd-apply` (write actual code)  
**Verification** → Validated by `sdd-verify` (tests pass, coverage improved)  
**Completion** → Archive phase and merge to main BACKLOG via `sdd-archive`
