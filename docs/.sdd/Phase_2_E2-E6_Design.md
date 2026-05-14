# Design: Phase 2 — E-Commerce Depth Features (E2-E6)

**Document Status**: READY FOR IMPLEMENTATION  
**Date**: 2026-05-14  
**Topic Key**: `sdd/Phase 2 — E-Commerce Depth Features (E2-E6)/design`

---

## Executive Summary

Phase 2 extends e-commerce signal detection from price reliability (E1—currently implemented) to 5 new dimensions: search API probe (E2), variant detection (E3), multiple PDP samples (E4), reviews provider detection (E5), and inventory mechanism classification (E6).

All detection functions follow existing patterns:
- **Static first**: HTML regex + Pydantic patterns (zero HTTP cost for E3, E5, E6)
- **Optional HTTP**: E2 probes search endpoints (1-2 requests max); E4 adds 2-3 PDP fetches
- **Type safety**: New Pydantic classes for each detection type; all fields optional in EcommerceSignals for backwards compatibility
- **Integration point**: All logic extends `_detect_ecommerce_signals()` in `classifier.py` + new function in `api_detector.py`

---

## Technical Approach

### Home Locations
- **E2 (search API)**: New function `_detect_search_api()` in `api_detector.py` (domain: API detection)
- **E3, E5, E6 (static)**: Extend `_detect_ecommerce_signals()` in `classifier.py` with 3 helper functions
- **E4 (multiple PDP)**: Modify existing `_fetch_pdp_sample()` to handle list of samples (currently handles 1)

### HTTP Budget Allocation
Total additional requests: **5-6 (max)** from current budget of 27.

| Feature | Requests | Notes |
|---------|----------|-------|
| E2 (search API) | 1-2 | Pattern detection (0 cost); optional endpoint probe if pattern found |
| E3 (variants) | 0 | Static HTML parsing only |
| E4 (multi-PDP) | +2-3 | Already allocates 1 for PDP; E4 increases to 3-4 total (3 new) |
| E5 (reviews) | 0 | Static HTML + script analysis |
| E6 (inventory) | 0 | Static HTML patterns + regex for update indicators |
| **Total added** | **5-6** | Within existing anti-bot budget: antibot has 12, can spare 5-6 |

---

## Architecture Decisions

### Decision 1: Where to place E2-E6 logic

**Choice**: 
- **E2**: New function `_detect_search_api(endpoints)` in `api_detector.py`
- **E3, E5, E6**: Extend `_detect_ecommerce_signals()` in `classifier.py`
- **E4**: Modify `_fetch_pdp_sample()` signature to return list instead of single result

**Rationale**: 
- E2 is fundamentally API detection (belongs in api_detector.py)
- E3/E5/E6 are e-commerce-specific static patterns (classifier.py owns ecommerce domain)
- E4 is a modification to existing PDP sampling logic
- Keeps separation of concerns: API detection separate from e-commerce signals

### Decision 2: E4 Multiple PDP Samples Strategy

**Choice**: 
- Extract ALL product links matching `_pdp_pattern()` from category HTML
- Random sample 2-3 links (balanced: more samples = more confidence but higher HTTP cost)
- Fetch each in parallel where possible; collect results in list
- Compute consistency metrics: % matching WAF headers, render mode agreement
- Return `pdp_samples: list[PdpSampleResult]` instead of `pdp_sample: PdpSampleResult | None`

**Rationale**: 
- Single sample is unreliable (one product might have different protection)
- Multiple samples detect platform-wide patterns vs. anomalies
- Magento, VTEX, Shopify vary protection by URL pattern — multi-sample catches this
- Consistency metric validates assumption: "all products in category have uniform protection"

**Backwards Compatibility**:
- ClassifierResult.pdp_sample stays but becomes deprecated (set to pdp_samples[0] if len(pdp_samples) > 0)
- New field: `pdp_samples: list[PdpSampleResult] = []`
- New field: `pdp_consistency: dict = {}` (metrics: "matching_waf_headers_pct", "render_mode_agreement", "error_count")

### Decision 3: Backwards Compatibility for EcommerceSignals

**Choice**: 
All new E2-E6 fields added as optional (default None or False) to EcommerceSignals.

```python
class EcommerceSignals(BaseModel):
    # ... existing fields (price_mechanism, cart_architecture, etc.)
    
    # E2
    search_api_found: bool | None = None
    search_api_type: str | None = None
    search_api_endpoint: str | None = None
    
    # E3
    has_variants: bool = False
    variant_selector_type: str | None = None
    variant_ajax_endpoint: str | None = None
    
    # E4
    pdp_samples: list[PdpSampleResult] = []
    pdp_consistency: dict = {}
    
    # E5
    reviews_provider: str | None = None
    reviews_confidence: str = "low"
    
    # E6
    inventory_mechanism: str = "UNKNOWN"
    inventory_confidence: str = "low"
```

**Rationale**: 
- Existing code consuming EcommerceSignals sees None/default for new fields (no breaking changes)
- Recommender.py and report logic don't need to change
- New code opts-in: `if signals.search_api_found: ...`

### Decision 4: Search API (E2) Probe Strategy

**Choice**: 
1. Pattern detection (0 HTTP): scan for Algolia, Elasticsearch, custom provider markers in:
   - Script tags (`window.algoliaConfig`, `elasticsearch.create()`)
   - HTML attributes (`data-algolia-app-id`)
   - State blobs in `window.__INITIAL_STATE__` or `__NEXT_DATA__`
2. If pattern found: probe 1 endpoint max with `?q=test` query
3. Confidence scoring:
   - Pattern only → "medium" confidence
   - Pattern + successful probe → "high" confidence

**Rationale**: 
- Keep HTTP budget low (most E2 sites have pattern-based detection)
- Pattern detection is high-confidence; probing is optional validation
- Reduces calls to api_detector while leveraging existing structure

### Decision 5: E3 Variant Detection

**Choice**: 
Detect variant selection mechanism by scanning for:
- **Dropdown**: `<select>`, `data-attribute-options`
- **Radio**: `input[type="radio"]`, `variant-option`
- **Swatch**: `data-swatch`, `color-swatch`, `size-option`
- **AJAX**: presence of `/cart/add` endpoint in JS + visible form inputs

Return `VariantInfo` with selector type + estimated count (based on option count in DOM).

**Rationale**: 
- Different selectors require different scraping approaches (selector click vs. form submission)
- AJAX endpoint presence indicates client-side variant logic
- Static HTML provides enough signal without Playwright

### Decision 6: E5 Reviews Provider Detection

**Choice**: 
Scan for known provider patterns in script tags + window objects:

```
Bazaarvoice:    "bv.doReplace", "window.BV"
Yotpo:          "yotpoElement", "window.yotpo"
Trustpilot:     "trustbox", "api.trustpilot.com"
Google Reviews: "google-reviews", "www.google.com/reviews"
Native:         reviews in JSON-LD, on-page review section
```

Confidence: "high" if provider script loaded, "medium" if only references, "low" if HTML reviews + no external signal.

**Rationale**: 
- External providers are directly scrape-able; avoiding the main site entirely
- Pattern detection is fast and reliable for known vendors
- Native reviews require different extraction logic

### Decision 7: E6 Inventory Mechanism

**Choice**: 
Classify as:
- **SERVER_SIDE**: stock value in HTML, changes via page reload
- **AJAX**: stock value empty/placeholder in HTML, loaded via XHR (indicators: "loading", data-ajax-url, fetch() patterns)
- **UNKNOWN**: no clear indicator

Confidence scoring based on pattern strength.

**Rationale**: 
- Determines scraping strategy: HTML parse vs. XHR interception
- AJAX + Playwright usage are linked recommendations
- Static patterns catch majority of cases

---

## Data Flow

```
classify_page(url, timeout)
  ├─ [existing: framework, CMS, CDN, structured data detection]
  │
  ├─ _detect_ecommerce_signals(html, soup, cms)
  │   ├─ [existing: is_ecommerce, platform, price_mechanism, price_reliability_score]
  │   │
  │   ├─ E3: _detect_variants(soup) → VariantInfo
  │   ├─ E5: _detect_reviews_provider(html, soup) → ReviewsInfo
  │   └─ E6: _detect_inventory_mechanism(html, soup) → InventoryInfo
  │
  ├─ [existing: fetch_mobile_variant, classify page type]
  │
  ├─ E4: _fetch_pdp_samples(url, html, headers, timeout, count=2-3)
  │   ├─ Extract all product links
  │   ├─ Sample 2-3 randomly
  │   ├─ Parallel fetch (or sequential)
  │   ├─ Collect PdpSampleResult for each
  │   └─ Compute pdp_consistency metrics
  │
  └─ return ClassifierResult with ecommerce + pdp_samples

[Later in recommender pipeline, if needed]
  detect_apis(url, classifier_type)
    └─ _detect_search_api(endpoints) → SearchApiResult
```

---

## File Changes

| File | Action | What Changes |
|------|--------|-------------|
| `models/schemas.py` | **Modify** | Add VariantInfo, ReviewsInfo, InventoryInfo, SearchApiResult classes; extend EcommerceSignals with 8 new optional fields; add pdp_samples + pdp_consistency to ClassifierResult |
| `modules/classifier.py` | **Modify** | Extend `_detect_ecommerce_signals()` to call 3 helpers (E3, E5, E6); modify `_fetch_pdp_sample()` → `_fetch_pdp_samples()` to handle multiple samples and compute consistency |
| `modules/api_detector.py` | **Modify** | Add `_detect_search_api(endpoints)` function to be called post-classify; populate new SearchApiResult fields in detect_apis() |
| `tests/unit/test_classifier_*.py` | **Modify** | Add 45-50 unit tests for E3, E4, E6 variants + reviews + inventory; add fixtures for HTML patterns |
| `tests/unit/test_api_detector.py` | **Modify** | Add 10-15 unit tests for E2 search API detection (Algolia, Elasticsearch patterns) |
| `tests/fixtures/html/` | **New** | Add 6-8 fixture HTML files for variant, reviews provider, inventory patterns |

---

## Detailed Interfaces

### SearchApiResult (NEW)
```python
class SearchApiResult(BaseModel):
    """E2: Search API detection result."""
    
    api_found: bool
    api_type: Literal["algolia", "elasticsearch", "custom", None] | None = None
    endpoint_url: str | None = None
    requires_auth: bool = False
    confidence: Literal["high", "medium", "low"] = "low"
    detection_method: Literal["pattern", "probe", "both"] | None = None
```

**Detection method clarification**:
- "pattern": Detected via script/config scan (no HTTP cost)
- "probe": Confirmed via endpoint request
- "both": Pattern + probe confirmed

### VariantInfo (NEW)
```python
class VariantInfo(BaseModel):
    """E3: Product variant detection."""
    
    has_variants: bool
    selector_type: Literal["dropdown", "radio", "swatch", "ajax", "unknown"] | None = None
    estimated_count: int | None = None  # # of options in DOM
    requires_ajax: bool = False  # separate endpoint for variants
    ajax_endpoint: str | None = None
    confidence: Literal["high", "medium", "low"] = "low"
```

### ReviewsInfo (NEW)
```python
class ReviewsInfo(BaseModel):
    """E5: Reviews provider detection."""
    
    provider: str | None = None  # "bazaarvoice", "yotpo", "trustpilot", "google", "native", None
    is_external: bool = False  # True if 3rd-party hosted
    confidence: Literal["high", "medium", "low"] = "low"
    detection_signals: list[str] = []  # signals that triggered detection
```

### InventoryInfo (NEW)
```python
class InventoryInfo(BaseModel):
    """E6: Inventory mechanism classification."""
    
    mechanism: Literal["SERVER_SIDE", "AJAX", "UNKNOWN"] = "UNKNOWN"
    confidence: Literal["high", "medium", "low"] = "low"
    indicators: list[str] = []  # patterns that informed the decision
    update_pattern: str | None = None  # regex or description of how values change
```

### Extended EcommerceSignals
```python
class EcommerceSignals(BaseModel):
    """E-commerce detection signals derived from HTML — no additional requests (except E2 probe)."""

    # ============ EXISTING (E1) ============
    is_ecommerce: bool
    platform: str | None
    price_mechanism: Literal["CLIENT_SIDE", "SERVER_SIDE", "UNKNOWN"]
    price_reliability_score: int | None = None
    cart_architecture: Literal["AJAX_FRAGMENTS", "AJAX_API", "SECTION_CACHE", "UNKNOWN"]
    has_faceted_nav: bool
    has_product_schema: bool
    signal_counts: dict[str, int]
    
    # ============ NEW (E2-E6) ============
    # E2: Search API
    search_api_found: bool | None = None
    search_api_type: str | None = None
    search_api_endpoint: str | None = None
    search_api_confidence: str = "low"
    
    # E3: Variants
    has_variants: bool = False
    variant_selector_type: str | None = None
    variant_ajax_endpoint: str | None = None
    variant_count_estimate: int | None = None
    
    # E5: Reviews
    reviews_provider: str | None = None
    reviews_is_external: bool = False
    reviews_confidence: str = "low"
    
    # E6: Inventory
    inventory_mechanism: str = "UNKNOWN"
    inventory_confidence: str = "low"
```

### Extended ClassifierResult
```python
class ClassifierResult(BaseModel):
    # ... existing fields ...
    
    # MODIFIED: PDP sampling
    pdp_sample: PdpSampleResult | None = None  # DEPRECATED: use pdp_samples[0]
    pdp_samples: list[PdpSampleResult] = []  # NEW: multiple samples
    pdp_consistency: dict = {}  # NEW: { "matching_headers_pct": 75, "render_mode_agreement": true, ... }
```

---

## Implementation Constraints

### What to Detect (and NOT detect)

| Feature | Detect? | Reason |
|---------|---------|--------|
| E2: Algolia, Elasticsearch, custom search endpoints | ✅ Yes | ~60% of e-commerce sites; high ROI for scraper decision-making |
| E2: Analytics/tracking APIs | ❌ No | Not relevant to scraping strategy |
| E3: Variant existence and selector UI type | ✅ Yes | Affects request strategy (form vs. AJAX) |
| E3: Exact variant count | Partial | Count option elements in HTML; don't probe |
| E4: Protection variance across products | ✅ Yes | Validates assumption about uniform protection |
| E5: Review provider existence | ✅ Yes | Suggests alternative scrape target |
| E5: Exact review count | ❌ No | Metadata; use provider's API instead |
| E6: Real stock value vs. placeholder | ✅ Yes | Determines refresh strategy (static vs. live) |
| E6: Exact stock number | ❌ No | Changes per minute; capture in scraper run |

### HTTP Cost Minimization

1. **E2**: Use pattern detection (0 cost); probe only if pattern found (1-2 requests)
2. **E3, E5, E6**: Pure static HTML parsing (0 cost)
3. **E4**: Allocate 2-3 extra requests (from available budget)
4. **Total overhead**: 5-6 requests (acceptable within 27-request budget)

### Confidence Scoring

Each E2-E6 detection must include `confidence: Literal["high", "medium", "low"]`:
- **high**: Multiple signals converge (e.g., pattern + probe OK + context)
- **medium**: Single strong signal or weak converging signals
- **low**: Single weak signal or speculative pattern

---

## Testing Strategy

### Unit Tests (60-70 tests total)

| Layer | What | Approach | Files |
|-------|------|----------|-------|
| **E3 (Variants)** | 10-12 tests | Parameterized HTML fixtures (dropdown, radio, swatch, AJAX); check selector detection + count estimation | `test_classifier_variants.py` |
| **E5 (Reviews)** | 8-10 tests | Mock provider scripts (Bazaarvoice, Yotpo, Trustpilot, native); validate provider detection + confidence | `test_classifier_reviews.py` |
| **E6 (Inventory)** | 10-12 tests | HTML patterns (SERVER_SIDE, AJAX loading indicators, placeholders); validate mechanism classification | `test_classifier_inventory.py` |
| **E4 (Multi-PDP)** | 10-12 tests | Mock _fetch_pdp_sample; verify list return, consistency computation | `test_classifier_pdp_samples.py` |
| **E2 (Search API)** | 12-15 tests | Mock HTTP responses; test pattern detection (Algolia, ES, custom); test probe logic with respx | `test_api_detector_search_api.py` |

### Integration Tests (5-8 tests)

- E2-E6 as part of `classify_page()` pipeline
- Use existing fixtures: WooCommerce, Shopify, PrestaShop, Magento
- Verify all fields populated correctly + no HTTP errors
- Verify backwards compatibility: old EcommerceSignals consumers still work

### Real-world Tests (3-5 smoke tests)

- `books.toscrape.com` (baseline: no variants, native reviews, SSR inventory)
- `buscalibre.cl/libros/computacion` (PrestaShop: variants + Yotpo reviews)
- `mercadolibre.cl/categoria` (hybrid: AJAX variants + external reviews + CloudFlare)

---

## Migration / Rollout

### Phase Ordering
1. **Implement E3, E5, E6 (static)** → Low risk, zero HTTP cost
2. **Implement E4 (multi-PDP)** → Test with existing pdp_pattern
3. **Implement E2 (search API)** → Requires api_detector.py coordination
4. **Integration tests** → Verify no regressions

### Backwards Compatibility
- ✅ All new fields optional; old code sees None/default
- ✅ `pdp_sample` (old field) stays but deprecated; new code uses `pdp_samples[0]`
- ✅ Recommender.py and report logic unchanged
- ✅ Existing tests pass as-is

### Configuration Changes
- No new config flags needed
- HTTP budget already accounts for 5-6 new requests
- Deep mode (E7) separate from Phase 2

---

## Open Questions / Decisions Pending

- [ ] **E2 probe strategy**: Should we always probe if pattern found, or only if user requests detailed analysis?
  - *Proposal*: Probe if pattern found (1 request budget acceptable)
  
- [ ] **E4 sample count**: 2 or 3 samples?
  - *Proposal*: 2 samples (balance between confidence and HTTP cost)
  
- [ ] **E3 variant count estimation**: Use DOM option count or probe for server-side variants?
  - *Proposal*: DOM count only (static); E7 deep mode can probe if needed
  
- [ ] **E5 reviews confidence scoring**: Should external provider presence alone = high confidence?
  - *Proposal*: Pattern match (script tag) = "medium"; probe success = "high"

---

## Summary

Phase 2 adds 5 new e-commerce detection dimensions (E2-E6) to existing price reliability scoring (E1). Implementation follows established patterns in classifier.py and api_detector.py: static HTML analysis first, optional HTTP validation, Pydantic schemas for type safety, and backwards-compatible field additions. Total HTTP overhead: 5-6 requests within existing budget. Ready for task breakdown and implementation.

**Status**: APPROVED FOR IMPLEMENTATION  
**Next Step**: `sdd-tasks` (task breakdown)
