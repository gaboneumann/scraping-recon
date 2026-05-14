# Proposal: Phase 2 — E-Commerce Depth Features (E2-E6)

## Intent

Phase 1 (B1-B7: behavioral antibot vendors) is complete, adding 2 new antibot detection dimensions (behavioral listeners, journey probes) and improving existing coverage (WAF, TLS, PoW, headless checks, behavioral scripts, WebRTC).

**Phase 2 extends e-commerce reconnaissance** by completing the 5 missing depth features (E2-E6), enabling scrapers to make informed decisions about:
- Alternative data sources (search APIs, reviews providers) that bypass HTML scraping
- Product variant architecture (static selectors vs AJAX endpoints)
- Inventory tracking mechanisms (real stock vs placeholders)
- Multi-sample consistency (whether all products behave identically or vary)

This transforms the classifier from basic "is it e-commerce?" detection to "what's the scraping strategy?" intelligence, reducing blind spots in early reconnaissance and cutting development time by identifying APIs and patterns upfront.

## Scope

### In Scope

| Feature | ID | What | Why | Impact |
|---------|----|----|-----|--------|
| Search API probe | E2 | Detect Algolia, Elasticsearch, custom search endpoints | Scrape catalog via API instead of HTML pagination | +1-2 HTTP requests, immediate ROI |
| Product variants | E3 | Identify color/size/SKU selectors and AJAX endpoints | Understand variant fetch pattern (form data, query param, POST) | Static detection, no extra requests |
| Multi-PDP samples | E4 | Fetch 2-3 PDPs instead of 1 for consistency check | Confirm whether all products have same protections/price mechanism | +1-2 HTTP requests, higher confidence |
| External reviews API | E5 | Detect Bazaarvoice, Yotpo, Trustpilot, eKomi scripts | Scrape reviews from vendor API (better quality, less effort) | Static detection, no extra requests |
| Inventory mechanism | E6 | Distinguish static HTML stock vs AJAX-updated values | Know if you need JavaScript to get real stock levels | Static detection, no extra requests |

**Total New HTTP Requests**: 3-5 (within budget tolerance; current baseline = 27).

### Out of Scope

- **E7 (Deep Mode / Playwright)** — Deferred to Phase 3. E2-E6 are all static-first.
- Real JavaScript execution of variant selection pages (requires Playwright).
- Sentiment analysis or review scraping logic itself.
- Cart / checkout probes (abandoned as A3; requires authenticated sessions).
- Search API schema inference (only endpoint detection, not payload analysis).

## Capabilities

### New Capabilities

#### `search-api-detection`
**Input**: HTML response + headers + URL.  
**Output**: `SearchApiSignal` with:
- `api_detected: bool` — is there a search endpoint?
- `provider: str | None` — "Algolia", "Elasticsearch", "custom", or None
- `endpoint_pattern: str | None` — e.g., "/api/search?q=", "/v3/search"
- `auth_required: bool` — does search need authentication?

**Logic**:
1. Scan for Algolia, Elasticsearch, TypeSense, MeiliSearch script includes
2. Look for `<script>` blocks with API keys (e.g., `algoliasearch("APP_ID", "SEARCH_KEY")`)
3. Probe common search patterns: `/api/search`, `/graphql?operationName=Search`, `/v3/search`
4. Check response headers for API signatures (x-algolia-*, x-elasticsearch-*)

**Tests**: 8-10 unit tests (Algolia, Elasticsearch, custom endpoint, no API)

---

#### `product-variant-detection`
**Input**: HTML from PDP sample.  
**Output**: `VariantSignal` with:
- `has_variants: bool` — does product have multiple options?
- `variant_type: Literal["SELECT_DROPDOWN", "RADIO_BUTTON", "LINK", "AJAX_GRID", "UNKNOWN"]`
- `ajax_endpoint: str | None` — e.g., "/api/variants", detected from XHR scripts
- `variant_params: dict[str, str]` — e.g., `{"product_id": "...", "variant_id": "..."}`
- `confidence: str` — "high", "medium", "low"

**Logic**:
1. Detect `<select>`, `<input type="radio">`, or grid-based selectors for size/color
2. Look for data attributes: `data-variant-id`, `data-option-values`, `data-variant-json`
3. Scan for XHR/fetch calls to `/api/variants`, `/variants.json`, or `/add-to-cart` with variant params
4. Infer transport: POST form data vs URL query param vs JSON body

**Tests**: 8-10 unit tests (WooCommerce selects, Shopify API variants, no variants, AJAX variants)

---

#### `external-reviews-provider-detection`
**Input**: HTML + script tags.  
**Output**: `ReviewsSignal` with:
- `provider_detected: str | None` — "Bazaarvoice", "Yotpo", "Trustpilot", "eKomi", "Judge.me", or None
- `api_endpoint: str | None` — e.g., "https://reviews.bazaarvoice.com/api/..."
- `confidence: str` — "high", "medium", "low"
- `can_scrape_independently: bool` — true if reviews are fetched client-side and reachable without site session

**Logic**:
1. Detect vendor SDK script tags: `reviews.bazaarvoice.com`, `yotpo.com/widgets`, `trustpilot.com/review`, `ekomi.de`
2. Extract API endpoints from script URLs and data attributes
3. Check if reviews are embedded via iframe (easier to extract) or AJAX calls
4. Confidence high if multiple vendor signals or explicit API endpoint found

**Tests**: 8-10 unit tests (Bazaarvoice, Yotpo, no vendor, mixed providers)

---

### Modified Capabilities

#### `ecommerce-classification` (extend in `classifier.py`)
**Changes to `EcommerceSignals`**:
- Add `E2: SearchApiSignal | None` (new field)
- Add `E3: VariantSignal | None` (new field)
- Add `E4: MultiSampleConsistency | None` (new field)
- Add `E5: ReviewsSignal | None` (new field)
- Add `E6: InventoryMechanism | None` (new field)

**Changes to `_detect_ecommerce_signals()`**:
1. Extend function to call new detection functions for E2-E6
2. Call `_probe_search_api()` with 1-2 requests (E2)
3. Extend `_fetch_pdp_sample()` to fetch 2-3 PDPs (E4) and analyze variants on first PDP (E3)
4. Scan returned HTML for external reviews providers (E5)
5. Analyze inventory signals on PDP samples (E6)

**Backwards Compatibility**: New fields are all optional (`| None`), so existing tests and output remain valid.

---

#### `multi-sample-consistency` (extend PDP fetching)
Currently: Fetch 1 PDP.  
**New behavior**: Fetch 2-3 PDPs (if available) and compare:
- Price rendering method (all server-side? all client-side? mixed?)
- Security/antibot signatures (same WAF, same JS protection, or varies?)
- Variant presence (all have variants, or inconsistent?)
- Schema markup (all have JSON-LD Product, or missing in some?)

**Output**: New `MultiSampleConsistency` schema:
```python
class MultiSampleConsistency(BaseModel):
    samples_collected: int  # 1, 2, or 3
    all_same_render_mode: bool
    all_same_protection: bool
    variance_notes: str | None  # e.g., "50% have data-price, 50% use JS"
```

---

## Approach

### Architecture Changes

1. **`models/schemas.py`**:
   - Add 5 new Pydantic classes: `SearchApiSignal`, `VariantSignal`, `ReviewsSignal`, `InventoryMechanism`, `MultiSampleConsistency`
   - Extend `EcommerceSignals` with new optional fields (E2-E6)
   - All new fields default to `None` for backwards compatibility

2. **`modules/classifier.py`**:
   - Add 5 new detection functions: `_probe_search_api()`, `_detect_variants()`, `_detect_reviews_provider()`, `_detect_inventory_mechanism()`, `_analyze_multi_sample()`
   - Modify `_fetch_pdp_sample()` to optionally fetch 2-3 samples (controlled by config flag `fetch_multiple_samples=True`)
   - Extend `_detect_ecommerce_signals()` to call new detection functions
   - Integrate E2 search probe within existing HTTP budget (1-2 requests)

3. **`modules/api_detector.py`**:
   - No changes required; search API probes are part of classifier E2, not api_detector

4. **`tests/unit/`**:
   - Add `test_classifier_search_api.py` (8-10 tests)
   - Add `test_classifier_variants.py` (8-10 tests)
   - Add `test_classifier_reviews_provider.py` (8-10 tests)
   - Add `test_classifier_inventory.py` (6-8 tests)
   - Add `test_classifier_multi_sample.py` (6-8 tests)
   - **Total**: ~45 new tests (current baseline 250 → ~295)

5. **`tests/fixtures/html/`**:
   - Add fixture for WooCommerce PDP with variants + reviews (Yotpo)
   - Add fixture for Shopify API variant response
   - Add fixture for Algolia search endpoint + key
   - Add fixture for Elasticsearch
   - Add fixture for Bazaarvoice reviews embed
   - **Total**: ~5 new fixtures

### HTTP Request Budget Allocation

**Current budget**: 27 requests / scan.  
**Proposed additions**:

| Feature | Requests | Notes |
|---------|----------|-------|
| E2: Search API probe | 1-2 | Try common patterns if no SDK detected; optional if timeout |
| E4: Multi-sample PDP | +1-2 | Fetch 2nd and 3rd PDPs (if available on category page) |
| **New Total** | **29-31** | Still within tolerance (config allows up to 32) |

**Safety**: All new probes are timeoutted (5s each); if slow, they fail gracefully and return None.

---

## Affected Areas

| Area | Impact | Details |
|------|--------|---------|
| `models/schemas.py` | **Modified** | Add 5 new Pydantic classes; extend `EcommerceSignals` (backward compatible) |
| `modules/classifier.py` | **Modified** | Add 5 new detection functions; extend `_detect_ecommerce_signals()` |
| `modules/api_detector.py` | **No change** | Search API detection stays in classifier (E2) |
| `modules/legal.py`, `auth_detector.py`, `pagination.py`, `antibot.py` | **No change** | Orthogonal |
| `tests/unit/test_classifier_*.py` | **Modified** | Add test cases for E2-E6 (inline with existing test files or split into 5 new files) |
| `tests/fixtures/html/` | **New** | Add 5-6 new HTML fixtures (Algolia, Shopify variants, Bazaarvoice, etc.) |
| `tests/integration/` | **Modified** | Extend real-world integration tests with E2-E6 assertions (books.toscrape.com, buscalibre.cl, mercadolibre.cl) |
| `config.py` | **Modified** | Add optional flag `fetch_multiple_samples: bool = False` (opt-in for multi-PDP) |
| `docs/BACKLOG.md` | **Modified** | Mark E2-E6 as ✅ complete; update line counts |

---

## Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| HTTP budget exceeded (>32 requests) | Low | Causes timeout on slow sites | Pre-test on real e-commerce sites (buscalibre, mercadolibre); time each probe; disable E2 or E4 if needed |
| Backwards compatibility broken | Low | Existing integration tests fail | New fields are `None`-default; all existing tests unchanged; spot-check on known sites |
| Search API detection too broad (false positives) | Medium | Recommends search API that doesn't work | Add confidence field; validate with Algolia/Elasticsearch reference implementations |
| Variant detection misses patterns | Medium | Incomplete variant information | Start with 3 major platforms (Shopify, WooCommerce, Magento); add `confidence: "low"` for uncertain cases; document limitations in BACKLOG |
| Reviews provider detection false negative | Low | Misses some vendors | Maintain a list of known vendors in a constant; easy to extend |
| Multi-sample fetching adds latency | Medium | Real sites with slow servers | Make it configurable (opt-in flag); timeout each PDP fetch at 5s; fallback to 1 sample on timeout |

---

## Rollback Plan

**If Phase 2 breaks something**:
1. Keep Phase 1 stable (behavioral antibot, all B1-B7 working).
2. Revert Phase 2 commits in reverse order:
   - `git revert` E6 changes (inventory)
   - `git revert` E5 changes (reviews provider)
   - `git revert` E4 changes (multi-sample)
   - `git revert` E3 changes (variants)
   - `git revert` E2 changes (search API)
3. If HTTP budget exceeded: Comment out E2 and E4 probes; keep E3/E5/E6 (all static).
4. Re-run `make test` to confirm no regression.

---

## Dependencies

| Dependency | Status | Notes |
|------------|--------|-------|
| Phase 1 (B1-B7) | ✅ Complete | All behavioral antibot features working |
| Existing test fixtures | ✅ Available | WooCommerce, Shopify, React API-driven test sites |
| HTTP library stack | ✅ Available | httpx, curl_cffi, BeautifulSoup4 (all installed) |
| New external libraries | ❌ Not needed | No new dependencies required |
| Real e-commerce test URLs | ✅ Available | books.toscrape.com, buscalibre.cl, mercadolibre.cl |

---

## Success Criteria

- [ ] **Implementation**: All 5 detection functions (E2-E6) implemented per BACKLOG.md spec
- [ ] **Testing**: 40-50 new unit tests + extended integration tests
  - E2 (search API): 8-10 tests
  - E3 (variants): 8-10 tests
  - E4 (multi-sample): 6-8 tests
  - E5 (reviews provider): 8-10 tests
  - E6 (inventory): 6-8 tests
- [ ] **Coverage**: Test coverage maintains >= 86% (currently 86.22%)
- [ ] **HTTP Budget**: New probes fit within 32-request tolerance (current + 3-5 new)
- [ ] **Integration Tests**: Pass against 3 real sites:
  - books.toscrape.com (baseline SSR e-commerce, no variants, no reviews)
  - buscalibre.cl (PrestaShop with variants, reviews, Algolia search)
  - mercadolibre.cl (custom e-commerce with AJAX, inventory tracking)
- [ ] **Backwards Compatibility**: All existing classifier tests pass unchanged; new fields are optional
- [ ] **Documentation**: BACKLOG.md updated to mark E2-E6 as ✅ complete; line counts updated
- [ ] **Code Quality**: No new linting errors; docstrings on all new functions; type hints throughout

---

## Effort Estimate

| Phase | Estimate | Notes |
|-------|----------|-------|
| **Design** (this document) | 1h | ✅ Done |
| **Implementation** (E2-E6 functions) | 4-5h | 5 detection functions + modifications to classifier.py |
| **Testing** (unit + fixtures) | 3-4h | 40-50 new tests + fixtures |
| **Integration** (real URLs) | 1-2h | Smoke test against 3 sites; adjust for false positives |
| **Documentation** | 0.5h | BACKLOG.md updates |
| **Review & Refine** | 1-2h | Code review, minor fixes |
| **Total** | **10-15h** | Spread over 2-3 development sessions |

---

## Next Steps

1. **Approval**: Confirm this proposal with the project owner (user).
2. **Design Phase** (`sdd-design`): Detailed architecture for each E2-E6 detection function.
3. **Task Breakdown** (`sdd-tasks`): Convert scope into granular implementation tasks.
4. **Implementation** (`sdd-apply`): Code each function, add tests, integrate.
5. **Verification** (`sdd-verify`): Confirm all success criteria met.
6. **Archive** (`sdd-archive`): Close Phase 2, merge to main, prepare Phase 3.

---

## Appendix: Example Outputs

### E2 Search API Detection
```json
{
  "api_detected": true,
  "provider": "Algolia",
  "endpoint_pattern": "/api/v1/search/",
  "auth_required": false
}
```

### E3 Variant Detection
```json
{
  "has_variants": true,
  "variant_type": "AJAX_GRID",
  "ajax_endpoint": "/api/products/{id}/variants",
  "variant_params": {"product_id": "123", "option": "size"},
  "confidence": "high"
}
```

### E5 Reviews Provider
```json
{
  "provider_detected": "Bazaarvoice",
  "api_endpoint": "https://reviews.bazaarvoice.com/api/...",
  "confidence": "high",
  "can_scrape_independently": true
}
```

### E6 Inventory Mechanism
```json
{
  "mechanism": "AJAX",
  "update_endpoint": "/api/stock/{sku}",
  "is_static_html": false,
  "confidence": "medium"
}
```
