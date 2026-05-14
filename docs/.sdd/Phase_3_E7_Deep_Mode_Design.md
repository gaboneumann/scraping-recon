# Design: Phase 3 — Deep Mode Playwright E7

**Document Status**: READY FOR IMPLEMENTATION  
**Date**: 2026-05-14  
**Topic Key**: `sdd/Phase 3 — Deep Mode Playwright E7/design`

---

## Executive Summary

Phase 3 implements **E7: Deep Mode Runtime Detection** via Playwright XHR interception. This is a **conditional, post-classification module** that observes runtime behavior (JavaScript price mutations, infinite scroll pagination, cart API endpoints) only when:
1. Classifier result = `DYNAMIC` or `HYBRID`
2. `ecommerce.is_ecommerce = True`
3. CLI flag `--deep` is present

When activated, E7 launches a single Playwright browser context to capture XHR/fetch requests across three observation windows (price JS, infinite scroll, cart probe), returning structured `E7Result` or `None` on failure. E7 is **non-blocking**: missing data (Playwright unavailable, timeout, crash) degrades gracefully to E1-E6 analysis only.

**HTTP Budget**: Zero additional HTTP requests (pure XHR observation, no new probes). Browser init overhead (~3-5s) counts toward existing timeout padding.

**Integration**: E7 runs as **Phase 2 of main.py** orchestration (after classifier Phase 1, before antibot detection). Results feed into EcommerceSignals schema and influence recommender confidence.

---

## Technical Approach

### Why Playwright + XHR Interception?

Static HTML analysis (E1-E6) answers: *"What payment flows, product variants, inventory signals does the page structure suggest?"*

Runtime observation (E7) answers: *"What actual requests fire when users interact with the page?"*

**Example gap**: A page may show `price_mechanism: SERVER_SIDE` (price in HTML), but JavaScript still mutates the DOM with newer prices fetched via API. Without E7, scraper builder assumes HTML parsing is sufficient and misses the async API requirement.

### Conditional Execution (Why Phase 2?)

**Phase 1** (concurrent, HTTP-heavy):
- legal, classifier, auth_detector, api_detector, pagination, antibot
- All HTML-based; no Playwright overhead

**Decision point** (after Phase 1):
```
IF classifier.type in (DYNAMIC, HYBRID) AND ecommerce.is_ecommerce AND config.deep:
    LAUNCH E7_detect()
ELSE:
    SKIP E7; continue with Phase 2 (antibot if not already run)
```

**Rationale**:
- STATIC sites: no JavaScript execution possible; E7 wastes 3-5 seconds
- DYNAMIC/HYBRID sites: JavaScript is relevant; E7 confirms what observers are active
- e-commerce flag: Cart probes only make sense for retail; SaaS/content sites skip them
- `--deep` opt-in: Users can fast-scan with E1-E6 only (10-15s); opt into deep mode when evaluating complex targets

### XHR Interception Pattern

**Approach**: Route-based pattern matching (not raw logging).

```python
INTERCEPT_PATTERNS = {
    "price": [
        r"/api/price",
        r"/api/products/\d+/price",
        r"/graphql",  # Often used for price queries
        r"/data/products",
    ],
    "pagination": [
        r"/api/products",
        r"/api/category",
        r"/api/search",
        r"/api/listings",
        r"/api/items",
    ],
    "cart": [
        r"/api/cart",
        r"/cart/add",
        r"/checkout/cart",
        r"/api/checkout",
    ],
}
```

When a request matches a pattern:
- Capture: `url`, `method` (GET/POST/PUT), presence of auth headers
- **Do NOT** capture request body or response (privacy, memory)
- Store as: `{"url": "...", "method": "POST", "has_auth": True, "pattern": "cart"}`

**Why patterns?** Reduces memory footprint (no bodies), focuses on decision-critical signals, tolerates URL variations across sites.

### Three Observation Windows

**Window 1: Price JS Detection (3 seconds)**
1. Navigate to primary URL
2. Wait for page load (domcontentloaded + 500ms)
3. Setup price XHR listener
4. *Observe* (passive): any price requests that fire automatically or on page mutation
5. Collect: `js_price_requests: list[dict]`

**Window 2: Infinite Scroll Detection (5 scrolls)**
1. Scroll to bottom of page (or max 5 scrolls, timeout 5s)
2. On each scroll, *trigger* pagination API if detected
3. Collect: `infinite_scroll_pattern: "offset" | "cursor" | "page" | "unknown"`
4. Collect: `estimated_products: int` (if page provides count)

**Window 3: Cart Probe (2 seconds)**
1. Look for "Add to cart" or "Add to bag" button
2. On hover/visibility, capture cart-related XHR if fired
3. If visible, attempt gentle click (no order submission, just probe)
4. Collect: `cart_endpoints: list[str]`

**Total timeout**: 10 seconds maximum (leaves 5s buffer for other Phase 2 modules).

### Error Handling & Graceful Degradation

```python
async def _detect_deep_ecommerce(...) -> E7Result | None:
    try:
        # Browser init, navigation, XHR capture
        return E7Result(...)
    except PlaywrightException as e:
        logger.warning(f"E7 Playwright failed: {e.__class__.__name__}")
        return None  # Non-blocking failure
    except TimeoutError:
        logger.warning("E7 observation timeout (10s exceeded)")
        return None
    except Exception as e:
        logger.exception(f"E7 unexpected error: {e}")
        return None
```

When `E7Result = None`:
- EcommerceSignals.e7_deep_mode = None
- Recommender skips E7 boost logic
- User still gets E1-E6 analysis (complete, but without runtime visibility)

---

## Architecture Decisions

### Decision 1: Where E7 Runs in Pipeline

**Choice**: Phase 2, conditional, post-classifier.

```
main.py orchestration:

PHASE 1 (concurrent, 15-20s total)
├── legal_detect()
├── classify_page()         ← classifier.type determined here
├── detect_auth()
├── detect_apis()           ← api_endpoints found here
├── detect_pagination()
└── detect_antibot()

DECISION GATE
IF classifier.type in (DYNAMIC, HYBRID) AND ecommerce.is_ecommerce AND config.deep:
    ↓
PHASE 2 (sequential, E7 only, up to 10s)
    └── _detect_deep_ecommerce()  ← NEW

PHASE 3 (after Phase 2, or run parallel if E7 skipped)
    └── recommender(all_results)
```

**Rationale**:
- Classifier must run first (need render mode)
- Can launch Playwright while antibot completes (if antibot not yet done)
- E7 completes before recommender (recommender can use E7 data)
- Selective activation saves 3-5s on STATIC sites (majority)

### Decision 2: Playwright Context Management

**Choice**: Lazy init + async context manager (utils/playwright_helper.py).

```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def get_browser_context(timeout: float) -> AsyncGenerator[BrowserContext, None]:
    """
    Manages Playwright browser context with auto-cleanup.
    
    Handles:
    - Browser process launch (first use only; reused across E7 calls)
    - Context creation (per call)
    - Timeout enforcement at page level
    - Exception safety (cleanup on error)
    """
    browser = None
    context = None
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled"],  # Hide Playwright signal
            )
            context = await browser.new_context()
            yield context
    finally:
        if context:
            await context.close()
        if browser:
            await browser.close()
```

**Why context manager?** Ensures browser cleanup even on timeout/exception, readable code, standard async pattern.

### Decision 3: Single Browser Instance vs. Context Per Window

**Choice**: Single context for all 3 windows (reuse).

```python
async with get_browser_context(timeout=10.0) as context:
    page = await context.new_page()
    
    # Window 1: Price JS (reuse page, setup listener)
    # Window 2: Infinite scroll (same page, new listener)
    # Window 3: Cart probe (same page)
    
    await page.close()
```

**Rationale**:
- Browser init is 2-5s overhead; reusing a single page saves that cost
- Session cookies/state carry across windows (closer to real user journey)
- Single page = lower memory footprint than 3 separate pages

**Risk**: Page state mutation from Window 1 affects Window 2. Mitigation: Reload page between windows if state is stale.

### Decision 4: XHR Interception Implementation

**Choice**: `page.route()` with pattern matching (not `on('response')` logging).

```python
async def setup_xhr_interception(page, patterns: dict) -> dict:
    """
    Setup route interception for matching XHR patterns.
    
    Returns dict of captured requests: 
    {pattern: [{"url": "...", "method": "...", "has_auth": ...}, ...]}
    """
    captured = {p: [] for p in patterns.keys()}
    
    async def handle_route(route):
        request = route.request
        url = request.url
        
        # Check against all patterns
        for pattern_type, regex_list in patterns.items():
            if any(re.search(r, url) for r in regex_list):
                captured[pattern_type].append({
                    "url": url,
                    "method": request.method,
                    "has_auth": bool(request.headers.get("Authorization")),
                    "timestamp": time.time(),
                })
        
        # Continue request (don't block)
        await route.continue_()
    
    # Register interception for all requests
    await page.route("**/*", handle_route)
    return captured
```

**Why `page.route()`?** 
- Non-blocking (requests continue normally)
- Lightweight (no response body capture)
- Can modify headers/block if needed in future

### Decision 5: E7 Data Storage in EcommerceSignals

**Choice**: New optional field `e7_deep_mode: E7Result | None = None`.

```python
class EcommerceSignals(BaseModel):
    # ... existing E1-E6 fields ...
    
    # E7: Deep mode runtime detection (optional)
    e7_deep_mode: E7Result | None = None  # NEW
```

**Rationale**:
- Backwards compatible (None by default)
- No changes needed to existing recommender if E7 absent
- Clear separation: E1-E6 = static, E7 = dynamic
- Future phases (E8, E9) can follow same pattern

---

## Data Flow

```
User: python main.py --url <target> --deep

    ↓ main.py phase 1 (concurrent)

    ├─ legal_detect() → legal_scope
    ├─ classify_page() → classifier (includes E1-E6)
    ├─ detect_auth() → auth_result
    ├─ detect_apis() → api_result
    ├─ detect_pagination() → pagination_result
    └─ detect_antibot() → antibot_result

    ↓ Decision Gate

    IF classifier.type in (DYNAMIC, HYBRID) 
       AND classifier.ecommerce.is_ecommerce 
       AND config.deep:
        
        ↓ E7 invocation
        
        _detect_deep_ecommerce(url, timeout=10.0, config)
        
        ├─ launch Playwright browser + navigate url
        ├─ setup XHR interception (capture matching routes)
        ├─ Window 1: 3s price observation
        ├─ Window 2: 5 scroll events + pagination detection
        ├─ Window 3: 2s cart probe
        └─ return E7Result {
            js_price_requests,
            infinite_scroll_pattern,
            estimated_products,
            cart_endpoints,
            browser_execution_time_ms,
            confidence
        }
        
        OR on error: return None
        
        ↓ Store in EcommerceSignals
        
        classifier.ecommerce.e7_deep_mode = E7Result | None
    
    ELSE:
        classifier.ecommerce.e7_deep_mode = None
    
    ↓ Phase 3: Recommender

    recommender(full_scan_result)
    
    ├─ reads e7_deep_mode (if present)
    ├─ if E7Result.js_price_requests:
    │   └─ boost confidence: "runtime price APIs detected"
    ├─ if E7Result.infinite_scroll_pattern == "cursor":
    │   └─ suggest cursor-based pagination library
    └─ if E7Result.cart_endpoints:
        └─ flag: "cart API available for direct order tracking"
    
    ↓ Final Report Output

    terminal_report() / json_export()
```

---

## File Changes

| File | Action | What & Why |
|------|--------|-----------|
| `models/schemas.py` | **Modify** | Add `E7Result` Pydantic class; extend `EcommerceSignals` with `e7_deep_mode: E7Result \| None = None` |
| `modules/classifier.py` | **Modify** | Add `_detect_deep_ecommerce(url, timeout, config) -> E7Result \| None` function; async def; call from main decision gate |
| `utils/playwright_helper.py` | **Create** | Browser context manager, XHR interception setup, timeout enforcement, event listeners |
| `main.py` | **Modify** | Add Phase 2 conditional E7 execution; orchestrate decision gate; pass E7Result back to classifier.ecommerce |
| `config.py` | **No change** | `deep: bool` already exists (added in Phase 1 for `--deep` flag) |
| `tests/unit/test_e7_detection.py` | **Create** | Unit tests: XHR pattern matching, E7Result schema validation, timeout handling, error cases |
| `tests/integration/test_e7_pipeline.py` | **Create** | Integration: classifier result → E7 decision → recommender (mock Playwright) |

---

## Interfaces & Contracts

### New Schema: E7Result (models/schemas.py)

```python
class E7Result(BaseModel):
    """
    Deep-mode runtime detection results from Playwright XHR interception.
    
    Captures: JavaScript price APIs, infinite scroll patterns, cart endpoints.
    None if Playwright unavailable or timeout exceeded.
    """
    
    # Price JS detection
    js_price_requests: list[dict] | None = None
    # Each dict: {"url": "...", "method": "GET|POST", "has_auth": bool}
    
    # Pagination detection
    infinite_scroll_pattern: Literal["offset", "cursor", "page", "unknown"] | None = None
    estimated_products: int | None = None  # If page provides total count
    
    # Cart API detection
    cart_endpoints: list[str] | None = None  # URLs of cart/checkout APIs
    
    # Metadata
    browser_execution_time_ms: int  # Total window time (for logging/profiling)
    confidence: Literal["high", "medium", "low"]
    
    class Config:
        """Allow additional fields for future extensibility."""
        extra = "allow"
```

### Modified Schema: EcommerceSignals (models/schemas.py)

```python
class EcommerceSignals(BaseModel):
    """E-commerce reconnaissance signals (E1-E7)."""
    
    # ... existing E1-E6 fields (unchanged) ...
    is_ecommerce: bool = False
    platform: str | None = None
    price_mechanism: Literal["CLIENT_SIDE", "SERVER_SIDE", "UNKNOWN"] = "UNKNOWN"
    price_reliability_score: float = 0.5
    cart_architecture: Literal["AJAX_FRAGMENTS", "AJAX_API", "SECTION_CACHE", "UNKNOWN"] = "UNKNOWN"
    has_faceted_nav: bool = False
    has_product_schema: bool = False
    
    # E2-E6 (from Phase 2)
    search_api: SearchApiResult | None = None
    variants: VariantInfo | None = None
    pdp_samples: list[PdpSampleResult] = []
    reviews_provider: ReviewsProviderInfo | None = None
    inventory: InventoryInfo | None = None
    
    # E7: NEW
    e7_deep_mode: E7Result | None = None  # Optional runtime detection
```

### New Function Signature: _detect_deep_ecommerce (modules/classifier.py)

```python
async def _detect_deep_ecommerce(
    url: str,
    timeout: float = 10.0,
    config: Config | None = None,
) -> E7Result | None:
    """
    Detect E7 signals (JS price, infinite scroll, cart) via Playwright.
    
    Args:
        url (str): Target URL to probe
        timeout (float): Max execution time in seconds (default: 10)
        config (Config): CLI config (includes deep flag, user agent, etc.)
    
    Returns:
        E7Result if detection successful, None if:
        - Playwright not installed
        - Browser launch failed
        - Timeout exceeded
        - Page unreachable
        - XHR interception setup failed
    
    Notes:
        - Only call if classifier.type in (DYNAMIC, HYBRID) and ecommerce.is_ecommerce
        - Respects timeout strictly; kills browser on excess
        - Captures XHR patterns only, not request bodies (privacy)
        - Graceful fallback: None treated as "E7 unavailable, continue with E1-E6"
    
    Example:
        result = await _detect_deep_ecommerce(
            url="https://example.com/products",
            timeout=10.0,
            config=config,
        )
        if result:
            print(f"Price APIs: {result.js_price_requests}")
            print(f"Pagination: {result.infinite_scroll_pattern}")
    """
    ...
```

### New Helper Module: utils/playwright_helper.py

```python
"""Playwright utilities for E7 deep-mode XHR interception."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator, Any
import asyncio
import logging
from playwright.async_api import async_playwright, BrowserContext, Page

logger = logging.getLogger(__name__)

@asynccontextmanager
async def get_browser_context(
    timeout: float = 10.0,
    headless: bool = True,
) -> AsyncGenerator[BrowserContext, None]:
    """
    Async context manager for Playwright browser context.
    
    Handles browser launch, context creation, and cleanup.
    Enforces timeout at page level.
    
    Args:
        timeout: Max execution time (seconds)
        headless: Run in headless mode (default True)
    
    Yields:
        BrowserContext ready for page creation
    
    Usage:
        async with get_browser_context(timeout=10.0) as context:
            page = await context.new_page()
            await page.goto(url, wait_until="domcontentloaded")
    
    Ensures cleanup even on timeout or exception.
    """
    ...

async def setup_xhr_interception(
    page: Page,
    patterns: dict[str, list[str]],
) -> dict[str, list[dict]]:
    """
    Setup XHR/fetch interception and capture matching requests.
    
    Args:
        page: Playwright Page object
        patterns: Dict of {signal_type: [url_regex_patterns]}
                  e.g., {"price": ["/api/price", "/graphql"]}
    
    Returns:
        Dict of captured requests: 
        {pattern_type: [{"url": "...", "method": "...", "has_auth": ...}]}
    
    Notes:
        - Non-blocking: allows requests to complete
        - Does NOT capture response bodies (privacy, memory)
        - Captures only URL, method, auth presence
    """
    ...

async def scroll_page_to_bottom(
    page: Page,
    max_scrolls: int = 5,
    scroll_delay_ms: int = 500,
) -> int:
    """
    Scroll page to bottom, triggering pagination if present.
    
    Returns:
        Number of scrolls actually performed (may be < max_scrolls if page height stable)
    """
    ...

async def find_and_click_cart_button(
    page: Page,
    gentle: bool = True,
) -> bool:
    """
    Find and click "Add to cart" button, triggering cart API if present.
    
    Args:
        page: Playwright Page
        gentle: If True, hover only (no actual click); if False, click
    
    Returns:
        True if button found and clicked/hovered, False if not found
    """
    ...
```

---

## Testing Strategy

### Unit Tests (test_e7_detection.py)

| What | How | Why |
|------|-----|-----|
| **XHR pattern matching** | Mock request objects; test regex patterns against various URLs | Ensure correct requests captured, false positives filtered |
| **E7Result schema** | Pydantic validation with valid/invalid inputs | Ensure data integrity, optional fields handle None |
| **Timeout enforcement** | Mock Playwright timeout; verify E7 returns None | Graceful degradation on timeout |
| **Error handling** | Mock PlaywrightException, TimeoutError; verify None return | Non-blocking failures |
| **Observation windows** | Mock page state changes; verify correct data captured per window | Correct signal detection (price vs. pagination vs. cart) |

### Integration Tests (test_e7_pipeline.py)

| What | How | Why |
|------|-----|-----|
| **Decision gate logic** | Mock classifier results; trigger E7 only on DYNAMIC + ecommerce | Correct conditional execution |
| **Classifier integration** | Mock E7Result; verify stored in EcommerceSignals | Data flows to recommender correctly |
| **Recommender use of E7** | E7Result present/absent; verify recommender reacts | Recommendations improve with E7 data |

### Optional: Real Playwright Integration (slow, not required)

- Use test site (e.g., buscalibre.cl DYNAMIC e-commerce)
- Verify real XHR interception works
- Validate E7Result against production scraper observations
- Run once per release (not in CI)

---

## Design Decisions Summary

| # | Decision | Choice | Rationale |
|---|----------|--------|-----------|
| 1 | Pipeline location | Phase 2, post-classifier, conditional | Need render mode first; save overhead on STATIC sites |
| 2 | Browser management | Async context manager, single context/all windows | Reuse browser init cost; cleaner async code |
| 3 | Context reuse | Single page across 3 windows | Lower memory/time vs. separate pages |
| 4 | XHR interception | Pattern-based route filtering | Lightweight, privacy-conscious, focuses on decisions |
| 5 | Storage | New `E7Result` + optional field in EcommerceSignals | Backwards compatible, clear separation of concerns |
| 6 | Error handling | Graceful None return | E7 optional; missing data doesn't block scan |
| 7 | Timeout | 10s max, kills browser on excess | Budget-aware, leaves padding for other modules |
| 8 | TDD strategy | Unit tests for detection logic; mocks for Playwright | Critical functions require tests; browser logic can mock |

---

## Open Questions

1. **Session/Auth for Cart Probe**: Should E7 attempt cart probe even without active session?
   - Current: Probe regardless of auth status
   - Future: Check `auth_detector.login_required`; skip if True (would require login)
   - Decision: **Probe regardless** (naive, but gives signal if public cart API exists)

2. **Dynamic Render Delays**: Some sites load prices after 5+ seconds of JavaScript execution.
   - Current: Fixed 3s window
   - Future: Adaptive wait based on page activity
   - Decision: **Fixed 3s** (acceptable tradeoff; user can re-run with adjusted timeout)

3. **Cart Button Click vs. Hover**: Should E7 actually click "Add to Cart" or just observe button presence?
   - Current: Hover only (safe, non-invasive)
   - Future: Click if site explicitly allows (no production order submission)
   - Decision: **Hover only** (safest, still captures cart API if it fires on hover)

4. **Rate Limiting During E7**: If Playwright triggers many requests, could site rate-limit?
   - Current: No explicit rate-limiting between windows
   - Future: Exponential backoff if 429 detected
   - Decision: **No backoff** (short windows, unlikely to trigger; user can retry)

---

## Rollout & Migration

**No migration required.**

- E7 is opt-in (`--deep` flag)
- `E7Result` is optional field (None by default)
- E1-E6 unaffected (backward compatible)
- Can deploy behind feature flag; rollback by removing E7 invocation in main.py
- Playwright dependency already listed in requirements.txt (Phase 1 added it)

---

## Related Documents

- **Proposal**: `Phase_3_E7_Deep_Mode_Proposal.md` (approved by orchestrator)
- **Specs**: `Phase_3_E7_Deep_Mode_Specs.md` (requirements + scenarios)
- **BACKLOG**: `docs/BACKLOG.md` (Phase 3, lines ~48-70)
- **Phase 2 Design**: `Phase_2_E2-E6_Design.md` (reference for patterns)

---

**Ready for Tasks Breakdown** → orchestrator will present sdd-tasks summary.
