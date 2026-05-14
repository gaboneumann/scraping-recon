# Tasks: Phase 2 — E-Commerce Depth Features (E2-E6)

**Document Status**: READY FOR IMPLEMENTATION  
**Date**: 2026-05-14  
**Topic Key**: `sdd/Phase 2 — E-Commerce Depth Features (E2-E6)/tasks`

Total Tasks: **48 across 8 phases**  
Estimated Duration: **16-24 hours** (spread across 2 weeks)  
Dependencies: Design complete ✅ | Specifications complete ✅

---

## Phase 1: Schema Foundation (Dependency layer)

**Duration**: ~1-2 hours  
**Blocking**: All downstream phases  
**Files**: `models/schemas.py`

- [ ] **1.1** Add `SearchApiResult` Pydantic class to `models/schemas.py` (after line 67, before `PdpSampleResult`)
  - Fields: `found: bool`, `type: str | None` (Algolia, Elasticsearch, Custom), `endpoint: str | None`, `authenticated: bool | None`, `confidence: str`
  - **Verification**: Class exists with all fields; can be imported without errors

- [ ] **1.2** Add `VariantInfo` Pydantic class to `models/schemas.py` (after `SearchApiResult`)
  - Fields: `selector_type: str | None` (dropdown, radio, swatch, button), `has_ajax: bool`, `ajax_endpoint: str | None`, `variant_count_estimate: int | None`, `confidence: str`
  - **Verification**: Class exists and serializes correctly; test with variant HTML

- [ ] **1.3** Add `InventoryInfo` Pydantic class to `models/schemas.py` (after `VariantInfo`)
  - Fields: `mechanism: Literal["SERVER_SIDE", "AJAX", "UNKNOWN"]`, `stock_element_found: bool`, `update_pattern: str | None`, `real_time: bool`
  - **Verification**: Class exists with all fields; backward compatibility

- [ ] **1.4** Add `ReviewsProviderInfo` Pydantic class to `models/schemas.py` (after `InventoryInfo`)
  - Fields: `provider: str | None` (Bazaarvoice, Yotpo, Trustpilot, eKomi, Google, Internal, None), `found: bool`, `api_endpoint: str | None`, `widget_script_found: bool`
  - **Verification**: Class exists; can parse real reviews HTML fixtures

- [ ] **1.5** Extend `EcommerceSignals` class (line 56-66) with E2-E6 fields
  - Add after `price_reliability_score` (line 62):
    - E2: `search_api: SearchApiResult | None = None`
    - E3: `variants: VariantInfo | None = None`
    - E5: `reviews_provider: ReviewsProviderInfo | None = None`
    - E6: `inventory: InventoryInfo | None = None`
  - **Verification**: Schema validates; old code reading EcommerceSignals still works (fields are optional)

- [ ] **1.6** Extend `ClassifierResult` class (line 80-101) with E4 fields
  - Add new fields after `pdp_sample` (line 101):
    - `pdp_samples: list[PdpSampleResult] = []` (list instead of single)
    - `pdp_consistency: dict[str, float] = {}` (metrics: "matching_waf_headers_pct", "render_mode_agreement", "error_rate")
  - Keep `pdp_sample` for backward compatibility (populate from `pdp_samples[0]` if available)
  - **Verification**: Schema migration backward compatible; existing code reading `pdp_sample` still works

- [ ] **1.7** Run schema validation test
  - Execute: `python -c "from models.schemas import SearchApiResult, VariantInfo, InventoryInfo, ReviewsProviderInfo; print('Schema import OK')"`
  - **Verification**: All imports succeed without errors

---

## Phase 2: Variant Detection (Static, E3)

**Duration**: ~2-3 hours  
**Blocking**: E3 integration test  
**Files**: `modules/classifier.py`

- [ ] **2.1** Implement `_detect_variants()` helper function in `classifier.py` (after line 400, before `_detect_ecommerce_signals()`)
  - **Signature**: `def _detect_variants(soup: BeautifulSoup) -> VariantInfo`
  - **Logic**:
    - Scan for dropdown selects: `select[name*="variant"], select[name*="option"]` → type="dropdown"
    - Scan for radio buttons: `input[type="radio"][name*="variant"]` → type="radio"
    - Scan for swatch selectors: `div[class*="swatch"]` or `div[data-swatch]` → type="swatch"
    - Scan for button options: `button[data-variant-id]` → type="button"
    - If found: estimate variant count from option count or data attributes
    - Check for AJAX: scan script tags for `/variant|/option|/swatch` endpoint patterns
  - **Return**: VariantInfo with confidence (HIGH/MEDIUM/LOW)
  - **Verification**: Test with 6 fixtures (dropdown, radio, swatch, button, multiple types, none)

- [ ] **2.2** Add `_variant_patterns` regex dict to top of `classifier.py` (near line 72, with other signal dicts)
  - Patterns for: `selector_dropdown`, `selector_radio`, `selector_swatch`, `selector_button`, `ajax_endpoint`
  - **Example**:
    ```python
    _VARIANT_PATTERNS = {
        "selector_dropdown": r'<select\s+[^>]*(?:name|id)="[^"]*(?:variant|option)',
        "selector_radio": r'<input\s+type="radio"[^>]*(?:name|id)="[^"]*(?:variant|option)',
        "selector_swatch": r'<(?:div|span)[^>]*(?:class|data-swatch)="[^"]*swatch',
        "ajax_endpoint": r'(?:POST|GET)\s+[\'"](?:/api)?/(?:variants?|options?|swatches)',
    }
    ```
  - **Verification**: Regex patterns match expected HTML snippets

- [ ] **2.3** Implement `_detect_inventory_mechanism()` helper in `classifier.py`
  - **Signature**: `def _detect_inventory_mechanism(html: str, soup: BeautifulSoup) -> InventoryInfo`
  - **Logic**:
    - Check for server-side stock: `data-stock`, `data-inventory`, hardcoded numbers in stock element
    - Check for AJAX updates: regex for `setInterval`, `updateInventory`, `fetch.*inventory` patterns
    - Compute confidence based on match quality (HIGH=clear pattern, LOW=ambiguous)
  - **Return**: InventoryInfo with mechanism type
  - **Verification**: Distinguish server-side vs AJAX HTML fixtures

- [ ] **2.4** Implement `_detect_reviews_provider()` helper in `classifier.py`
  - **Signature**: `def _detect_reviews_provider(soup: BeautifulSoup, html: str) -> ReviewsProviderInfo`
  - **Logic**:
    - Scan script tags for: `bv`, `Bazaarvoice`, `bvApi` → provider="Bazaarvoice"
    - Scan script tags for: `yotpo`, `YotpoReviews` → provider="Yotpo"
    - Scan script tags for: `trustpilot` → provider="Trustpilot"
    - Scan script tags for: `ekomi`, `eKomiIntegration` → provider="eKomi"
    - Scan script tags for: `google.*reviews|GoogleCustomerReviews` → provider="Google"
    - If no external provider found, check for internal review divs → provider="Internal"
  - **Return**: ReviewsProviderInfo with provider name and confidence
  - **Verification**: Correctly identify 6 provider types from fixtures

- [ ] **2.5** Integrate E3, E5, E6 into `_detect_ecommerce_signals()` (line ~320)
  - Add calls to new helper functions after existing `price_mechanism` detection:
    ```python
    ecommerce_signals.variants = _detect_variants(soup)
    ecommerce_signals.reviews_provider = _detect_reviews_provider(soup, html)
    ecommerce_signals.inventory = _detect_inventory_mechanism(html, soup)
    ```
  - **Verification**: No breaking changes to existing logic; fields populate correctly

---

## Phase 3: Multi-PDP Sampling (Static + HTTP, E4)

**Duration**: ~3-4 hours  
**Blocking**: Consistency metrics tests  
**Files**: `modules/classifier.py`

- [ ] **3.1** Refactor `_fetch_pdp_sample()` → `_fetch_pdp_samples()` signature change
  - **Old signature** (line ~380): `async def _fetch_pdp_sample(url: str, timeout: float) -> PdpSampleResult | None`
  - **New signature**: `async def _fetch_pdp_samples(url: str, timeout: float, sample_count: int = 2) -> list[PdpSampleResult]`
  - Maintain backward compatibility: internal calls can still use old name as wrapper if needed
  - **Verification**: Function signature updated; old call sites still work

- [ ] **3.2** Implement product link extraction in `_fetch_pdp_samples()`
  - Fetch category page HTML (reuse from classifier)
  - Extract all product links using `_pdp_pattern()` (existing function)
  - If count < 2: return single sample (not enough products to sample)
  - If count >= 2: random.sample(links, min(sample_count, count))
  - **Verification**: Extract 2-3 links from test fixtures correctly

- [ ] **3.3** Implement parallel fetching for multiple PDP URLs
  - Use `asyncio.gather()` to fetch 2-3 samples concurrently
  - Set timeout per request: `timeout / sample_count` (fair allocation)
  - Collect results in list; skip failed requests
  - **Verification**: Fetch multiple URLs in parallel without timeout errors

- [ ] **3.4** Compute consistency metrics
  - **matching_waf_headers_pct**: % of samples with same WAF headers as category fetch
  - **render_mode_agreement**: % of samples with same render mode (SERVER_SIDE vs CLIENT_SIDE)
  - **error_rate**: (failed_samples / total_samples) * 100
  - Store in `pdp_consistency` dict in ClassifierResult
  - **Verification**: Metrics computed correctly for test data (100% match = same headers, 0% = all different)

- [ ] **3.5** Update `classify_page()` to call `_fetch_pdp_samples()`
  - Replace call to `_fetch_pdp_sample()` (if exists) with new function
  - Populate both `classifier_result.pdp_sample` (from pdp_samples[0]) and `classifier_result.pdp_samples` (full list)
  - **Verification**: No regression; pdp_sample still populated for backward compatibility

---

## Phase 4: Search API Detection (HTTP, E2)

**Duration**: ~2-3 hours  
**Blocking**: E2 integration test  
**Files**: `modules/api_detector.py`

- [ ] **4.1** Implement `_detect_search_api()` function in `api_detector.py` (new function after existing helpers)
  - **Signature**: `async def _detect_search_api(html: str, endpoints: list[ApiEndpoint], base_url: str, timeout: float) -> SearchApiResult`
  - **Logic**:
    - Pattern match HTML for Algolia: `algoliasearch`, `algolia.com`, `AA.*INDEX_NAME`
    - Pattern match for Elasticsearch: `elasticsearch`, `kibana`, `_search endpoint`
    - Pattern match for custom API: `/api/search`, `/api/products`, `/api/catalog`
    - Use provided `endpoints` list from api_detector output
  - **Return**: SearchApiResult with found=True/False, type, endpoint URL, confidence
  - **Verification**: Identify Algolia, Elasticsearch, custom APIs from HTML

- [ ] **4.2** Implement optional HTTP probe for search API endpoint
  - If endpoint found AND looks valid (not localhost, not example.com):
    - Construct test query: `?q=test` or `?search=test` or JSON body
    - Make single GET/POST request (max 1 HTTP request)
    - Check response status (200 = working, 403/401 = auth required, 404 = invalid)
  - Update `authenticated` and `found` fields based on probe result
  - **Verification**: Probe works for valid endpoints; skips invalid ones

- [ ] **4.3** Integrate `_detect_search_api()` into `_detect_apis()` function
  - Call after existing endpoint detection:
    ```python
    if classifier_result.ecommerce and classifier_result.ecommerce.is_ecommerce:
        search_result = await _detect_search_api(html, endpoints, base_url, timeout)
        if classifier_result.ecommerce:
            classifier_result.ecommerce.search_api = search_result
    ```
  - **Verification**: Search API result populates EcommerceSignals.search_api field

- [ ] **4.4** Add E2 to HTTP budget tracking
  - Update budget check: antibot module adds 5-6 requests max (was 12, can spare)
  - Total: 27 + 5 = 32 requests (new budget ceiling)
  - Document in code comment
  - **Verification**: Total request count <= 32 in full scan

---

## Phase 5: Unit Tests — Detection Functions

**Duration**: ~6-8 hours  
**Blocking**: None (can run in parallel)  
**Files**: `tests/unit/test_*.py`

- [ ] **5.1** Create `tests/unit/test_classifier_variants.py` — variant detection
  - **Test cases** (10 total):
    - `test_variants_dropdown_single` — dropdown with 3 options
    - `test_variants_dropdown_multiple` — multiple dropdown selectors
    - `test_variants_radio_buttons` — radio button options
    - `test_variants_swatch_colors` — swatch/color selectors
    - `test_variants_button_options` — button-based variant selection
    - `test_variants_with_ajax` — variant selector + AJAX endpoint in script
    - `test_variants_no_selector` — HTML with no variant indicators
    - `test_variants_low_confidence` — ambiguous selector patterns
    - `test_variants_estimate_count` — variant count estimation
    - `test_variants_mixed_types` — multiple selector types in one page
  - **Fixtures**: Use `tests/fixtures/` HTML files
  - **Verification**: Each test passes; coverage >= 90%

- [ ] **5.2** Create `tests/unit/test_classifier_reviews_provider.py` — reviews provider detection
  - **Test cases** (8 total):
    - `test_reviews_bazaarvoice` — Bazaarvoice widget detection
    - `test_reviews_yotpo` — Yotpo reviews detection
    - `test_reviews_trustpilot` — Trustpilot widget detection
    - `test_reviews_ekomi` — eKomi reviews detection
    - `test_reviews_google` — Google reviews detection
    - `test_reviews_internal` — Internal reviews div detection
    - `test_reviews_no_provider` — Page with no reviews
    - `test_reviews_multiple_providers` — Multiple widgets present (return primary)
  - **Verification**: Correctly identify all 6 provider types

- [ ] **5.3** Create `tests/unit/test_classifier_inventory.py` — inventory mechanism detection
  - **Test cases** (10 total):
    - `test_inventory_server_side_data_attr` — stock in data-stock attribute
    - `test_inventory_server_side_hardcoded` — hardcoded stock number in HTML
    - `test_inventory_ajax_via_setinterval` — AJAX detected via setInterval pattern
    - `test_inventory_ajax_via_fetch` — AJAX detected via fetch pattern
    - `test_inventory_ajax_endpoint_in_script` — AJAX endpoint in script tag
    - `test_inventory_high_confidence_match` — clear mechanism with high confidence
    - `test_inventory_low_confidence` — ambiguous signals
    - `test_inventory_unknown_mechanism` — No stock indicators
    - `test_inventory_real_time_flag` — Real-time stock update detection
    - `test_inventory_backorder_signals` — Backorder/preorder detection
  - **Verification**: Distinguish server-side vs AJAX correctly

- [ ] **5.4** Create `tests/unit/test_api_detector_search_api.py` — search API detection
  - **Test cases** (10 total):
    - `test_search_api_algolia_detection` — Algolia script/config found
    - `test_search_api_elasticsearch_detection` — Elasticsearch endpoint detected
    - `test_search_api_custom_endpoint` — /api/search endpoint pattern
    - `test_search_api_with_endpoint_list` — Use provided endpoints list
    - `test_search_api_not_found` — No search API indicators
    - `test_search_api_authenticated` — Endpoint requires auth (403)
    - `test_search_api_endpoint_validation` — Skip localhost, example.com
    - `test_search_api_confidence_high` — Clear pattern match
    - `test_search_api_confidence_low` — Ambiguous indicators
    - `test_search_api_multiple_types` — Multiple search APIs (return primary)
  - **Verification**: Identify all 3 search API types

- [ ] **5.5** Create `tests/unit/test_classifier_multi_pdp.py` — multi-sample PDP logic
  - **Test cases** (8 total):
    - `test_pdp_samples_extract_multiple_links` — Extract 2-3 product links
    - `test_pdp_samples_insufficient_products` — < 2 products returns single sample
    - `test_pdp_samples_parallel_fetch` — Fetch samples concurrently
    - `test_pdp_samples_consistency_matching_headers` — 100% matching WAF headers
    - `test_pdp_samples_consistency_varying_headers` — Different WAF headers across samples
    - `test_pdp_samples_render_mode_agreement` — All SERVER_SIDE or all CLIENT_SIDE
    - `test_pdp_samples_error_handling` — Handle failed fetches gracefully
    - `test_pdp_samples_backward_compat_pdp_sample` — pdp_sample field still populated
  - **Verification**: Consistency metrics computed correctly

- [ ] **5.6** Run unit test suite for Phase 2
  - Execute: `venv/bin/pytest tests/unit/test_classifier_*.py tests/unit/test_api_detector_*.py -v --cov --cov-report=term-missing`
  - **Verification**: All tests pass; coverage >= 86%; no regression in existing tests

---

## Phase 6: Fixtures & Integration Setup

**Duration**: ~2-3 hours  
**Blocking**: Integration tests  
**Files**: `tests/fixtures/`

- [ ] **6.1** Create `tests/fixtures/woocommerce_pdp_variants.html`
  - HTML with WooCommerce product page (variants)
  - Include: size/color dropdowns, data-product-id, price in HTML
  - Expected detections: variants=DROPDOWN, inventory=SERVER_SIDE
  - **Verification**: File exists; fixtures can parse it

- [ ] **6.2** Create `tests/fixtures/shopify_pdp_swatch.html`
  - HTML with Shopify product page (color swatches)
  - Include: div.swatch elements, color buttons, variant AJAX endpoint
  - Expected detections: variants=SWATCH with AJAX
  - **Verification**: File exists; swatch detection works

- [ ] **6.3** Create `tests/fixtures/bazaarvoice_reviews.html`
  - HTML with Bazaarvoice widget embedded
  - Include: script tag with bvApi, review container, star ratings
  - Expected detections: reviews_provider=Bazaarvoice
  - **Verification**: File exists; Bazaarvoice detection works

- [ ] **6.4** Create `tests/fixtures/yotpo_reviews.html`
  - HTML with Yotpo reviews widget
  - Include: yotpo script tag, reviews container, rating display
  - Expected detections: reviews_provider=Yotpo
  - **Verification**: File exists; Yotpo detection works

- [ ] **6.5** Create `tests/fixtures/ajax_inventory.html`
  - HTML with AJAX-based inventory updates
  - Include: setInterval pattern, fetch pattern, no hardcoded stock
  - Expected detections: inventory=AJAX with real_time=True
  - **Verification**: File exists; AJAX detection works

- [ ] **6.6** Create `tests/fixtures/server_side_inventory.html`
  - HTML with server-side stock numbers
  - Include: hardcoded stock count, data-inventory attribute, no AJAX scripts
  - Expected detections: inventory=SERVER_SIDE
  - **Verification**: File exists; server-side detection works

---

## Phase 7: Integration & Smoke Tests

**Duration**: ~4-5 hours  
**Blocking**: Release  
**Files**: `tests/integration/test_e2e_*.py`, CLI

- [ ] **7.1** Create `tests/integration/test_e2e_ecommerce_depth.py`
  - Integration test: full `classify_page()` pipeline with E2-E6 enabled
  - Use WooCommerce + Shopify fixtures
  - **Test cases** (6 total):
    - `test_full_woocommerce_signals` — All e-commerce signals detected
    - `test_full_shopify_signals` — Shopify-specific signals
    - `test_ecommerce_signals_populated` — EcommerceSignals has E2-E6 fields
    - `test_classifier_result_includes_e4` — pdp_samples and pdp_consistency populated
    - `test_api_detector_search_api_integrated` — search_api field in EcommerceSignals
    - `test_no_regression_existing_fields` — Old fields (price_mechanism, etc.) still work
  - **Verification**: All tests pass; no regression

- [ ] **7.2** Run full test suite: `make test`
  - Execute: `pytest tests/ -v --cov=modules --cov=models --cov-report=term-missing`
  - **Verification**: 
    - All 300+ tests pass
    - Coverage >= 86% (same as E1)
    - No new warnings or errors

- [ ] **7.3** Smoke test on real e-commerce sites
  - Test URLs:
    - `python main.py --url https://www.buscalibre.cl/libros --module classifier --json`
    - `python main.py --url https://www.mercadolibre.cl --module classifier --json`
    - `https://www.amazon.com --module classifier` (if accessible)
  - **Verification**:
    - E2-E6 fields present in output
    - No errors or timeouts
    - HTTP request count <= 32

- [ ] **7.4** Validate HTTP request budget
  - Add counter in `utils/http.py` to track requests
  - Run full scan on test URL
  - Assert total requests <= 32
  - **Verification**: Budget respected; no excess requests

- [ ] **7.5** Update BACKLOG.md — mark E2-E6 as COMPLETE
  - Change status from "Phase 2: Under Exploration" to "✅ Phase 2: COMPLETE"
  - Update lines for E2, E3, E4, E5, E6 (mark as ✅)
  - Update test count (now 300+ tests expected)
  - Update coverage (should still be >= 86%)
  - **Verification**: File updated; no missing checkmarks

---

## Phase 8: Documentation & Polish

**Duration**: ~1-2 hours  
**Blocking**: Release  
**Files**: Various docs

- [ ] **8.1** Add docstrings to new functions in `classifier.py`
  - All new functions need full docstrings:
    - `_detect_variants(soup)` — describe variant detection logic
    - `_detect_reviews_provider(soup, html)` — describe provider detection
    - `_detect_inventory_mechanism(html, soup)` — describe mechanism detection
    - `_fetch_pdp_samples(url, timeout, sample_count)` — describe multi-sampling
  - All Pydantic classes in `models/schemas.py` need docstrings
  - **Verification**: All public functions have docstrings; no missing descriptions

- [ ] **8.2** Add docstrings to `_detect_search_api()` in `api_detector.py`
  - Function docstring with logic description
  - Parameter descriptions
  - Return value documentation
  - **Verification**: Docstring is complete and accurate

- [ ] **8.3** Update `report/terminal.py` to display E2-E6 signals (optional)
  - Add section for e-commerce depth signals (optional: inline with E1 or separate section)
  - Display: variants info, reviews provider, inventory mechanism, search API, multi-PDP consistency
  - **Verification**: Terminal output includes all E2-E6 signals

- [ ] **8.4** Update `README.md` or `docs/` with E2-E6 feature descriptions
  - Add section under "E-Commerce Detection" (or create new section)
  - Describe what each signal (E2-E6) detects and why it matters
  - Include example output
  - **Verification**: Documentation is clear and up-to-date

- [ ] **8.5** Test backward compatibility
  - Verify old code reading `EcommerceSignals` without E2-E6 fields still works
  - Verify old code reading `pdp_sample` instead of `pdp_samples` still works
  - Run smoke test with `--json` output to verify schema stability
  - **Verification**: No breaking changes; schema is stable

---

## Phase 9: Commit & Archive

**Duration**: ~30 minutes  
**Blocking**: Release  
**Files**: Git

- [ ] **9.1** Create git commit with all Phase 2 changes
  - Message: `feat: Phase 2 — E2-E6 e-commerce depth features (search API, variants, reviews, inventory, multi-sample PDP)`
  - Include all code, tests, fixtures, docs
  - Verify no accidental files included
  - **Verification**: `git diff --staged` shows clean changeset; commit message is clear

- [ ] **9.2** Tag commit as v0.2.0 (or next semantic version)
  - Execute: `git tag -a v0.2.0 -m "Phase 2: E-Commerce Depth Features (E2-E6)"`
  - Push tag: `git push origin v0.2.0`
  - **Verification**: Tag created and pushed; appears in GitHub releases

- [ ] **9.3** Update project version in relevant files
  - If `setup.py` or `pyproject.toml` exists: bump version to 0.2.0
  - If `config.py` has VERSION constant: update to 0.2.0
  - **Verification**: Version updated everywhere; consistent across project

- [ ] **9.4** Archive SDD documents
  - Move delta specs to main specs (if applicable)
  - Archive in `docs/.sdd/` with Phase_2_COMPLETE suffix
  - Clean up temporary planning files
  - **Verification**: Archive complete; documentation organized

---

## Dependency Graph

```
Phase 1 (Schema)
    ↓
    ├─→ Phase 2 (Variants, E3)
    ├─→ Phase 3 (Multi-PDP, E4)
    ├─→ Phase 4 (Search API, E2)
    │
    ├─→ Phase 5 (Unit Tests) — can run in parallel with 2-4
    │
    ├─→ Phase 6 (Fixtures) — needed for integration tests
    │   ↓
    └─→ Phase 7 (Integration & Smoke) — wait for 2, 3, 4, 5, 6
        ↓
        └─→ Phase 8 (Documentation)
            ↓
            └─→ Phase 9 (Commit & Archive)
```

---

## Execution Notes

### Recommended Approach

1. **Start Phase 1**: Schema changes are blocking everything. Complete and validate.
2. **Parallel Phases 2-4**: Variant, Multi-PDP, and Search API are independent.
3. **Parallel Phase 5**: Write unit tests as you implement (TDD hybrid approach).
4. **Phase 6**: Create fixtures while implementing; reuse for tests.
5. **Phase 7**: Run integration suite after all modules complete.
6. **Phases 8-9**: Polish and ship.

### Testing Strategy (TDD Hybrid)

- **Deterministic layers** (E3, E5, E6 static detection): Write tests first, then code (strict TDD)
- **Discovery layers** (E2 search API, E4 multi-PDP HTTP): Explore first, then write tests (exploratory)
- **All layers**: Unit tests + integration tests + smoke tests on real URLs

### HTTP Budget Watch

- Start of Phase 2: Budget = 27 requests total
- After Phase 4 (E2 search API): Budget = 32 requests total (antibot yields 5 requests)
- **Verify in Phase 7.4**: No scan should exceed 32 requests

### Backward Compatibility Checklist

- [ ] `EcommerceSignals` old fields still work (price_mechanism, price_reliability_score, etc.)
- [ ] `ClassifierResult.pdp_sample` still populated (from pdp_samples[0])
- [ ] Old code reading only `pdp_sample` continues to work
- [ ] All new fields are optional (default None or empty list)
- [ ] JSON export still serializes correctly
- [ ] Terminal report displays all signals (old + new)

---

## Success Criteria

✅ **Phase 2 is COMPLETE when**:

1. All 48 tasks marked as done
2. All tests pass: `make test` succeeds with coverage >= 86%
3. Smoke tests pass on buscalibre.cl and mercadolibre.cl
4. HTTP budget respected: <= 32 requests per full scan
5. No breaking changes: old code still works
6. Documentation updated: README + docstrings
7. Commit created with tag v0.2.0
8. BACKLOG.md updated: E2-E6 marked as ✅ COMPLETE

---

## Notes for Future Implementation

- E4 (multi-PDP): Consider caching consistency metrics to avoid re-fetching same URL
- E2 (search API): May need proxy rotation if high-volume scanning planned
- E5 (reviews): Reviews provider list may grow (Criteo, UserReviews, etc.)
- E6 (inventory): Real-time detection may improve with WebSocket pattern matching
- Phase 3 (E7): Consider --deep flag full JavaScript execution for CSR sites

