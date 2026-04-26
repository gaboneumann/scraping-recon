"""
tests/unit/test_antibot_extra.py
Additional pure-function coverage for modules/antibot.py.
Covers: _assess_ip_reputation (geo_block paths), _detect_waf (wafw00f success path),
_detect_fingerprinting (no match), _detect_captcha (no match).
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from bs4 import BeautifulSoup

from modules.antibot import (
    _assess_ip_reputation,
    _detect_captcha,
    _detect_fingerprinting,
    _detect_honeypots,
    _detect_waf,
)


# ─────────────────────────────────────────────
# _assess_ip_reputation
# ─────────────────────────────────────────────

def test_ip_reputation_geo_block_cf_ipcountry() -> None:
    """cf-ipcountry header → geo_block=True, score=2."""
    result = _assess_ip_reputation({"cf-ipcountry": "US"})
    assert result.geo_block is True
    assert result.score == 2
    assert "Residential" in result.proxy_recommendation


def test_ip_reputation_geo_block_x_geo_country() -> None:
    """x-geo-country header → geo_block=True."""
    result = _assess_ip_reputation({"x-geo-country": "DE"})
    assert result.geo_block is True


def test_ip_reputation_cache_miss() -> None:
    """x-cache: miss → geo_block=True (heuristic)."""
    result = _assess_ip_reputation({"x-cache": "miss"})
    assert result.geo_block is True


def test_ip_reputation_no_geo_block() -> None:
    """No geo-related headers → geo_block=False, score=0."""
    result = _assess_ip_reputation({"server": "nginx"})
    assert result.geo_block is False
    assert result.score == 0
    assert "Datacenter" in result.proxy_recommendation


# ─────────────────────────────────────────────
# _detect_waf — wafw00f success path
# ─────────────────────────────────────────────

def test_detect_waf_wafw00f_success(monkeypatch, tmp_path) -> None:
    """wafw00f returns JSON with detected=True → score=3, confidence=HIGH."""
    waf_data = [{"detected": True, "firewall": "Akamai", "url": "https://example.com"}]

    def mock_subprocess_run(cmd, capture_output, timeout):
        # Write fake JSON to the temp file path given in the command
        tmp_file = cmd[3]  # -o <path>
        Path(tmp_file).write_text(json.dumps(waf_data))
        result = MagicMock()
        result.returncode = 0
        return result

    monkeypatch.setattr("modules.antibot.subprocess.run", mock_subprocess_run)
    result = _detect_waf("https://example.com", {}, "")
    assert result.score == 3
    assert result.vendor == "Akamai"
    assert result.confidence == "HIGH"


def test_detect_waf_wafw00f_not_detected_falls_back(monkeypatch) -> None:
    """wafw00f returns detected=False → falls back to header detection (score=0 if no headers)."""
    waf_data = [{"detected": False, "firewall": "None", "url": "https://example.com"}]

    def mock_subprocess_run(cmd, capture_output, timeout):
        tmp_file = cmd[3]
        Path(tmp_file).write_text(json.dumps(waf_data))
        result = MagicMock()
        result.returncode = 0
        return result

    monkeypatch.setattr("modules.antibot.subprocess.run", mock_subprocess_run)
    result = _detect_waf("https://example.com", {}, "")
    # No headers either → score 0
    assert result.score == 0
    assert result.vendor is None


# ─────────────────────────────────────────────
# _detect_captcha — no match
# ─────────────────────────────────────────────

def test_detect_captcha_no_match() -> None:
    """HTML with no captcha signals → score=0, provider=None."""
    result = _detect_captcha("<html><body><p>Hello</p></body></html>")
    assert result.score == 0
    assert result.provider is None
    assert result.version is None


def test_detect_captcha_hcaptcha() -> None:
    """hcaptcha.com in HTML → provider=hCaptcha, score=2."""
    result = _detect_captcha('<script src="https://js.hcaptcha.com/1/api.js"></script>')
    assert result.score == 2
    assert result.provider == "hCaptcha"


def test_detect_captcha_funcaptcha() -> None:
    """funcaptcha.com in HTML → provider=FunCaptcha, score=3."""
    result = _detect_captcha('<script src="https://api.funcaptcha.com/fc/api.js"></script>')
    assert result.score == 3
    assert result.provider == "FunCaptcha"


# ─────────────────────────────────────────────
# _detect_fingerprinting — no match
# ─────────────────────────────────────────────

def test_detect_fingerprinting_no_match() -> None:
    """HTML with no fingerprinting signals → score=0, libraries=[]."""
    result = _detect_fingerprinting("<html><body>Hello</body></html>")
    assert result.score == 0
    assert result.libraries == []


def test_detect_fingerprinting_canvas_audio() -> None:
    """Canvas + AudioContext signals → multiple libs, score >= 2."""
    html = "<script>canvas.toDataURL(); new AudioContext();</script>"
    result = _detect_fingerprinting(html)
    assert result.score >= 2
    assert len(result.libraries) >= 2


# ─────────────────────────────────────────────
# _detect_honeypots — href captured
# ─────────────────────────────────────────────

def test_detect_honeypots_href_captured() -> None:
    """Honeypot links with href → locations list is populated."""
    html = (
        '<html><body>'
        '<div style="display:none"><a href="/trap-hidden">trap</a></div>'
        '</body></html>'
    )
    soup = BeautifulSoup(html, "lxml")
    result = _detect_honeypots(soup)
    assert result.count == 1
    assert "/trap-hidden" in result.locations[0]


def test_detect_honeypots_left_offscreen() -> None:
    """left:-9999 style → honeypot detected."""
    html = (
        '<html><body>'
        '<div style="left:-9999px"><a href="/offscreen">offscreen</a></div>'
        '</body></html>'
    )
    soup = BeautifulSoup(html, "lxml")
    result = _detect_honeypots(soup)
    assert result.count >= 1
