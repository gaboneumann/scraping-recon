# STEP 0 — models/schemas.py [CHECKPOINT]

**Implementa primero. Todos los módulos importan desde aquí.**

Define los Pydantic models para cada módulo. Si los schemas cambian, actualiza este archivo y notifícame antes de continuar.

```python
"""
models/schemas.py
Pydantic contracts for all scraping_recon module outputs.
Import from here — never define inline schemas in modules.
"""
from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field


class RobotsTxtResult(BaseModel):
    found: bool
    ua_specific: bool
    crawl_delay_seconds: int | None
    target_path_allowed: bool
    blocked_paths: list[str]
    sitemap_declared: str | None


class SitemapResult(BaseModel):
    found: bool
    type: str
    url_count: int | None
    last_modified: str | None
    product_sitemap_url: str | None = None  # /sitemap_products.xml (Shopify), /media/sitemap/ (Magento)


class TosResult(BaseModel):
    found: bool
    url: str | None
    risk_level: Literal["LOW", "MEDIUM", "HIGH", "UNKNOWN"]
    flagged_keywords: list[str]


class LegalResult(BaseModel):
    robots_txt: RobotsTxtResult
    sitemap: SitemapResult
    tos: TosResult


class StructuredDataResult(BaseModel):
    json_ld_found: bool
    schema_types: list[str]        # e.g. ["Product", "BreadcrumbList"]
    microdata_found: bool
    opengraph_found: bool
    scraping_shortcut: bool        # True si JSON-LD cubre campos objetivo


class SecurityHeadersResult(BaseModel):
    csp: bool                      # Content-Security-Policy presente
    hsts: bool                     # Strict-Transport-Security presente
    x_frame_options: bool
    x_content_type_options: bool
    csp_blocks_inline: bool        # CSP contiene "unsafe-inline" ausente → scripts inline bloqueados


class EcommerceSignals(BaseModel):
    """
    E-commerce specific signals detected from HTML analysis only — no extra requests.
    All fields default to False/UNKNOWN so non-ecommerce scans are unaffected.
    """
    is_ecommerce: bool = False
    is_product_page: bool = False           # product detail page signals present
    has_cart: bool = False                  # add-to-cart / mini-cart signals
    has_price_signals: bool = False         # ≥2 price-related elements detected
    has_inventory_signals: bool = False     # in-stock / out-of-stock / availability
    has_review_signals: bool = False        # ratings / review count
    has_faceted_nav: bool = False           # filter/facet UI detected
    price_mechanism: Literal["SERVER_SIDE", "CLIENT_SIDE", "STRUCTURED_DATA", "UNKNOWN"] = "UNKNOWN"
    # SERVER_SIDE: prices in HTML text nodes
    # CLIENT_SIDE: empty containers + data-price attrs → prices loaded via AJAX
    # STRUCTURED_DATA: prices only in JSON-LD
    cart_architecture: Literal["AJAX_FRAGMENTS", "AJAX_API", "SECTION_CACHE", "UNKNOWN_DYNAMIC", "UNKNOWN"] = "UNKNOWN"
    # AJAX_FRAGMENTS: WooCommerce wc-cart-fragments
    # AJAX_API: Shopify /cart.js
    # SECTION_CACHE: Magento magentoSectionData


class ClassifierResult(BaseModel):
    type: Literal["STATIC", "DYNAMIC", "HYBRID", "API_DRIVEN", "UNKNOWN"]
    confidence: Literal["HIGH", "MEDIUM", "LOW"]
    js_frameworks: list[str]
    cms: str | None
    server: str | None
    cdn: str | None
    infrastructure: list[str]
    dns_signals: dict[str, str]
    content_ratio: float
    response_time_ms: int
    structured_data: StructuredDataResult
    security_headers: SecurityHeadersResult
    cache_control: str | None      # valor raw del header Cache-Control
    last_modified: str | None      # valor raw del header Last-Modified
    locales: list[str]             # códigos detectados vía hreflang o rutas (/es/, /en/)
    mobile_differs: bool           # True si mobile UA entrega contenido distinto
    internal_link_count: int       # links internos únicos en el homepage
    estimated_pages: Literal["<50", "50-500", "500-5000", ">5000", "UNKNOWN"]
    ecommerce: EcommerceSignals = Field(default_factory=EcommerceSignals)
    is_ecommerce_platform: bool = False  # True si CMS pertenece a ECOMMERCE_PLATFORMS


class ApiEndpoint(BaseModel):
    url: str
    type: Literal["REST", "GraphQL", "WebSocket", "WooCommerce-REST", "Magento-REST", "BigCommerce-REST", "SFCC-REST", "Unknown"]
    authenticated: bool | None


class ApiDetectorResult(BaseModel):
    internal_api_found: bool
    endpoints: list[ApiEndpoint]
    state_blobs_found: list[str]
    recommendation: str
    endpoints_may_be_incomplete: bool  # True si el sitio es DYNAMIC — endpoints JS no interceptables sin browser


class PaginationResult(BaseModel):
    type: Literal[
        "QUERY_PARAM", "PATH", "CURSOR", "LOAD_MORE",
        "INFINITE_SCROLL", "LINK_REL_NEXT", "NONE", "UNKNOWN"
    ]
    parameter: str | None
    example_next_url: str | None
    requires_js: bool
    has_faceted_nav: bool = False  # product filter/facet UI detected (retail catalog pattern)


class WafDimension(BaseModel):
    score: int = Field(ge=0, le=3)
    vendor: str | None
    confidence: str


class TlsDimension(BaseModel):
    score: int = Field(ge=0, le=3)
    sensitivity: str
    client_results: dict[str, str]


class RateLimitDimension(BaseModel):
    score: int = Field(ge=0, le=3)
    triggered_at: int | None
    error_type: str | None


class CaptchaDimension(BaseModel):
    score: int = Field(ge=0, le=3)
    provider: str | None
    version: str | None


class FingerprintDimension(BaseModel):
    score: int = Field(ge=0, le=3)
    libraries: list[str]


class HoneypotDimension(BaseModel):
    score: int = Field(ge=0, le=3)
    count: int
    locations: list[str]


class IpRepDimension(BaseModel):
    score: int = Field(ge=0, le=3)
    geo_block: bool
    proxy_recommendation: str


class AntibotDimensions(BaseModel):
    waf: WafDimension
    tls_fingerprint: TlsDimension
    rate_limiting: RateLimitDimension
    captcha: CaptchaDimension
    browser_fingerprinting: FingerprintDimension
    honeypots: HoneypotDimension
    ip_reputation: IpRepDimension


class AntibotResult(BaseModel):
    overall_score: float = Field(ge=0.0, le=10.0)
    overall_level: Literal["NONE", "LOW", "MEDIUM", "HIGH", "EXTREME"]
    dimensions: AntibotDimensions


class RecommenderResult(BaseModel):
    primary_library: str
    secondary_library: str | None
    managed_api_suggested: bool
    managed_api_options: list[str]
    additional_flags: list[str]
    estimated_complexity: int = Field(ge=1, le=10)
    estimated_dev_time: str
    full_stack_recommendation: str


class AuthResult(BaseModel):
    required: bool
    type: Literal["NONE", "FORM", "OAUTH", "API_KEY", "PAYWALL", "COOKIE_CONSENT", "UNKNOWN"]
    login_url: str | None
    paywall_type: Literal["HARD", "METERED", "NONE"] | None
    cookie_consent_blocking: bool


class ModuleStatus(BaseModel):
    name: str
    status: Literal["OK", "INCOMPLETE", "BLOCKED", "SKIPPED"]
    error: str | None = None


class ReconReport(BaseModel):
    url: str
    timestamp: str
    scan_duration_ms: int
    modules_status: list[ModuleStatus]
    legal: LegalResult | None = None
    classifier: ClassifierResult | None = None
    auth: AuthResult | None = None
    api_detector: ApiDetectorResult | None = None
    pagination: PaginationResult | None = None
    antibot: AntibotResult | None = None
    recommender: RecommenderResult | None = None
```

**[CHECKPOINT 0]** — Ejecuta:
```bash
python -c "
from models.schemas import ReconReport, EcommerceSignals, ClassifierResult
r = ClassifierResult.__fields__
assert 'ecommerce' in r and 'is_ecommerce_platform' in r
print('schemas OK — EcommerceSignals fields:', list(EcommerceSignals.__fields__.keys()))
"
```
Muéstrame el output. No continúes si hay errores de importación.
