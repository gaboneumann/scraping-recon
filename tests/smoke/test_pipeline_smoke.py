"""
tests/smoke/test_pipeline_smoke.py
Full-pipeline smoke tests: build a realistic ReconReport from HTML fixture content
and call build_recommendation(). On first run, writes a JSON snapshot; subsequent
runs assert the result matches the snapshot.

Run with UPDATE_SNAPSHOTS=1 to force-rewrite all snapshots.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

from models.schemas import (
    AntibotDimensions,
    AntibotResult,
    ApiDetectorResult,
    AuthResult,
    CaptchaDimension,
    ClassifierResult,
    EcommerceSignals,
    FingerprintDimension,
    HoneypotDimension,
    IpRepDimension,
    LegalResult,
    PaginationResult,
    RateLimitDimension,
    ReconReport,
    RobotsTxtResult,
    SecurityHeadersResult,
    SitemapResult,
    StructuredDataResult,
    TlsDimension,
    TosResult,
    WafDimension,
)
from modules.recommender import build_recommendation

# ─────────────────────────────────────────────────────────────────────────────
# Snapshot helper
# ─────────────────────────────────────────────────────────────────────────────

SNAPSHOTS_DIR = Path(__file__).parent.parent / "fixtures" / "snapshots"
FIXTURES_HTML = Path(__file__).parent.parent / "fixtures" / "html"


def _load_html(name: str) -> str:
    return (FIXTURES_HTML / f"{name}.html").read_text(encoding="utf-8")


def check_or_write_snapshot(name: str, data: dict) -> None:
    """Write snapshot on first run (or UPDATE_SNAPSHOTS=1); assert match otherwise."""
    path = SNAPSHOTS_DIR / f"{name}.json"
    if os.environ.get("UPDATE_SNAPSHOTS") or not path.exists():
        SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, default=str))
        return
    snapshot = json.loads(path.read_text())
    assert data == snapshot, f"Snapshot mismatch for {name}"


# ─────────────────────────────────────────────────────────────────────────────
# Sub-model factories (shared across archetypes)
# ─────────────────────────────────────────────────────────────────────────────

def _make_legal_minimal() -> LegalResult:
    return LegalResult(
        robots_txt=RobotsTxtResult(
            found=True,
            ua_specific=False,
            crawl_delay_seconds=None,
            target_path_allowed=True,
            blocked_paths=[],
            sitemap_declared=None,
        ),
        sitemap=SitemapResult(
            found=False,
            type="NONE",
            url_count=None,
            last_modified=None,
        ),
        tos=TosResult(
            found=False,
            url=None,
            risk_level="UNKNOWN",
            flagged_keywords=[],
        ),
    )


def _make_structured_data(
    json_ld_found: bool = False,
    schema_types: list[str] | None = None,
    scraping_shortcut: bool = False,
) -> StructuredDataResult:
    return StructuredDataResult(
        json_ld_found=json_ld_found,
        schema_types=schema_types or [],
        microdata_found=False,
        opengraph_found=False,
        scraping_shortcut=scraping_shortcut,
    )


def _make_security_headers() -> SecurityHeadersResult:
    return SecurityHeadersResult(
        csp=False,
        hsts=False,
        x_frame_options=False,
        x_content_type_options=False,
        csp_blocks_inline=False,
    )


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
) -> AntibotResult:
    score = overall_score
    level = (
        "NONE" if score == 0.0 else
        "LOW" if score < 3.0 else
        "MEDIUM" if score < 5.0 else
        "HIGH" if score < 8.0 else
        "EXTREME"
    )
    return AntibotResult(
        overall_score=score,
        overall_level=level,
        dimensions=AntibotDimensions(
            waf=WafDimension(score=waf_score, vendor=waf_vendor, confidence="NONE" if waf_score == 0 else "HIGH"),
            tls_fingerprint=TlsDimension(score=tls_score, sensitivity="NONE", client_results={}),
            rate_limiting=RateLimitDimension(score=rate_score, triggered_at=None, error_type=None),
            captcha=CaptchaDimension(score=captcha_score, provider=None, version=None),
            browser_fingerprinting=FingerprintDimension(score=fp_score, libraries=[]),
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
        ),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Archetype report builders
# ─────────────────────────────────────────────────────────────────────────────

def _build_static_blog_report() -> ReconReport:
    """static_blog.html — Article JSON-LD, no JS framework, no antibot."""
    # HTML has Article JSON-LD — scraping_shortcut=True
    return ReconReport(
        url="https://blog.example.com/",
        timestamp=datetime(2026, 4, 25, 12, 0, 0, tzinfo=timezone.utc).isoformat(),
        scan_duration_ms=420,
        modules_status=[],
        legal=_make_legal_minimal(),
        classifier=ClassifierResult(
            type="STATIC",
            confidence="HIGH",
            js_frameworks=[],
            cms="WordPress",
            server="nginx",
            cdn=None,
            infrastructure=[],
            dns_signals={},
            content_ratio=0.85,
            response_time_ms=120,
            structured_data=_make_structured_data(
                json_ld_found=True,
                schema_types=["Article"],
                scraping_shortcut=True,
            ),
            security_headers=_make_security_headers(),
            cache_control="max-age=3600",
            last_modified=None,
            locales=["en"],
            mobile_differs=False,
            internal_link_count=20,
            estimated_pages="50-500",
        ),
        auth=AuthResult(
            required=False,
            type="NONE",
            login_url=None,
            paywall_type="NONE",
            cookie_consent_blocking=False,
        ),
        api_detector=ApiDetectorResult(
            internal_api_found=False,
            endpoints=[],
            state_blobs_found=[],
            recommendation="No API detected",
            endpoints_may_be_incomplete=False,
        ),
        pagination=PaginationResult(
            type="LINK_REL_NEXT",
            parameter=None,
            example_next_url=None,
            requires_js=False,
        ),
        antibot=_make_antibot(overall_score=0.0),
        recommender=None,
    )


def _build_shopify_pdp_report() -> ReconReport:
    """shopify_pdp.html — Product JSON-LD, Shopify CMS, ecommerce=True, low antibot."""
    return ReconReport(
        url="https://shop.example.com/products/test-widget",
        timestamp=datetime(2026, 4, 25, 12, 0, 0, tzinfo=timezone.utc).isoformat(),
        scan_duration_ms=650,
        modules_status=[],
        legal=_make_legal_minimal(),
        classifier=ClassifierResult(
            type="HYBRID",
            confidence="HIGH",
            js_frameworks=[],
            cms="Shopify",
            server="nginx",
            cdn="Cloudflare",
            infrastructure=["Shopify"],
            dns_signals={},
            content_ratio=0.5,
            response_time_ms=250,
            structured_data=_make_structured_data(
                json_ld_found=True,
                schema_types=["Product"],
                scraping_shortcut=True,
            ),
            security_headers=_make_security_headers(),
            cache_control=None,
            last_modified=None,
            locales=["en"],
            mobile_differs=False,
            internal_link_count=15,
            estimated_pages="50-500",
            ecommerce=EcommerceSignals(
                is_ecommerce=True,
                platform="Shopify",
                price_mechanism="SERVER_SIDE",
                cart_architecture="AJAX_API",
                has_faceted_nav=False,
                has_product_schema=True,
                signal_counts={"product_schema": 1, "price_element": 1, "cart_button": 1},
            ),
            is_ecommerce_platform=True,
        ),
        auth=AuthResult(
            required=False,
            type="NONE",
            login_url=None,
            paywall_type="NONE",
            cookie_consent_blocking=False,
        ),
        api_detector=ApiDetectorResult(
            internal_api_found=True,
            endpoints=[],
            state_blobs_found=["window.Shopify"],
            recommendation="Shopify Storefront API may be available",
            endpoints_may_be_incomplete=False,
        ),
        pagination=PaginationResult(
            type="NONE",
            parameter=None,
            example_next_url=None,
            requires_js=False,
        ),
        antibot=_make_antibot(overall_score=2.0, waf_score=1, waf_vendor="Cloudflare"),
        recommender=None,
    )


def _build_cloudflare_gated_report() -> ReconReport:
    """cloudflare_gated.html — Cloudflare challenge page, high antibot score."""
    return ReconReport(
        url="https://protected.example.com/",
        timestamp=datetime(2026, 4, 25, 12, 0, 0, tzinfo=timezone.utc).isoformat(),
        scan_duration_ms=3100,
        modules_status=[],
        legal=_make_legal_minimal(),
        classifier=ClassifierResult(
            type="DYNAMIC",
            confidence="HIGH",
            js_frameworks=[],
            cms=None,
            server=None,
            cdn="Cloudflare",
            infrastructure=["Cloudflare"],
            dns_signals={},
            content_ratio=0.1,
            response_time_ms=1200,
            structured_data=_make_structured_data(),
            security_headers=SecurityHeadersResult(
                csp=True,
                hsts=True,
                x_frame_options=True,
                x_content_type_options=True,
                csp_blocks_inline=True,
            ),
            cache_control=None,
            last_modified=None,
            locales=[],
            mobile_differs=False,
            internal_link_count=0,
            estimated_pages="UNKNOWN",
        ),
        auth=AuthResult(
            required=False,
            type="UNKNOWN",
            login_url=None,
            paywall_type="NONE",
            cookie_consent_blocking=False,
        ),
        api_detector=ApiDetectorResult(
            internal_api_found=False,
            endpoints=[],
            state_blobs_found=[],
            recommendation="No API detected — Cloudflare challenge page intercepted",
            endpoints_may_be_incomplete=True,
        ),
        pagination=PaginationResult(
            type="UNKNOWN",
            parameter=None,
            example_next_url=None,
            requires_js=True,
        ),
        antibot=_make_antibot(
            overall_score=6.0,
            waf_score=3,
            waf_vendor="Cloudflare",
            tls_score=2,
            rate_score=1,
            fp_score=2,
        ),
        recommender=None,
    )


def _build_consent_onetrust_report() -> ReconReport:
    """onetrust_consent.html — OneTrust cookie banner blocking content, low antibot."""
    return ReconReport(
        url="https://consented.example.com/",
        timestamp=datetime(2026, 4, 25, 12, 0, 0, tzinfo=timezone.utc).isoformat(),
        scan_duration_ms=390,
        modules_status=[],
        legal=_make_legal_minimal(),
        classifier=ClassifierResult(
            type="STATIC",
            confidence="HIGH",
            js_frameworks=[],
            cms=None,
            server="Apache",
            cdn=None,
            infrastructure=[],
            dns_signals={},
            content_ratio=0.6,
            response_time_ms=180,
            structured_data=_make_structured_data(),
            security_headers=_make_security_headers(),
            cache_control=None,
            last_modified=None,
            locales=["en"],
            mobile_differs=False,
            internal_link_count=5,
            estimated_pages="<50",
        ),
        auth=AuthResult(
            required=False,
            type="COOKIE_CONSENT",
            login_url=None,
            paywall_type="NONE",
            cookie_consent_blocking=True,
        ),
        api_detector=ApiDetectorResult(
            internal_api_found=False,
            endpoints=[],
            state_blobs_found=[],
            recommendation="No API detected",
            endpoints_may_be_incomplete=False,
        ),
        pagination=PaginationResult(
            type="NONE",
            parameter=None,
            example_next_url=None,
            requires_js=False,
        ),
        antibot=_make_antibot(overall_score=1.0, waf_score=0),
        recommender=None,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Parametrized smoke test
# ─────────────────────────────────────────────────────────────────────────────

_ARCHETYPES = [
    ("static_blog", _build_static_blog_report),
    ("shopify_pdp", _build_shopify_pdp_report),
    ("cloudflare_gated", _build_cloudflare_gated_report),
    ("consent_onetrust", _build_consent_onetrust_report),
]


@pytest.mark.smoke
@pytest.mark.parametrize("case,builder", _ARCHETYPES, ids=[a[0] for a in _ARCHETYPES])
def test_pipeline_smoke(case: str, builder) -> None:
    """
    Build a full ReconReport for the archetype, call build_recommendation(),
    and compare the result against a JSON snapshot.
    """
    report = builder()
    result = build_recommendation(report)

    # Verify result is a well-formed RecommenderResult
    assert result.primary_library, f"{case}: primary_library must be non-empty"
    assert result.estimated_complexity >= 1
    assert result.estimated_complexity <= 10
    assert result.full_stack_recommendation, f"{case}: full_stack_recommendation must be non-empty"

    # Snapshot check
    check_or_write_snapshot(case, result.model_dump())
