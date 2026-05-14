# Tasks: Phase 3 — Deep Mode Playwright E7

**Document Status**: READY FOR IMPLEMENTATION  
**Date**: 2026-05-14  
**Topic Key**: `sdd/Phase 3 — Deep Mode Playwright E7/tasks`  
**Total Tasks**: 43  
**Phases**: 8

---

## Phase 1: Schemas & Types Foundation (3 tasks)

**Goal**: Create Pydantic models for E7 results and extend existing schemas.

- [ ] **1.1** Create `E7Result` Pydantic class in `models/schemas.py`
  - Fields: `js_price_requests: list[dict] | None`, `infinite_scroll_pattern: Literal["offset", "cursor", "page", "unknown"] | None`, `estimated_products: int | None`, `cart_endpoints: list[str] | None`, `browser_execution_time_ms: int`, `confidence: Literal["high", "medium", "low"]`
  - Add docstring describing deep-mode runtime detection
  - Set `extra = "allow"` in Config for future extensibility
  - **Verifiable**: `from models.schemas import E7Result; e = E7Result(js_price_requests=[], infinite_scroll_pattern="cursor", estimated_products=100, cart_endpoints=[], browser_execution_time_ms=5000, confidence="high")` succeeds

- [ ] **1.2** Extend `EcommerceSignals` in `models/schemas.py` with optional `e7_deep_mode` field
  - Add field: `e7_deep_mode: E7Result | None = None` after existing E1-E6 fields
  - Add docstring comment: `# E7: Deep mode runtime detection (optional, None if --deep not specified or browser unavailable)`
  - **Verifiable**: `EcommerceSignals(is_ecommerce=True, ..., e7_deep_mode=None)` instantiates; both with and without E7Result work

- [ ] **1.3** Verify imports in `modules/classifier.py`
  - Add import: `from models.schemas import E7Result, EcommerceSignals`
  - Verify all existing imports remain (no unused imports)
  - **Verifiable**: `python -c "from modules.classifier import E7Result"` succeeds with no ImportError

---

## Phase 2: Playwright Helper Module (5 tasks)

**Goal**: Create infrastructure for browser lifecycle management and XHR interception.

- [ ] **2.1** Create `utils/playwright_helper.py` with async context manager for browser lifecycle
  - Implement `async def get_browser_context(timeout: float = 10.0, headless: bool = True) -> AsyncGenerator[BrowserContext, None]`
  - Handles: browser launch (headless, with `--disable-blink-features=AutomationControlled`), context creation, cleanup on error/timeout
  - Add docstring with usage example
  - **Verifiable**: `async with get_browser_context(timeout=10.0) as ctx: page = await ctx.new_page(); ...` completes without exception

- [ ] **2.2** Implement XHR route interception function in `utils/playwright_helper.py`
  - Implement `async def setup_xhr_interception(page: Page, patterns: dict[str, list[str]]) -> dict[str, list[dict]]`
  - Captures: `{"url": "...", "method": "GET|POST", "has_auth": bool, "timestamp": float}` for each matched request
  - Use `page.route("**/*", handle_route)` to intercept all requests
  - Pattern matching: check each request URL against regex list in patterns dict
  - Do NOT capture response bodies or request bodies (privacy)
  - Continue request normally (non-blocking)
  - Add docstring with example patterns and return format
  - **Verifiable**: Setup interception on mock page, trigger requests, verify captured dict has correct structure and content

- [ ] **2.3** Implement page scrolling helper function in `utils/playwright_helper.py`
  - Implement `async def scroll_page_to_bottom(page: Page, max_scrolls: int = 5, scroll_delay_ms: int = 500) -> int`
  - Scroll page to bottom in a loop, yield control between scrolls to trigger lazy-loading
  - Return number of scrolls actually performed
  - Handle: page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
  - Add timeout: if scroll not changing height after 500ms, break early
  - Add docstring
  - **Verifiable**: Call on mock page, verify returns int <= max_scrolls, page scrolls occur

- [ ] **2.4** Implement cart button detection and click helper in `utils/playwright_helper.py`
  - Implement `async def find_and_click_cart_button(page: Page, gentle: bool = True) -> bool`
  - Find button with text matching: "add to cart", "add to bag", "add to basket", "buy now" (case-insensitive, common e-commerce patterns)
  - If `gentle=True`: hover over button only (no click)
  - If `gentle=False`: click button
  - Return True if found and hovered/clicked, False if not found
  - Add error handling: if button not found or hover/click fails, return False (don't crash)
  - Add docstring
  - **Verifiable**: Call on mock page with cart button, verify returns True; on page without, returns False

- [ ] **2.5** Add error handling and timeout enforcement to all helpers in `utils/playwright_helper.py`
  - Wrap all async operations in try/except for `PlaywrightException`, `TimeoutError`, `Exception`
  - Log warnings (not errors) on exception: `logger.warning(f"XHR interception setup failed: {e.__class__.__name__}")`
  - Each function returns graceful fallback (empty dict, 0, False, None) instead of raising
  - Add docstring notes about timeout behavior
  - Add logger initialization: `logger = logging.getLogger(__name__)`
  - **Verifiable**: Mock Playwright failure, call helpers, verify warning logged and function returns gracefully

---

## Phase 3: E7 Detection Function (7 tasks)

**Goal**: Implement core E7 detection logic with 3 observation windows.

- [ ] **3.1** Implement `_detect_deep_ecommerce(url: str, timeout: float = 10.0, config: Config | None = None) -> E7Result | None` in `modules/classifier.py`
  - Signature: async function, takes url, timeout (default 10), optional config
  - Add comprehensive docstring with args, returns, notes, example
  - Function body: try/except wrapping all logic; return None on PlaywrightException, TimeoutError, Exception
  - Log warnings on error (not exception level)
  - **Verifiable**: Function exists with correct signature, docstring present, returns E7Result or None

- [ ] **3.2** Implement decision gate logic in `_detect_deep_ecommerce()`
  - Check preconditions before launching browser:
    - `if config and not config.deep: return None` (flag not set)
    - Caller guarantees classifier.type in (DYNAMIC, HYBRID) and ecommerce.is_ecommerce (verified in main.py)
  - Log debug message: `logger.debug("E7: Launching deep-mode Playwright detection")`
  - If preconditions fail, return None silently
  - **Verifiable**: Call with config.deep=False, verify returns None immediately without browser launch

- [ ] **3.3** Implement Window 1: Price JS detection (3-second observation window)
  - Navigate to URL: `await page.goto(url, wait_until="domcontentloaded", timeout=3000)`
  - Wait additional 500ms for initial JS: `await page.wait_for_timeout(500)`
  - Setup XHR interception for price patterns: `{price: [r"/api/price", r"/api/products/\d+/price", r"/graphql", r"/data/products"]}`
  - Observe for 3 seconds: `await page.wait_for_timeout(3000)`
  - Capture: `js_price_requests = captured_requests["price"]` (list of dicts)
  - Add docstring comment in code: `# Window 1: Passive observation of price JS requests`
  - **Verifiable**: Window 1 completes within 3s, js_price_requests populated with matched request dicts

- [ ] **3.4** Implement Window 2: Infinite scroll pagination detection
  - Reuse page from Window 1 (no reload)
  - Setup XHR interception for pagination patterns: `{pagination: [r"/api/products", r"/api/category", r"/api/search", r"/api/listings", r"/api/items"]}`
  - Scroll page to bottom using `scroll_page_to_bottom(page, max_scrolls=5)`
  - Analyze captured pagination requests to detect pattern:
    - If `offset` parameter in any request → `infinite_scroll_pattern = "offset"`
    - If `cursor` parameter → `infinite_scroll_pattern = "cursor"`
    - If `page` parameter → `infinite_scroll_pattern = "page"`
    - Else → `infinite_scroll_pattern = "unknown"`
  - Try to extract `estimated_products` from page meta tags or JS variables (e.g., `data-total-items`, `window.totalProducts`)
  - Capture: `estimated_products: int | None`
  - **Verifiable**: Window 2 detects pagination pattern correctly; estimated_products extracted if available

- [ ] **3.5** Implement Window 3: Cart API endpoint probing
  - Reuse page from Windows 1-2 (no reload)
  - Setup XHR interception for cart patterns: `{cart: [r"/api/cart", r"/cart/add", r"/checkout/cart", r"/api/checkout"]}`
  - Call `find_and_click_cart_button(page, gentle=True)` to hover over cart button
  - Wait 2 seconds: `await page.wait_for_timeout(2000)` for any cart API to fire on hover
  - Capture: `cart_endpoints = [req["url"] for req in captured_requests["cart"]]` (list of URLs)
  - If cart button not found, still observe for 2s (may trigger API on auto-load)
  - **Verifiable**: Window 3 detects cart endpoints; gentle=True prevents actual purchase

- [ ] **3.6** Aggregate results into E7Result with confidence scoring
  - Calculate `browser_execution_time_ms` as total time from browser launch to window 3 completion
  - Score confidence based on signal clarity:
    - `"high"`: At least 2 windows captured meaningful data (js_price_requests + pagination/cart)
    - `"medium"`: 1 window captured data
    - `"low"`: Windows ran but no clear signal; or short timeout
  - Create `E7Result(js_price_requests=..., infinite_scroll_pattern=..., estimated_products=..., cart_endpoints=..., browser_execution_time_ms=..., confidence=...)`
  - **Verifiable**: E7Result created with all fields populated; confidence logic correct

- [ ] **3.7** Add error handling for PlaywrightException and TimeoutError
  - Wrap entire function body in try/except:
    - `except PlaywrightException as e: logger.warning(f"E7 Playwright error: {e.__class__.__name__}"); return None`
    - `except asyncio.TimeoutError: logger.warning("E7 observation timeout (10s exceeded)"); return None`
    - `except Exception as e: logger.exception(f"E7 unexpected error: {e}"); return None`
  - Verify browser is closed even on exception (context manager handles this)
  - **Verifiable**: Mock Playwright failure, verify warning logged and function returns None gracefully

---

## Phase 4: Pipeline Integration (4 tasks)

**Goal**: Wire E7 detection into main.py orchestration and verify backward compatibility.

- [ ] **4.1** Modify `main.py` Phase 2 to conditionally call E7 detection
  - Locate `_run_scan()` function; find where Phase 1 results are gathered
  - After Phase 1 completes (all concurrent tasks done), add decision gate:
    ```python
    if (classifier_result.type in (PageType.DYNAMIC, PageType.HYBRID) 
        and classifier_result.ecommerce.is_ecommerce 
        and config.deep):
        logger.info("Phase 2: E7 deep-mode detection (conditional)")
        e7_result = await _detect_deep_ecommerce(url, timeout=10.0, config=config)
        if e7_result:
            classifier_result.ecommerce.e7_deep_mode = e7_result
    ```
  - Add import: `from modules.classifier import _detect_deep_ecommerce`
  - Add comment above gate: `# Decision gate: only run E7 on DYNAMIC/HYBRID e-commerce sites with --deep flag`
  - **Verifiable**: Decision gate appears in correct location in _run_scan(); imports added

- [ ] **4.2** Verify E7Result is passed back and stored in EcommerceSignals
  - Confirm `classifier_result.ecommerce.e7_deep_mode = e7_result` assignment in Phase 2
  - If E7 skipped (preconditions fail), `e7_deep_mode` remains None (default)
  - Trace data flow: `_run_scan()` returns `classifier_result` → `recommender()` reads `ecommerce.e7_deep_mode`
  - Add docstring comment: `# E7 data flows to recommender for enhanced confidence scoring`
  - **Verifiable**: Full scan with --deep populates e7_deep_mode in classifier result; without --deep, e7_deep_mode=None

- [ ] **4.3** Verify recommender backward compatibility
  - Open `modules/recommender.py` and check `build_recommendation(scan_result)` function
  - Verify recommender can read `scan_result.ecommerce.e7_deep_mode` without crash:
    - If e7_deep_mode is None: skip E7 boost logic (continue as before)
    - If e7_deep_mode is E7Result: optionally use fields for confidence/suggestion boost
  - Add safe access: `if scan_result.ecommerce.e7_deep_mode:`
  - No changes required if recommender doesn't yet use E7 data (E7 is optional)
  - **Verifiable**: Recommender runs without error when e7_deep_mode=None and when populated

- [ ] **4.4** Test full pipeline smoke tests with --deep flag
  - **Smoke test 1**: Scan DYNAMIC e-commerce site with `--deep` flag
    - Command: `python main.py --url https://buscalibre.cl --deep --json -o /tmp/e7_test.json`
    - Verify E7Result populated in output (js_price_requests, cart_endpoints, etc. not empty)
    - Verify no crashes or errors
  - **Smoke test 2**: Scan STATIC site (e.g., amazon.com homepage) with `--deep` flag
    - Command: `python main.py --url https://amazon.com --deep --json -o /tmp/static_test.json`
    - Verify E7 skipped (classifier.type=STATIC, e7_deep_mode=None)
    - Verify scan completes in <15s (no Playwright overhead)
  - **Smoke test 3**: Scan DYNAMIC site without `--deep` flag
    - Command: `python main.py --url https://buscalibre.cl --json -o /tmp/no_deep_test.json`
    - Verify E7 skipped (config.deep=False, e7_deep_mode=None)
  - **Verifiable**: All 3 smoke tests pass; output matches expectations

---

## Phase 5: Unit Testing (7 tasks)

**Goal**: Test E7 detection logic with mocks, ensuring pattern matching and error handling work.

- [ ] **5.1** Create `tests/unit/test_e7_detection.py` with TestE7ResultSchema test class
  - Import: `import pytest` and `from models.schemas import E7Result`
  - Create test class: `class TestE7ResultSchema:`
  - Add test fixtures if needed (mock E7Result data)
  - **Verifiable**: Test file exists, pytest discovers it, basic structure in place

- [ ] **5.2** Test E7Result Pydantic schema validation
  - Test **valid input**: `E7Result(js_price_requests=[], infinite_scroll_pattern="cursor", estimated_products=100, cart_endpoints=["https://api.example.com/cart"], browser_execution_time_ms=5000, confidence="high")` succeeds
  - Test **optional fields**: `E7Result(js_price_requests=None, infinite_scroll_pattern=None, estimated_products=None, cart_endpoints=None, browser_execution_time_ms=1000, confidence="low")` succeeds (all optionals are None)
  - Test **invalid confidence**: `E7Result(..., confidence="invalid")` raises Pydantic ValidationError
  - Test **invalid pattern**: `E7Result(..., infinite_scroll_pattern="invalid")` raises Pydantic ValidationError
  - Test **missing required field**: `E7Result(confidence="high")` (missing browser_execution_time_ms) raises ValidationError
  - Add 5+ test methods covering above scenarios
  - **Verifiable**: All test methods pass; coverage >= 90% for E7Result validation

- [ ] **5.3** Test XHR pattern matching logic
  - Create test class `class TestXhrPatternMatching:` in same file
  - Mock request objects with `.url` and `.method` attributes
  - Test **price pattern matching**: Request URL "/api/price/123" matches pattern `r"/api/price"`
  - Test **pagination pattern matching**: URL "/api/products?offset=0" matches `r"/api/products"`
  - Test **cart pattern matching**: URL "/api/cart/add" matches `r"/cart/add"`
  - Test **no match**: URL "/static/image.png" does NOT match price/pagination/cart patterns
  - Test **false positive prevention**: URL "/api/pricing-info" does NOT match `/api/price` (regex boundary check needed)
  - Test **case sensitivity**: URL "/API/PRICE" (uppercase) should NOT match `/api/price`
  - Add 6+ test methods
  - **Verifiable**: Pattern matching tests pass; false positive rate = 0%

- [ ] **5.4** Test timeout handling and graceful degradation
  - Create test class `class TestTimeoutHandling:` in same file
  - Mock `_detect_deep_ecommerce()` to raise `asyncio.TimeoutError` after 3s
  - Test: Function catches TimeoutError and returns None (not crash)
  - Test: Warning logged with message containing "timeout"
  - Test: browser.close() is called (even on timeout)
  - Add 3+ test methods
  - **Verifiable**: Timeout tests pass; no unhandled exceptions

- [ ] **5.5** Test error handling (PlaywrightException, generic Exception)
  - Create test class `class TestErrorHandling:` in same file
  - Mock `_detect_deep_ecommerce()` to raise `PlaywrightException("Browser crash")`
  - Test: Function catches PlaywrightException, returns None, warning logged
  - Mock to raise generic `Exception("Unexpected error")`
  - Test: Function catches generic Exception, returns None, exception logged
  - Verify browser cleanup still occurs
  - Add 4+ test methods
  - **Verifiable**: Error handling tests pass; browser cleanup verified

- [ ] **5.6** Test decision gate logic (precondition checks)
  - Create test class `class TestDecisionGate:` in same file
  - Mock classifier.type = STATIC, e7 should skip (return None immediately)
  - Mock classifier.type = DYNAMIC, is_ecommerce = False, e7 should skip
  - Mock config.deep = False, e7 should skip even on DYNAMIC + ecommerce
  - Mock classifier.type = DYNAMIC, is_ecommerce = True, config.deep = True → proceed (would call browser, mock browser call)
  - Add 4+ test methods
  - **Verifiable**: Decision gate tests pass; correct conditionals verified

- [ ] **5.7** Test graceful Playwright unavailability
  - Create test class `class TestPlaywrightAvailability:` in same file
  - Mock `from playwright.async_api import async_playwright` to raise ImportError
  - Test: `_detect_deep_ecommerce()` catches ImportError, logs warning, returns None
  - Verify scan continues without crashing
  - Add 2+ test methods
  - **Verifiable**: Playwright unavailability tests pass; no import exceptions reach caller

---

## Phase 6: Integration Testing (7 tasks)

**Goal**: Test E7 detection within the full pipeline using mocks.

- [ ] **6.1** Create `tests/integration/test_e7_pipeline.py` with TestE7PipelineIntegration test class
  - Import necessary modules: `pytest`, `AsyncMock`, `unittest.mock`, schemas, classifier
  - Create test class: `class TestE7PipelineIntegration:`
  - Add pytest asyncio marker: `@pytest.mark.asyncio`
  - **Verifiable**: Test file exists, pytest discovers it, async tests work

- [ ] **6.2** Test classifier → decision gate → E7 detection flow (mock Playwright)
  - Create test: `async def test_dynamic_ecommerce_triggers_e7():`
  - Mock classifier result with type=DYNAMIC, is_ecommerce=True
  - Mock config with deep=True
  - Mock `_detect_deep_ecommerce()` to return valid E7Result
  - Call decision gate logic from main.py (or simulate it)
  - Verify: E7 invoked with correct URL/timeout
  - Verify: E7 result stored in classifier.ecommerce.e7_deep_mode
  - Add test: `async def test_static_site_skips_e7():`
  - Mock classifier result with type=STATIC
  - Verify: E7 NOT invoked
  - Add 4+ test methods
  - **Verifiable**: Pipeline flow tests pass; mocks called correctly

- [ ] **6.3** Test E7Result integration with EcommerceSignals
  - Create test: `async def test_e7_result_stored_in_ecommerce_signals():`
  - Create E7Result with sample data
  - Create EcommerceSignals with e7_deep_mode=E7Result
  - Verify all fields accessible: `signals.e7_deep_mode.js_price_requests`, etc.
  - Verify JSON serialization works (for report export)
  - Add 3+ test methods
  - **Verifiable**: Integration tests pass; E7Result properly stored and serialized

- [ ] **6.4** Test recommender handling of E7Result (with and without)
  - Create test: `async def test_recommender_with_e7_data():`
  - Mock full scan_result with e7_deep_mode populated
  - Call `build_recommendation(scan_result)`
  - Verify: recommender doesn't crash
  - Verify: if E7 has meaningful data, confidence/suggestions improve (optional)
  - Create test: `async def test_recommender_without_e7_data():`
  - Mock full scan_result with e7_deep_mode=None
  - Call `build_recommendation(scan_result)`
  - Verify: recommender doesn't crash, behaves as E1-E6 only
  - Add 4+ test methods
  - **Verifiable**: Recommender tests pass both with/without E7

- [ ] **6.5** Test STATIC site with --deep: E7 skipped, E1-E6 unaffected
  - Create test: `async def test_static_site_deep_flag_e7_skipped():`
  - Mock full scan on STATIC site (e.g., HTML-only WordPress blog)
  - Set config.deep=True
  - Call _run_scan()
  - Verify: classifier.type = STATIC
  - Verify: E7 NOT called (no Playwright)
  - Verify: e7_deep_mode = None
  - Verify: E1-E6 results populated normally
  - Verify: total scan time < 15s (no Playwright overhead)
  - Add 2+ test methods
  - **Verifiable**: STATIC site tests pass; E7 skipped correctly

- [ ] **6.6** Test DYNAMIC site without --deep: E7 skipped, config respected
  - Create test: `async def test_dynamic_site_without_deep_flag():`
  - Mock full scan on DYNAMIC site (e.g., React SPA)
  - Set config.deep=False (default)
  - Call _run_scan()
  - Verify: classifier.type = DYNAMIC
  - Verify: E7 NOT called (deep flag not set)
  - Verify: e7_deep_mode = None
  - Verify: E1-E6 results populated normally
  - Add 2+ test methods
  - **Verifiable**: Deep flag respected; E7 skipped when not requested

- [ ] **6.7** Optional: Real Playwright integration test (skip by default, opt-in only)
  - Create test: `@pytest.mark.slow` `async def test_e7_real_playwright_buscalibre():`
  - Use real URL (e.g., https://buscalibre.cl)
  - Call actual `_detect_deep_ecommerce(url, timeout=10.0, config)`
  - Verify: E7Result populated with real XHR data
  - Verify: js_price_requests, cart_endpoints, pagination detected
  - Verify: total execution < 10s
  - Add note: "Run with: pytest -m slow tests/integration/test_e7_pipeline.py"
  - Add 1 slow test (optional)
  - **Verifiable**: Real Playwright test passes (when run with -m slow); validates against real site

---

## Phase 7: Validation & Bug Fixes (6 tasks)

**Goal**: Smoke test on real sites, fix bugs, validate coverage.

- [ ] **7.1** Run full test suite with coverage report
  - Command: `make test` (or `pytest tests/unit tests/integration -v --cov=modules --cov=models --cov=utils --cov-report=term-missing`)
  - Verify: All tests pass (100% on new code in E7 modules)
  - Verify: Coverage >= 86% (project minimum)
  - Verify: No warnings or deprecations
  - Record test output
  - **Verifiable**: Test output shows all tests passing, coverage >= 86%

- [ ] **7.2** Smoke test: DYNAMIC e-commerce with --deep flag
  - Command: `python main.py --url https://buscalibre.cl --deep --json -o /tmp/e7_smoke.json`
  - Expected: Scan completes in 20-30s (Phase 1 + E7 + Phase 3)
  - Verify: Report includes E7 section with non-empty results
  - Verify: js_price_requests, infinite_scroll_pattern, cart_endpoints populated
  - Verify: confidence level set (high/medium/low)
  - Verify: recommender uses E7 data (if recommender logic updated)
  - Record output and verify manually
  - **Verifiable**: Smoke test passes; E7 data meaningful and present

- [ ] **7.3** Smoke test: STATIC site with --deep flag (no overhead)
  - Command: `python main.py --url https://example.com --deep --json -o /tmp/static_smoke.json`
  - Expected: Scan completes in < 15s (E7 skipped)
  - Verify: classifier.type = STATIC (or similar)
  - Verify: e7_deep_mode = None in output
  - Verify: E1-E6 results normal
  - Verify: No Playwright browser window opened
  - **Verifiable**: STATIC smoke test passes; E7 skipped, no overhead

- [ ] **7.4** Smoke test: Real DYNAMIC sites (2-3 e-commerce targets)
  - Pick 3 real sites (e.g., buscalibre.cl, mercadolibre.com, another retail site)
  - Command: `python main.py --url <url> --deep` for each
  - Verify: No crashes, all scans complete
  - Verify: E7 data populated (or gracefully None if Playwright fails)
  - Verify: Recommender produces sensible suggestions
  - Record outputs and scan times
  - **Verifiable**: 3 real-site smoke tests pass without crashes

- [ ] **7.5** Fix any test failures or bugs discovered in validation
  - If any tests fail in 7.1-7.4, debug and fix:
    - PatternMatching issue: fix regex patterns
    - Timeout issue: adjust window timeouts or increase total budget
    - Playwright initialization issue: verify Playwright binary installed
    - Recommender integration issue: verify E7Result fields accessible
  - Re-run tests after each fix
  - Document fixes in commit message
  - **Verifiable**: All tests pass; all smoke tests succeed

- [ ] **7.6** Verify git status clean and BACKLOG.md updated
  - Command: `git status`
  - Verify: Only expected files modified (schemas.py, classifier.py, main.py, pytest outputs)
  - Verify: No untracked files (except __pycache__, .pytest_cache)
  - Verify: BACKLOG.md updated to mark Phase 3 COMPLETE (see Phase 8.1)
  - **Verifiable**: git status clean; BACKLOG reflects Phase 3 done

---

## Phase 8: Documentation & Cleanup (4 tasks)

**Goal**: Document work, clean up code, prepare for merge.

- [ ] **8.1** Update `docs/BACKLOG.md` to mark Phase 3 E7 as complete
  - Open docs/BACKLOG.md
  - Locate Phase 3 E7 section (lines ~48-70)
  - Change status: `- [x] Phase 3: E7 Deep Mode (Playwright XHR interception)` ← mark complete
  - Update module line counts (if tracked):
    - `classifier.py`: +~150 lines (E7 detection function)
    - `utils/playwright_helper.py`: +~200 lines (new file)
    - `models/schemas.py`: +~30 lines (E7Result + extension)
    - `main.py`: +~15 lines (E7 invocation gate)
  - Add note: "✅ Completed 2026-05-14: XHR interception, 3 observation windows, full test coverage (43 tasks)"
  - **Verifiable**: BACKLOG.md updated; Phase 3 marked complete with line counts

- [ ] **8.2** Add comprehensive docstrings to all new functions
  - `E7Result` class docstring: Describes deep-mode runtime detection, fields, confidence scoring
  - `_detect_deep_ecommerce()` docstring: Explains args, returns, error handling, usage example (from design spec)
  - `get_browser_context()` docstring: Context manager lifecycle, timeout, usage
  - `setup_xhr_interception()` docstring: Pattern matching, captured data structure, privacy notes
  - `scroll_page_to_bottom()` docstring: Scroll behavior, return value, timeout handling
  - `find_and_click_cart_button()` docstring: Button discovery, gentle mode, return value
  - All docstrings follow project convention (NumPy/Google style or as-is)
  - **Verifiable**: Each new function has docstring; `python -m pydoc modules.classifier._detect_deep_ecommerce` produces output

- [ ] **8.3** Ensure imports are clean and no unused imports exist
  - Review `modules/classifier.py`: All imports used, no duplicates, correct relative imports
  - Review `utils/playwright_helper.py`: All imports used, no duplicates
  - Review `models/schemas.py`: All imports used, no duplicates
  - Run `python -m py_compile models/schemas.py modules/classifier.py utils/playwright_helper.py` to check syntax
  - Run linter if available: `flake8 --max-line-length=120` (or project-specific linter)
  - **Verifiable**: No unused imports; py_compile succeeds; linter (if run) shows no warnings

- [ ] **8.4** Create final commit with comprehensive message
  - Stage files: `git add models/schemas.py modules/classifier.py utils/playwright_helper.py main.py docs/BACKLOG.md tests/unit/test_e7_detection.py tests/integration/test_e7_pipeline.py`
  - Commit message (multi-line):
    ```
    feat: Phase 3 — E7 deep mode Playwright XHR interception for JS price, infinite scroll, cart detection
    
    - Add E7Result schema with js_price_requests, infinite_scroll_pattern, cart_endpoints
    - Extend EcommerceSignals with optional e7_deep_mode field
    - Implement _detect_deep_ecommerce() with 3 observation windows (price JS, infinite scroll, cart)
    - Create utils/playwright_helper.py for browser lifecycle and XHR route interception
    - Conditional execution: only run on DYNAMIC/HYBRID sites with --deep flag
    - Graceful error handling: returns None on Playwright unavailable, timeout, or crash
    - Full test coverage: 43 tasks, unit + integration tests, 3 real-site smoke tests
    - BACKLOG.md updated; Phase 3 complete
    ```
  - Push: `git push origin main` (or create PR if workflow requires)
  - **Verifiable**: Commit appears in git log with proper message; CI passes (if applicable)

---

## Task Summary by Phase

| Phase | Tasks | Focus | Estimated Time |
|-------|-------|-------|-----------------|
| 1 | 3 | Schemas & types (foundation) | 15 min |
| 2 | 5 | Playwright helper (infrastructure) | 45 min |
| 3 | 7 | E7 detection (core logic) | 60 min |
| 4 | 4 | Pipeline integration (wiring) | 30 min |
| 5 | 7 | Unit testing (TDD validation) | 75 min |
| 6 | 7 | Integration testing (pipeline) | 60 min |
| 7 | 6 | Validation & bug fixes | 45 min |
| 8 | 4 | Documentation & cleanup | 20 min |
| **Total** | **43** | **Full implementation** | **~5 hours** |

---

## Implementation Notes

### Order of Execution

1. **Phase 1** (Schemas) → creates foundation for all downstream code
2. **Phase 2** (Playwright helpers) → infrastructure ready before Phase 3
3. **Phase 3** (E7 detection) → core logic implemented and testable
4. **Phases 5-6** (Testing) → TDD-style: tests validate Phase 3 before Phase 4
5. **Phase 4** (Pipeline integration) → wire after testing passes
6. **Phase 7** (Validation) → smoke tests on real sites
7. **Phase 8** (Cleanup) → final documentation and commit

### Verification Checklist

After completing all 43 tasks:

- [ ] All unit tests pass (test_e7_detection.py)
- [ ] All integration tests pass (test_e7_pipeline.py)
- [ ] Coverage >= 86%
- [ ] 3 real-site smoke tests pass
- [ ] BACKLOG.md updated
- [ ] All docstrings present
- [ ] No unused imports
- [ ] git status clean
- [ ] Commit pushed

### Known Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| Playwright installation fails | Graceful None return; E1-E6 still work |
| Browser initialization slow (5s+) | Total timeout 10s is acceptable; user can adjust |
| XHR patterns miss API endpoints | Pattern list extensible; test with real sites |
| Session/auth required for cart probe | Currently ignores auth; future improvement |
| Rate limiting on rapid scrolls | No backoff currently; acceptable for initial phase |

---

**Status**: Ready for sdd-apply implementation  
**Next**: Orchestrator will present summary and ask to begin Phase 1.

