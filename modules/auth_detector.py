"""
modules/auth_detector.py
Detects authentication requirements: login walls, OAuth, API keys,
paywalls (hard/metered), and cookie consent blocking.
Reuses the base fetch from classifier when possible.
"""
from __future__ import annotations

import logging
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from models.schemas import AuthResult
from utils.http import UA_CHROME, make_request

logger = logging.getLogger(__name__)

LOGIN_FORM_SELECTORS = [
    'input[type="password"]',
    'form[action*="login"]',
    'form[action*="signin"]',
    'form[action*="session"]',
]

LOGIN_LINK_PATTERNS = ["/login", "/signin", "/auth", "/account/login"]

OAUTH_DOMAINS = [
    "accounts.google.com",
    "facebook.com/login",
    "twitter.com/oauth",
    "github.com/login/oauth",
    "login.microsoftonline.com",
    "appleid.apple.com",
]

PAYWALL_HARD_SIGNALS = [
    "subscribe to read", "subscribers only", "sign up to continue",
    "create an account to", "members only", "premium content",
    "exclusive content", "subscription required",
]

PAYWALL_METERED_SIGNALS = [
    "articles remaining", "free articles left", "monthly limit",
    "you have read", "stories this month", "free reads",
]

CONSENT_SIGNALS: dict[str, list[str]] = {
    "OneTrust":  ["onetrust-banner-sdk", "onetrust-accept-btn-handler"],
    "Cookiebot": ["CybotCookiebotDialog"],
    "TrustArc":  ["truste-consent-track"],
    "Quantcast": ["qc-cmp2-ui"],
    "Generic":   ["cookie-consent", "cookie-banner", "gdpr-banner", "cookies-banner"],
}


async def detect_auth(
    url: str,
    timeout: float = 15.0,
    html: str | None = None,
    headers: dict | None = None,
    redirect_chain: list[str] | None = None,
) -> AuthResult:
    """
    Detect authentication requirements for the target URL.
    Accepts pre-fetched html/headers to avoid a duplicate request.
    """
    if html is None:
        status, headers, html, _ = await make_request(url, ua=UA_CHROME, timeout=timeout)
        if status == 401:
            h = {k.lower(): v for k, v in (headers or {}).items()}
            if "www-authenticate" in h:
                return AuthResult(
                    required=True,
                    type="API_KEY",
                    login_url=None,
                    paywall_type="NONE",
                    cookie_consent_blocking=False,
                )

    soup = BeautifulSoup(html, "lxml")
    html_lower = html.lower()
    headers = headers or {}
    h = {k.lower(): v for k, v in headers.items()}

    # Check redirect chain for OAuth domains
    if redirect_chain:
        for redirect_url in redirect_chain:
            if any(domain in redirect_url for domain in OAUTH_DOMAINS):
                return AuthResult(
                    required=True,
                    type="OAUTH",
                    login_url=redirect_url,
                    paywall_type="NONE",
                    cookie_consent_blocking=_detect_consent(soup, html),
                )

    # Login form detection — only flag required if a password form
    # is the dominant element (login-gated page, not optional login)
    auth_type = "NONE"
    login_url: str | None = None
    required = False

    password_inputs = soup.select('input[type="password"]')
    if password_inputs:
        main_content = soup.find("article") or soup.find("main")
        main_words = len(main_content.get_text().split()) if main_content else 0
        # A login-gated page has very little non-form content
        if main_words < 100:
            required = True
            auth_type = "FORM"
        else:
            # Login form present but content is accessible — note the URL
            auth_type = "FORM"
        form = soup.find("form")
        if form and form.get("action"):
            action = form["action"]
            if not action.startswith("http"):
                base = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
                action = base + action
            login_url = action

    # Paywall detection
    paywall_type: str = "NONE"
    main_content = soup.find("article") or soup.find("main") or soup
    visible_words = len(main_content.get_text().split()) if main_content else 0

    if any(signal in html_lower for signal in PAYWALL_HARD_SIGNALS):
        if visible_words < 200:
            paywall_type = "HARD"
            required = True
            auth_type = "PAYWALL"
    elif any(signal in html_lower for signal in PAYWALL_METERED_SIGNALS):
        paywall_type = "METERED"
        required = True
        auth_type = "PAYWALL"

    cookie_consent_blocking = _detect_consent(soup, html)

    return AuthResult(
        required=required,
        type=auth_type,
        login_url=login_url,
        paywall_type=paywall_type,
        cookie_consent_blocking=cookie_consent_blocking,
    )


def _detect_consent(soup: BeautifulSoup, html: str) -> bool:
    """Return True if a cookie consent wall is present and blocking."""
    html_lower = html.lower()
    for provider, signals in CONSENT_SIGNALS.items():
        if any(sig.lower() in html_lower for sig in signals):
            # Check if body has overflow:hidden or banner has fixed position
            body = soup.find("body")
            body_style = (body.get("style") or "") if body else ""
            if "overflow" in body_style and "hidden" in body_style:
                return True
            # Check for high z-index fixed elements
            for tag in soup.find_all(style=True):
                style = tag["style"].lower()
                if "position" in style and "fixed" in style:
                    if "z-index" in style:
                        try:
                            z = int(re.search(r'z-index:\s*(\d+)', style).group(1))
                            if z > 999:
                                return True
                        except (AttributeError, ValueError):
                            pass
            # Consent element present — assume blocking
            return True
    return False


import re
