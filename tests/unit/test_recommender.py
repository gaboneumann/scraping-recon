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
