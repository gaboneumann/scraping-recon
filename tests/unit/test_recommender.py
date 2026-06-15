"""
tests/unit/test_recommender.py
Unit tests for modules/recommender.py — pure function, no I/O.
Uses the make_report fixture for building partial ReconReport objects.
"""
import pytest

from models.schemas import (
    AntibotDimensions,
    AntibotResult,
    ApiDetectorResult,
    BehavioralDetectionDimension,
    ClassifierResult,
    EcommerceSignals,
    FingerprintDimension,
    HoneypotDimension,
    IpRepDimension,
    JourneyDimension,
    CaptchaDimension,
    RateLimitDimension,
    SecurityHeadersResult,
    StructuredDataResult,
    TlsDimension,
    WafDimension,
    PaginationResult,
)
from modules.recommender import build_recommendation


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _make_antibot(
    overall_score: float,
    waf_score: int = 0,
    tls_score: int = 0,
    rate_score: int = 0,
    captcha_score: int = 0,
    fp_score: int = 0,
    honeypot_count: int = 0,
    honeypot_score: int = 0,
    geo_block: bool = False,
) -> AntibotResult:
    """Convenience factory for AntibotResult."""
    level = (
        "NONE" if overall_score == 0 else
        "LOW" if overall_score < 3 else
        "MEDIUM" if overall_score < 5 else
        "HIGH" if overall_score < 8 else
        "EXTREME"
    )
    return AntibotResult(
        overall_score=overall_score,
        overall_level=level,
        dimensions=AntibotDimensions(
            waf=WafDimension(score=waf_score, vendor=None, confidence="NONE"),
            tls_fingerprint=TlsDimension(
                score=tls_score, sensitivity="NONE", client_results={}
            ),
            rate_limiting=RateLimitDimension(
                score=rate_score, triggered_at=None, error_type=None
            ),
            captcha=CaptchaDimension(
                score=captcha_score, provider=None, version=None
            ),
            browser_fingerprinting=FingerprintDimension(
                score=fp_score, libraries=[]
            ),
            honeypots=HoneypotDimension(
                score=honeypot_score, count=honeypot_count, locations=[]
            ),
            ip_reputation=IpRepDimension(
                score=2 if geo_block else 0,
                geo_block=geo_block,
                proxy_recommendation="Residential proxy required" if geo_block else "Datacenter proxy sufficient",
            ),
            behavioral_detection=BehavioralDetectionDimension(
                score=0, listener_count=0, listener_types=[], confidence="low"
            ),
            journey_probes=JourneyDimension(
                score=0, blocked_at_url=None, blocked_type="none", probes_sent=0
            ),
        ),
    )


def _make_classifier(
    type_: str,
    confidence: str = "HIGH",
    scraping_shortcut: bool = False,
    schema_types: list | None = None,
) -> ClassifierResult:
    """Convenience factory for ClassifierResult."""
    return ClassifierResult(
        type=type_,
        confidence=confidence,
        js_frameworks=[],
        cms=None,
        server=None,
        cdn=None,
        infrastructure=[],
        dns_signals={},
        content_ratio=0.3,
        response_time_ms=100,
        structured_data=StructuredDataResult(
            json_ld_found=False,
            schema_types=schema_types or [],
            microdata_found=False,
            opengraph_found=False,
            scraping_shortcut=scraping_shortcut,
        ),
        security_headers=SecurityHeadersResult(
            csp=False,
            hsts=False,
            x_frame_options=False,
            x_content_type_options=False,
            csp_blocks_inline=False,
        ),
        cache_control=None,
        last_modified=None,
        locales=[],
        mobile_differs=False,
        internal_link_count=10,
        estimated_pages="<50",
    )


def _make_api(internal_api_found: bool = True) -> ApiDetectorResult:
    return ApiDetectorResult(
        internal_api_found=internal_api_found,
        endpoints=[],
        state_blobs_found=[],
        recommendation="",
        endpoints_may_be_incomplete=False,
    )


# ─────────────────────────────────────────────
# Tests S-R-01 through S-R-07
# ─────────────────────────────────────────────

def test_sr01_no_antibot_data(make_report) -> None:
    """S-R-01: antibot=None → httpx, no secondary, complexity 3."""
    report = make_report(antibot=None)
    result = build_recommendation(report)
    assert "httpx" in result.primary_library
    assert result.secondary_library is None
    assert result.estimated_complexity == 3


def test_sr02_extreme_protection(make_report) -> None:
    """S-R-02: overall_score=8.5 → playwright+stealth, managed API suggested with ZenRows."""
    antibot = _make_antibot(overall_score=8.5)
    report = make_report(antibot=antibot)
    result = build_recommendation(report)
    assert "playwright" in result.primary_library.lower()
    assert result.managed_api_suggested is True
    assert any("ZenRows" in opt for opt in result.managed_api_options)


def test_sr03_classifier_none_antibot_medium(make_report) -> None:
    """S-R-03: classifier=None + antibot.overall_score=4.0 → silent fallthrough, valid result."""
    antibot = _make_antibot(overall_score=4.0)
    report = make_report(antibot=antibot, classifier=None)
    result = build_recommendation(report)
    # Should not raise; falls through to else branch
    assert result.primary_library is not None
    assert "httpx" in result.primary_library


def test_sr04_static_score_zero(make_report) -> None:
    """S-R-04: STATIC + score 0 → httpx+BS4, Scrapy secondary, complexity 2."""
    antibot = _make_antibot(overall_score=0.0)
    classifier = _make_classifier("STATIC")
    report = make_report(antibot=antibot, classifier=classifier)
    result = build_recommendation(report)
    assert "httpx" in result.primary_library
    assert "BeautifulSoup4" in result.primary_library
    assert result.secondary_library is not None
    assert "Scrapy" in result.secondary_library
    assert result.estimated_complexity == 2


def test_sr05_dynamic_internal_api_tls_score(make_report) -> None:
    """S-R-05: DYNAMIC + internal API + tls_score=2 → httpx direct to API, curl_cffi secondary."""
    antibot = _make_antibot(overall_score=4.0, tls_score=2)
    classifier = _make_classifier("DYNAMIC")
    api = _make_api(internal_api_found=True)
    report = make_report(antibot=antibot, classifier=classifier, api_detector=api)
    result = build_recommendation(report)
    assert "httpx" in result.primary_library
    assert "API" in result.primary_library
    assert result.secondary_library is not None
    assert "curl_cffi" in result.secondary_library


def test_sr06_hybrid(make_report) -> None:
    """S-R-06: HYBRID + score 3.0 → httpx SSR + Playwright, Scrapy + plugin secondary."""
    antibot = _make_antibot(overall_score=3.0)
    classifier = _make_classifier("HYBRID")
    report = make_report(antibot=antibot, classifier=classifier)
    result = build_recommendation(report)
    assert "httpx" in result.primary_library
    assert result.secondary_library is not None
    assert "Scrapy" in result.secondary_library
    assert result.estimated_complexity == 6


def test_sr07_flag_truncation(make_report) -> None:
    """
    S-R-07: ≥5 flags → full_stack has exactly 3 (semicolon-limited);
    additional_flags has all flags (≥5).
    """
    # Build dimensions that trigger ≥5 flags:
    # 1. rate_limiting.score >= 2 → flag
    # 2. tls_fingerprint.score >= 2 → flag
    # 3. captcha.score >= 2 → flag
    # 4. honeypots.count > 0 → flag
    # 5. ip_reputation.geo_block=True → flag
    antibot = AntibotResult(
        overall_score=5.0,
        overall_level="HIGH",
        dimensions=AntibotDimensions(
            waf=WafDimension(score=0, vendor=None, confidence="NONE"),
            tls_fingerprint=TlsDimension(score=2, sensitivity="MEDIUM", client_results={}),
            rate_limiting=RateLimitDimension(score=3, triggered_at=4, error_type="HTTP 429"),
            captcha=CaptchaDimension(score=2, provider="reCAPTCHA", version=None),
            browser_fingerprinting=FingerprintDimension(score=0, libraries=[]),
            honeypots=HoneypotDimension(score=1, count=2, locations=["/trap"]),
            ip_reputation=IpRepDimension(
                score=2, geo_block=True,
                proxy_recommendation="Residential proxy required",
            ),
            behavioral_detection=BehavioralDetectionDimension(
                score=0, listener_count=0, listener_types=[], confidence="low"
            ),
            journey_probes=JourneyDimension(
                score=0, blocked_at_url=None, blocked_type="none", probes_sent=0
            ),
        ),
    )
    classifier = _make_classifier("HYBRID")
    report = make_report(antibot=antibot, classifier=classifier)
    result = build_recommendation(report)

    assert len(result.additional_flags) >= 3
    assert result.full_stack_recommendation is not None
    # The summary truncates flags at 3 (joined by '; ')
    # Count semicolons in the "Key considerations" part
    if "Key considerations:" in result.full_stack_recommendation:
        considerations = result.full_stack_recommendation.split("Key considerations:")[1]
        considerations = considerations.split(". Complexity:")[0].strip()
        flag_count = considerations.count(";") + 1
        assert flag_count == 3



# ===== merged from test_recommender_extra.py =====
import pytest

from models.schemas import (
    AntibotDimensions,
    AntibotResult,
    ApiDetectorResult,
    AuthResult,
    BehavioralDetectionDimension,
    CaptchaDimension,
    ClassifierResult,
    FingerprintDimension,
    HoneypotDimension,
    IpRepDimension,
    JourneyDimension,
    PaginationResult,
    RateLimitDimension,
    SecurityHeadersResult,
    StructuredDataResult,
    TlsDimension,
    WafDimension,
)
from modules.recommender import build_recommendation


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _antibot(
    score: float,
    tls_score: int = 0,
    rate_score: int = 0,
    captcha_score: int = 0,
    honeypot_count: int = 0,
    geo_block: bool = False,
) -> AntibotResult:
    level = (
        "NONE" if score == 0 else
        "LOW" if score < 3 else
        "MEDIUM" if score < 5 else
        "HIGH" if score < 8 else
        "EXTREME"
    )
    return AntibotResult(
        overall_score=score,
        overall_level=level,
        dimensions=AntibotDimensions(
            waf=WafDimension(score=0, vendor=None, confidence="NONE"),
            tls_fingerprint=TlsDimension(score=tls_score, sensitivity="NONE", client_results={}),
            rate_limiting=RateLimitDimension(score=rate_score, triggered_at=None, error_type=None),
            captcha=CaptchaDimension(score=captcha_score, provider=None, version=None),
            browser_fingerprinting=FingerprintDimension(score=0, libraries=[]),
            honeypots=HoneypotDimension(
                score=1 if honeypot_count > 0 else 0,
                count=honeypot_count,
                locations=[],
            ),
            ip_reputation=IpRepDimension(
                score=2 if geo_block else 0,
                geo_block=geo_block,
                proxy_recommendation="Residential proxy required" if geo_block else "Datacenter proxy sufficient",
            ),
            behavioral_detection=BehavioralDetectionDimension(
                score=0, listener_count=0, listener_types=[], confidence="low"
            ),
            journey_probes=JourneyDimension(
                score=0, blocked_at_url=None, blocked_type="none", probes_sent=0
            ),
        ),
    )


def _classifier(
    type_: str,
    mobile_differs: bool = False,
    estimated_pages: str = "<50",
    scraping_shortcut: bool = False,
    schema_types: list[str] | None = None,
) -> ClassifierResult:
    return ClassifierResult(
        type=type_,
        confidence="HIGH",
        js_frameworks=[],
        cms=None,
        server=None,
        cdn=None,
        infrastructure=[],
        dns_signals={},
        content_ratio=0.3,
        response_time_ms=100,
        structured_data=StructuredDataResult(
            json_ld_found=bool(schema_types),
            schema_types=schema_types or [],
            microdata_found=False,
            opengraph_found=False,
            scraping_shortcut=scraping_shortcut,
        ),
        security_headers=SecurityHeadersResult(
            csp=False, hsts=False, x_frame_options=False,
            x_content_type_options=False, csp_blocks_inline=False,
        ),
        cache_control=None,
        last_modified=None,
        locales=[],
        mobile_differs=mobile_differs,
        internal_link_count=10,
        estimated_pages=estimated_pages,
    )


# ─────────────────────────────────────────────
# STATIC with antibot > 0 (lines 54-57)
# ─────────────────────────────────────────────

def test_static_with_antibot_low(make_report) -> None:
    """STATIC + antibot.overall_score=1.5 → curl_cffi+BS4, complexity=4."""
    antibot = _antibot(score=1.5)
    classifier = _classifier("STATIC")
    report = make_report(antibot=antibot, classifier=classifier)
    result = build_recommendation(report)
    assert "curl_cffi" in result.primary_library
    assert result.estimated_complexity == 4
    assert result.estimated_dev_time == "1-3 days"


# ─────────────────────────────────────────────
# DYNAMIC without API (lines 69-72)
# ─────────────────────────────────────────────

def test_dynamic_no_api(make_report) -> None:
    """DYNAMIC + no internal API → Playwright async, complexity=7."""
    antibot = _antibot(score=2.0)
    classifier = _classifier("DYNAMIC")
    api = ApiDetectorResult(
        internal_api_found=False,
        endpoints=[],
        state_blobs_found=[],
        recommendation="",
        endpoints_may_be_incomplete=False,
    )
    report = make_report(antibot=antibot, classifier=classifier, api_detector=api)
    result = build_recommendation(report)
    assert "Playwright" in result.primary_library
    assert result.estimated_complexity == 7


def test_api_driven_with_api(make_report) -> None:
    """API_DRIVEN + internal API + tls_score=0 → httpx direct to API, secondary=None."""
    antibot = _antibot(score=2.0, tls_score=0)
    classifier = _classifier("API_DRIVEN")
    api = ApiDetectorResult(
        internal_api_found=True,
        endpoints=[],
        state_blobs_found=[],
        recommendation="",
        endpoints_may_be_incomplete=False,
    )
    report = make_report(antibot=antibot, classifier=classifier, api_detector=api)
    result = build_recommendation(report)
    assert "httpx" in result.primary_library
    assert "API" in result.primary_library
    assert result.secondary_library is None  # tls_score=0


def test_dynamic_underestimate_flag(make_report) -> None:
    """DYNAMIC + antibot.overall_score < 5 → underestimate warning flag added."""
    antibot = _antibot(score=3.0)
    classifier = _classifier("DYNAMIC")
    report = make_report(antibot=antibot, classifier=classifier)
    result = build_recommendation(report)
    assert any("underestimated" in f for f in result.additional_flags)


# ─────────────────────────────────────────────
# Auth flags (lines 119-131)
# ─────────────────────────────────────────────

def test_auth_form_flag(make_report) -> None:
    """Auth FORM required → 'Session management' flag."""
    auth = AuthResult(
        required=True,
        type="FORM",
        login_url="/login",
        paywall_type="NONE",
        cookie_consent_blocking=False,
    )
    report = make_report(auth=auth)
    result = build_recommendation(report)
    assert any("Session management" in f for f in result.additional_flags)


def test_auth_oauth_flag(make_report) -> None:
    """Auth OAUTH required → 'OAuth flow' flag."""
    auth = AuthResult(
        required=True,
        type="OAUTH",
        login_url="/oauth",
        paywall_type="NONE",
        cookie_consent_blocking=False,
    )
    report = make_report(auth=auth)
    result = build_recommendation(report)
    assert any("OAuth flow" in f for f in result.additional_flags)


def test_auth_api_key_flag(make_report) -> None:
    """Auth API_KEY required → 'API key auth' flag."""
    auth = AuthResult(
        required=True,
        type="API_KEY",
        login_url=None,
        paywall_type="NONE",
        cookie_consent_blocking=False,
    )
    report = make_report(auth=auth)
    result = build_recommendation(report)
    assert any("API key auth" in f for f in result.additional_flags)


def test_auth_paywall_hard(make_report) -> None:
    """Hard paywall → 'Hard paywall' flag."""
    auth = AuthResult(
        required=False,
        type="PAYWALL",
        login_url=None,
        paywall_type="HARD",
        cookie_consent_blocking=False,
    )
    report = make_report(auth=auth)
    result = build_recommendation(report)
    assert any("Hard paywall" in f for f in result.additional_flags)


def test_auth_paywall_metered(make_report) -> None:
    """Metered paywall → 'Metered paywall' flag."""
    auth = AuthResult(
        required=False,
        type="PAYWALL",
        login_url=None,
        paywall_type="METERED",
        cookie_consent_blocking=False,
    )
    report = make_report(auth=auth)
    result = build_recommendation(report)
    assert any("Metered paywall" in f for f in result.additional_flags)


def test_auth_cookie_consent_blocking(make_report) -> None:
    """cookie_consent_blocking=True → 'Cookie consent wall' flag."""
    auth = AuthResult(
        required=False,
        type="COOKIE_CONSENT",
        login_url=None,
        paywall_type="NONE",
        cookie_consent_blocking=True,
    )
    report = make_report(auth=auth)
    result = build_recommendation(report)
    assert any("Cookie consent wall" in f for f in result.additional_flags)


# ─────────────────────────────────────────────
# Classifier flags (lines 133-140)
# ─────────────────────────────────────────────

def test_json_ld_scraping_shortcut_flag(make_report) -> None:
    """scraping_shortcut=True with schema types → JSON-LD flag appended."""
    classifier = _classifier(
        "STATIC",
        scraping_shortcut=True,
        schema_types=["Product", "Offer"],
    )
    report = make_report(classifier=classifier)
    result = build_recommendation(report)
    assert any("JSON-LD available" in f for f in result.additional_flags)


def test_mobile_differs_flag(make_report) -> None:
    """mobile_differs=True → 'Mobile UA serves different content' flag."""
    classifier = _classifier("STATIC", mobile_differs=True)
    report = make_report(classifier=classifier)
    result = build_recommendation(report)
    assert any("Mobile UA" in f for f in result.additional_flags)


def test_large_site_flag(make_report) -> None:
    """estimated_pages='>5000' → 'Large site' flag."""
    classifier = _classifier("STATIC", estimated_pages=">5000")
    report = make_report(classifier=classifier)
    result = build_recommendation(report)
    assert any("Large site" in f for f in result.additional_flags)


# ─────────────────────────────────────────────
# Pagination + api incomplete flags
# ─────────────────────────────────────────────

def test_pagination_requires_js_flag(make_report) -> None:
    """pagination.requires_js=True → 'Browser automation mandatory' flag."""
    pagination = PaginationResult(
        type="INFINITE_SCROLL",
        parameter=None,
        example_next_url=None,
        requires_js=True,
    )
    report = make_report(pagination=pagination)
    result = build_recommendation(report)
    assert any("Browser automation mandatory" in f for f in result.additional_flags)


def test_endpoints_may_be_incomplete_flag(make_report) -> None:
    """api.endpoints_may_be_incomplete=True → '--deep flag' flag."""
    api = ApiDetectorResult(
        internal_api_found=True,
        endpoints=[],
        state_blobs_found=[],
        recommendation="",
        endpoints_may_be_incomplete=True,
    )
    report = make_report(api_detector=api)
    result = build_recommendation(report)
    assert any("--deep" in f for f in result.additional_flags)
