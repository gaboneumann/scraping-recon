"""
tests/unit/test_schemas.py
Pydantic round-trip and validation tests for models/schemas.py.
"""
import pytest
from pydantic import ValidationError

from models.schemas import (
    AntibotDimensions,
    AntibotResult,
    CaptchaDimension,
    ClassifierResult,
    FingerprintDimension,
    HoneypotDimension,
    IpRepDimension,
    RateLimitDimension,
    ReconReport,
    RecommenderResult,
    SecurityHeadersResult,
    StructuredDataResult,
    TlsDimension,
    WafDimension,
)


def _minimal_recon_report() -> ReconReport:
    """Build the smallest valid ReconReport."""
    return ReconReport(
        url="https://example.com",
        timestamp="2026-01-01T00:00:00Z",
        scan_duration_ms=42,
        modules_status=[],
    )


# ── Round-trip ──────────────────────────────────────────────────────────────

def test_recon_report_round_trip() -> None:
    """model_dump() → ReconReport(**dump) must produce an equal object."""
    report = _minimal_recon_report()
    dump = report.model_dump()
    rebuilt = ReconReport(**dump)
    assert rebuilt.model_dump() == dump


def test_recon_report_optional_fields_none() -> None:
    """All optional module fields default to None."""
    report = _minimal_recon_report()
    assert report.legal is None
    assert report.classifier is None
    assert report.auth is None
    assert report.api_detector is None
    assert report.pagination is None
    assert report.antibot is None
    assert report.recommender is None


# ── ValidationError: AntibotDimension score out of range ───────────────────

def test_waf_dimension_score_max() -> None:
    """WafDimension(score=3) is valid — boundary value."""
    dim = WafDimension(score=3, vendor="Test", confidence="HIGH")
    assert dim.score == 3


def test_waf_dimension_score_over_max_raises() -> None:
    """WafDimension(score=4) must raise ValidationError (ge=0, le=3)."""
    with pytest.raises(ValidationError):
        WafDimension(score=4, vendor=None, confidence="NONE")


def test_tls_dimension_score_over_max_raises() -> None:
    """TlsDimension(score=5) must raise ValidationError."""
    with pytest.raises(ValidationError):
        TlsDimension(score=5, sensitivity="HIGH", client_results={})


def test_antibot_result_score_over_max_raises() -> None:
    """AntibotResult(overall_score=10.1) must raise ValidationError (le=10.0)."""
    with pytest.raises(ValidationError):
        AntibotResult(
            overall_score=10.1,
            overall_level="EXTREME",
            dimensions=AntibotDimensions(
                waf=WafDimension(score=0, vendor=None, confidence="NONE"),
                tls_fingerprint=TlsDimension(score=0, sensitivity="NONE", client_results={}),
                rate_limiting=RateLimitDimension(score=0, triggered_at=None, error_type=None),
                captcha=CaptchaDimension(score=0, provider=None, version=None),
                browser_fingerprinting=FingerprintDimension(score=0, libraries=[]),
                honeypots=HoneypotDimension(score=0, count=0, locations=[]),
                ip_reputation=IpRepDimension(
                    score=0, geo_block=False,
                    proxy_recommendation="Datacenter proxy sufficient",
                ),
            ),
        )


def test_recommender_result_complexity_bounds() -> None:
    """estimated_complexity must be 1..10; out-of-range raises ValidationError."""
    with pytest.raises(ValidationError):
        RecommenderResult(
            primary_library="httpx",
            secondary_library=None,
            managed_api_suggested=False,
            managed_api_options=[],
            additional_flags=[],
            estimated_complexity=11,
            estimated_dev_time="1 day",
            full_stack_recommendation="Use httpx.",
        )
