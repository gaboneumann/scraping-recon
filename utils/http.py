"""
utils/http.py
HTTP client factory for scraping_recon.
Centralizes all request logic — no state, all config explicit.
"""
from __future__ import annotations

import asyncio
import time
import logging
from typing import Any

import httpx

try:
    from curl_cffi.requests import AsyncSession as CurlSession
    TLS_IMPERSONATION_AVAILABLE = True
except ImportError:
    TLS_IMPERSONATION_AVAILABLE = False

logger = logging.getLogger(__name__)

UA_PYTHON    = "python-httpx/0.27"
UA_GOOGLEBOT = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
UA_CHROME    = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
UA_MOBILE    = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"

WAF_BODY_SIGNALS = [
    "access denied", "blocked", "captcha", "cloudflare",
    "ddos protection", "security check", "ray id",
]

MAX_CONTENT_BYTES = 5 * 1024 * 1024  # 5MB


async def make_request(
    url: str,
    ua: str = UA_CHROME,
    timeout: float = 15.0,
    verify_ssl: bool = True,
    impersonate: str | None = None,
) -> tuple[int, dict[str, str], str, int]:
    """
    Fetch a URL and return (status_code, headers, text, response_time_ms).
    Retries twice on ConnectionError/TimeoutError with 1s backoff.
    Falls back to verify_ssl=False on SSL errors.
    Follows redirects up to 10, logging the redirect chain.
    """
    headers = {"User-Agent": ua}
    redirect_chain: list[str] = []

    async def _do_request(verify: bool) -> tuple[int, dict, str, int]:
        if impersonate and TLS_IMPERSONATION_AVAILABLE:
            return await _curl_request(url, ua, timeout, verify, impersonate)
        return await _httpx_request(url, headers, timeout, verify, redirect_chain)

    for attempt in range(3):
        try:
            status, resp_headers, text, ms = await _do_request(verify_ssl)
            if redirect_chain:
                logger.debug("Redirect chain: %s", " -> ".join(redirect_chain))
            return status, resp_headers, text, ms
        except httpx.ConnectError as e:
            if "SSL" in str(e) or "certificate" in str(e).lower():
                logger.warning("SSL error for %s — retrying with verify=False", url)
                return await _do_request(verify=False)
            if attempt < 2:
                await asyncio.sleep(1.0)
            else:
                raise
        except httpx.TimeoutException:
            if attempt < 2:
                await asyncio.sleep(1.0)
            else:
                raise


async def _httpx_request(
    url: str,
    headers: dict,
    timeout: float,
    verify: bool,
    redirect_chain: list[str],
) -> tuple[int, dict, str, int]:
    """Internal httpx fetch with redirect tracking and content size limit."""
    start = time.monotonic()
    async with httpx.AsyncClient(
        headers=headers,
        timeout=timeout,
        verify=verify,
        follow_redirects=True,
        max_redirects=10,
    ) as client:
        async with client.stream("GET", url) as response:
            for r in response.history:
                redirect_chain.append(str(r.url))
            redirect_chain.append(str(response.url))

            chunks: list[bytes] = []
            total = 0
            async for chunk in response.aiter_bytes():
                total += len(chunk)
                if total > MAX_CONTENT_BYTES:
                    logger.warning("Content truncated at 5MB for %s", url)
                    break
                chunks.append(chunk)

            text = b"".join(chunks).decode("utf-8", errors="replace")
            ms = int((time.monotonic() - start) * 1000)
            return response.status_code, dict(response.headers), text, ms


async def _curl_request(
    url: str,
    ua: str,
    timeout: float,
    verify: bool,
    impersonate: str,
) -> tuple[int, dict, str, int]:
    """Internal curl_cffi fetch with TLS impersonation."""
    from curl_cffi.requests import AsyncSession
    start = time.monotonic()
    async with AsyncSession(impersonate=impersonate) as session:
        response = await session.get(
            url,
            headers={"User-Agent": ua},
            timeout=timeout,
            verify=verify,
            allow_redirects=True,
            max_redirects=10,
        )
        text = response.text[:MAX_CONTENT_BYTES]
        ms = int((time.monotonic() - start) * 1000)
        return response.status_code, dict(response.headers), text, ms


async def try_with_fallback_uas(
    url: str,
    timeout: float = 15.0,
) -> tuple[int, dict[str, str], str, int]:
    """
    Try UA_CHROME, then UA_GOOGLEBOT, then UA_PYTHON in sequence.
    Returns the first non-blocked successful response.
    """
    for ua in [UA_CHROME, UA_GOOGLEBOT, UA_PYTHON]:
        status, headers, text, ms = await make_request(url, ua=ua, timeout=timeout)
        if not detect_block(status, text):
            return status, headers, text, ms
        logger.warning("Blocked with UA %s for %s", ua, url)
    return status, headers, text, ms


def detect_block(status: int, text: str) -> bool:
    """Return True if the response looks like a WAF/antibot block."""
    if status in (403, 503, 429, 520):
        text_lower = text.lower()
        return any(signal in text_lower for signal in WAF_BODY_SIGNALS)
    return False


async def compare_mobile_desktop(
    url: str,
    timeout: float = 15.0,
) -> dict[str, Any]:
    """
    Fetch with desktop and mobile UAs. Returns content_differs and size_diff_pct.
    Used by classifier to detect mobile-specific content strategies.
    """
    from bs4 import BeautifulSoup

    _, _, desktop_text, _ = await make_request(url, ua=UA_CHROME, timeout=timeout)
    _, _, mobile_text, _ = await make_request(url, ua=UA_MOBILE, timeout=timeout)

    size_diff_pct = abs(len(desktop_text) - len(mobile_text)) / max(len(desktop_text), 1)

    def get_h1(html: str) -> str:
        soup = BeautifulSoup(html, "lxml")
        tag = soup.find("h1")
        return tag.get_text(strip=True) if tag else ""

    h1_differs = get_h1(desktop_text) != get_h1(mobile_text)
    content_differs = size_diff_pct > 0.15 or h1_differs

    return {
        "content_differs": content_differs,
        "size_diff_pct": round(size_diff_pct, 3),
    }
