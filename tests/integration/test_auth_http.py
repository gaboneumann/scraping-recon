"""
tests/integration/test_auth_http.py
Integration tests for modules/auth_detector.py using html= param (no HTTP).
"""
from pathlib import Path

import pytest

from modules.auth_detector import detect_auth

FIXTURES = Path(__file__).parent.parent / "fixtures" / "html"


@pytest.mark.asyncio
async def test_auth_login_form():
    """Login-gated page with password input → required=True, type=FORM."""
    html = (FIXTURES / "login_form.html").read_text()
    result = await detect_auth("https://example.com", 15.0, html=html)

    assert result.required is True
    assert result.type == "FORM"


@pytest.mark.asyncio
async def test_auth_paywall_hard():
    """Hard paywall page → required=True, paywall_type=HARD."""
    html = (FIXTURES / "paywall_hard.html").read_text()
    result = await detect_auth("https://example.com", 15.0, html=html)

    assert result.required is True
    assert result.paywall_type == "HARD"


@pytest.mark.asyncio
async def test_auth_cookie_consent_blocking():
    """OneTrust consent wall with overflow:hidden → cookie_consent_blocking=True."""
    html = (FIXTURES / "onetrust_consent.html").read_text()
    result = await detect_auth("https://example.com", 15.0, html=html)

    assert result.cookie_consent_blocking is True


@pytest.mark.asyncio
async def test_auth_static_blog_clean():
    """Static blog with no auth signals → required=False."""
    html = (FIXTURES / "static_blog.html").read_text()
    result = await detect_auth("https://example.com", 15.0, html=html)

    assert result.required is False
    assert result.paywall_type == "NONE"
    assert result.cookie_consent_blocking is False
