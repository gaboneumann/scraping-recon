"""
tests/unit/test_antibot_pure.py
Pure function tests for modules/antibot.py internal helpers.
All subprocess/TLS I/O is patched before calling sync helpers.
"""
import pytest
from unittest.mock import MagicMock
from bs4 import BeautifulSoup

from modules.antibot import (
    _detect_captcha,
    _detect_fingerprinting,
    _detect_honeypots,
    _detect_waf,
)


# ── S-A-01 — WAF: cf-ray header → Cloudflare ───────────────────────────────

def test_detect_waf_cloudflare(monkeypatch) -> None:
    """
    cf-ray header with subprocess.run patched to raise FileNotFoundError →
    falls back to header detection → score==3, vendor=Cloudflare.
    """
    monkeypatch.setattr(
        "modules.antibot.subprocess.run",
        MagicMock(side_effect=FileNotFoundError("wafw00f not found")),
    )
    result = _detect_waf("https://example.com", {"cf-ray": "abc-SJC"}, "")
    assert result.score == 3
    assert result.vendor == "Cloudflare"
    assert result.confidence == "MEDIUM"


# ── S-A-02 — Captcha: Turnstile → score 3; reCAPTCHA v2 → score 2 ──────────

@pytest.mark.parametrize(
    "html, expected_score, expected_provider",
    [
        # Turnstile
        (
            '<script src="https://challenges.cloudflare.com/turnstile/v0/api.js"></script>',
            3,
            "Turnstile",
        ),
        # reCAPTCHA v2 (data-sitekey)
        (
            '<div class="g-recaptcha" data-sitekey="6Lc_test_key"></div>',
            2,
            "reCAPTCHA",
        ),
    ],
)
def test_detect_captcha(html: str, expected_score: int, expected_provider: str) -> None:
    """Captcha signals map to the correct score and provider."""
    result = _detect_captcha(html)
    assert result.score == expected_score
    assert result.provider == expected_provider


# ── S-A-03 — Fingerprinting: multiple libraries → max score ────────────────

def test_detect_fingerprinting_multiple() -> None:
    """HTML with fpjs.io (score 2) AND navigator.webdriver (score 3) → score 3, ≥2 libs."""
    html = (
        '<script src="https://fpcdn.io/v3/fpjs.js"></script>'
        '<script src="https://fpjs.io/agent?api=1"></script>'
        "<script>if(navigator.webdriver){throw new Error('bot');}</script>"
    )
    result = _detect_fingerprinting(html)
    assert result.score == 3
    assert len(result.libraries) >= 2


# ── S-A-04 — Honeypots: count → score boundaries ───────────────────────────

def _make_soup_with_hidden_links(count: int) -> BeautifulSoup:
    """Build minimal BeautifulSoup with N hidden anchors."""
    links = "".join(
        f'<div style="display:none"><a href="/trap-{i}">trap</a></div>'
        for i in range(count)
    )
    return BeautifulSoup(f"<html><body>{links}</body></html>", "lxml")


@pytest.mark.parametrize(
    "count, expected_score",
    [
        (0, 0),
        (1, 1),
        (2, 1),
        (3, 2),
        (5, 2),
        (6, 3),
    ],
)
def test_detect_honeypots_boundaries(count: int, expected_score: int) -> None:
    """Hidden link count maps to the correct honeypot score."""
    soup = _make_soup_with_hidden_links(count)
    result = _detect_honeypots(soup)
    assert result.score == expected_score
