"""
tests/unit/test_auth_pure.py
Pure function tests for modules/auth_detector.py internal helpers.
"""
import pytest
from bs4 import BeautifulSoup

from modules.auth_detector import _detect_consent


def _soup_and_html(raw: str):
    """Helper: return (soup, html) from raw HTML string."""
    return BeautifulSoup(raw, "lxml"), raw


# ── S-A-05 — Consent detection ─────────────────────────────────────────────

@pytest.mark.parametrize(
    "html, expected",
    [
        # OneTrust banner + overflow:hidden → True
        (
            '<html><head></head>'
            '<body style="overflow: hidden">'
            '<div id="onetrust-banner-sdk">Accept cookies</div>'
            '</body></html>',
            True,
        ),
        # OneTrust banner + fixed element with z-index > 999 → True
        (
            '<html><head></head><body>'
            '<div id="onetrust-banner-sdk">Consent</div>'
            '<div style="position: fixed; z-index: 1000">Banner</div>'
            '</body></html>',
            True,
        ),
        # OneTrust banner + fixed element with z-index <= 999 →
        # consent element present so fallback returns True
        (
            '<html><head></head><body>'
            '<div id="onetrust-banner-sdk">Consent</div>'
            '<div style="position: fixed; z-index: 100">Banner</div>'
            '</body></html>',
            True,
        ),
        # No consent signals → False
        (
            '<html><head></head><body><p>Clean page, no banners.</p></body></html>',
            False,
        ),
    ],
)
def test_detect_consent(html: str, expected: bool) -> None:
    """_detect_consent returns the expected boolean for each HTML variant."""
    soup, raw = _soup_and_html(html)
    assert _detect_consent(soup, raw) is expected
