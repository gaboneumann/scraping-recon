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
    schema_types: list[str]
    microdata_found: bool
    opengraph_found: bool
    scraping_shortcut: bool


class SecurityHeadersResult(BaseModel):
    csp: bool
    hsts: bool
    x_frame_options: bool
    x_content_type_options: bool
    csp_blocks_inline: bool


class EcommerceSignals(BaseModel):
    """E-commerce detection signals derived from HTML — no additional requests (except E2 probe)."""

    is_ecommerce: bool
    platform: str | None
    price_mechanism: Literal["CLIENT_SIDE", "SERVER_SIDE", "UNKNOWN"]
    price_reliability_score: int | None = None
    cart_architecture: Literal["AJAX_FRAGMENTS", "AJAX_API", "SECTION_CACHE", "UNKNOWN"]
    has_faceted_nav: bool
    has_product_schema: bool
    signal_counts: dict[str, int]

    # E2: Search API
    search_api: SearchApiResult | None = None

    # E3: Variants
    variants: VariantInfo | None = None

    # E5: Reviews
    reviews_provider: ReviewsProviderInfo | None = None

    # E6: Inventory
    inventory: InventoryInfo | None = None


class SearchApiResult(BaseModel):
    """E2: Search API detection result."""

    found: bool
    api_type: Literal["algolia", "elasticsearch", "custom"] | None = None
    endpoint_url: str | None = None
    authenticated: bool | None = None
    confidence: Literal["high", "medium", "low"] = "low"
    detection_method: Literal["pattern", "probe", "both"] | None = None


class VariantInfo(BaseModel):
    """E3: Product variant detection."""

    has_variants: bool = False
    selector_type: Literal["dropdown", "radio", "swatch", "button", "unknown"] | None = None
    variant_count_estimate: int | None = None
    requires_ajax: bool = False
    ajax_endpoint: str | None = None
    confidence: Literal["high", "medium", "low"] = "low"


class InventoryInfo(BaseModel):
    """E6: Inventory mechanism classification."""

    mechanism: Literal["SERVER_SIDE", "AJAX", "UNKNOWN"] = "UNKNOWN"
    stock_element_found: bool = False
    update_pattern: str | None = None
    real_time: bool = False
    confidence: Literal["high", "medium", "low"] = "low"


class ReviewsProviderInfo(BaseModel):
    """E5: Reviews provider detection."""

    provider: Literal[
        "bazaarvoice", "yotpo", "trustpilot", "ekomi", "google", "internal", None
    ] | None = None
    found: bool = False
    api_endpoint: str | None = None
    widget_script_found: bool = False
    confidence: Literal["high", "medium", "low"] = "low"


class PdpSampleResult(BaseModel):
    """Result of fetching 1 PDP URL extracted from category HTML."""

    url: str
    renders_server_side: bool
    price_in_html: bool
    product_schema_found: bool
    response_time_ms: int
    same_protection_as_category: bool


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
    cache_control: str | None
    last_modified: str | None
    locales: list[str]
    mobile_differs: bool
    internal_link_count: int
    estimated_pages: Literal["<50", "50-500", "500-5000", ">5000", "UNKNOWN"]
    ecommerce: EcommerceSignals | None = None
    is_ecommerce_platform: bool = False
    pdp_sample: PdpSampleResult | None = None

    # E4: Multiple PDP samples
    pdp_samples: list[PdpSampleResult] = []
    pdp_consistency: dict[str, float] = {}


class ApiEndpoint(BaseModel):
    url: str
    type: Literal["REST", "GraphQL", "WebSocket", "Unknown"]
    authenticated: bool | None


class ApiDetectorResult(BaseModel):
    internal_api_found: bool
    endpoints: list[ApiEndpoint]
    state_blobs_found: list[str]
    recommendation: str
    endpoints_may_be_incomplete: bool


class PaginationResult(BaseModel):
    type: Literal[
        "QUERY_PARAM", "PATH", "CURSOR", "LOAD_MORE",
        "INFINITE_SCROLL", "LINK_REL_NEXT", "NONE", "UNKNOWN"
    ]
    parameter: str | None
    example_next_url: str | None
    requires_js: bool


class AuthResult(BaseModel):
    required: bool
    type: Literal["NONE", "FORM", "OAUTH", "API_KEY", "PAYWALL", "COOKIE_CONSENT", "UNKNOWN"]
    login_url: str | None
    paywall_type: Literal["HARD", "METERED", "NONE"] | None
    cookie_consent_blocking: bool


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


class BehavioralDetectionDimension(BaseModel):
    """B5: Behavioral event listener detection."""

    score: int = Field(ge=0, le=3)
    listener_count: int
    listener_types: list[str]
    confidence: str


class JourneyDimension(BaseModel):
    """B6: Commerce journey probe results."""

    score: int = Field(ge=0, le=3)
    blocked_at_url: str | None
    blocked_type: Literal["403", "challenge", "redirect", "rate_limit", "none"]
    probes_sent: int


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
    behavioral_detection: BehavioralDetectionDimension
    journey_probes: JourneyDimension


class ApiEndpointProbeResult(BaseModel):
    url: str
    endpoint_type: Literal["REST", "GraphQL"]
    tls: TlsDimension
    rate_limiting: RateLimitDimension


class BehavioralVendor(BaseModel):
    """Behavioral vendor detection signal."""

    name: str
    confidence: Literal["high", "medium", "low"]
    detected_via: list[str]


class AntibotResult(BaseModel):
    overall_score: float = Field(ge=0.0, le=10.0)
    overall_level: Literal["NONE", "LOW", "MEDIUM", "HIGH", "EXTREME"]
    dimensions: AntibotDimensions
    api_endpoint_probes: list[ApiEndpointProbeResult] = Field(default_factory=list)
    behavioral_vendors: list[BehavioralVendor] = Field(default_factory=list)


class RecommenderResult(BaseModel):
    primary_library: str
    secondary_library: str | None
    managed_api_suggested: bool
    managed_api_options: list[str]
    additional_flags: list[str]
    estimated_complexity: int = Field(ge=1, le=10)
    estimated_dev_time: str
    full_stack_recommendation: str


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
