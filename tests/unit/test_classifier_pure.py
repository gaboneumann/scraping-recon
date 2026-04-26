"""
tests/unit/test_classifier_pure.py
Pure function tests for modules/classifier.py internal helpers.
No I/O — all functions are synchronous.
"""
import pytest
from bs4 import BeautifulSoup

from modules.classifier import (
    _classify,
    _detect_cms,
    _detect_ecommerce_signals,
    _detect_structured_data,
)


# ── S-C-01 — _classify() threshold boundaries ──────────────────────────────

@pytest.mark.parametrize(
    "content_ratio, js_frameworks, cms, expected_type",
    [
        # Below 0.05 → API_DRIVEN regardless of frameworks or CMS
        (0.049, [], None, "API_DRIVEN"),
        # Between 0.05 and 0.08, no frameworks, no special CMS → UNKNOWN
        (0.051, [], None, "UNKNOWN"),
        # Between 0.08 and 0.15, no frameworks → STATIC MEDIUM
        (0.099, [], None, "STATIC"),
        # Next.js + ratio >= 0.10 → HYBRID
        (0.101, ["Next.js"], None, "HYBRID"),
        # WordPress is NOT in SSR_ECOMMERCE or headless → falls through to STATIC
        (0.149, [], "WordPress", "STATIC"),
        # >= 0.15, no frameworks → STATIC HIGH
        (0.151, [], None, "STATIC"),
    ],
)
def test_classify_thresholds(
    content_ratio: float,
    js_frameworks: list,
    cms: str | None,
    expected_type: str,
) -> None:
    """_classify() returns the expected type for each threshold boundary."""
    result_type, _confidence = _classify(content_ratio, js_frameworks, cms)
    assert result_type == expected_type


# ── S-C-02 — _detect_ecommerce_signals() price mechanism ───────────────────

def test_ecommerce_price_empty_vs_zero() -> None:
    """Empty data-price attr → CLIENT_SIDE; data-price="0" → SERVER_SIDE."""
    # Empty attribute — regex matches empty string between quotes
    html_empty = '<div data-price="" class="price">Loading...</div>'
    soup_empty = BeautifulSoup(html_empty, "lxml")
    result_empty = _detect_ecommerce_signals(html_empty, soup_empty, None)
    assert result_empty.price_mechanism == "CLIENT_SIDE"

    # data-price="0" — zero is a non-empty value; regex does not match → SERVER_SIDE
    html_zero = '<div data-price="0" class="price">$0.00</div>'
    soup_zero = BeautifulSoup(html_zero, "lxml")
    result_zero = _detect_ecommerce_signals(html_zero, soup_zero, None)
    assert result_zero.price_mechanism != "CLIENT_SIDE"


# ── S-C-03 — _detect_structured_data() malformed JSON-LD ───────────────────

def test_structured_data_malformed_json() -> None:
    """Malformed JSON-LD must not raise; json_ld_found=True, schema_types=[]."""
    html = '<html><head><script type="application/ld+json">{ broken json</script></head><body></body></html>'
    soup = BeautifulSoup(html, "lxml")
    result = _detect_structured_data(soup, html)
    assert result.json_ld_found is True
    assert result.schema_types == []


# ── S-C-04 — _detect_cms() header case-insensitivity ───────────────────────

def test_detect_cms_header_case() -> None:
    """Mixed-case X-Drupal-Cache header must resolve to 'Drupal'."""
    cms = _detect_cms("", {"X-Drupal-Cache": "HIT"})
    assert cms == "Drupal"
