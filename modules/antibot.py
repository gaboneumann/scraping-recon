"""
modules/antibot.py
Analyzes anti-bot protections across 7 dimensions:
WAF, TLS fingerprint, rate limiting, captcha, browser fingerprinting,
honeypots, and IP reputation. Produces a score from 0-10.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from models.schemas import (
    AntibotDimensions,
    AntibotResult,
    ApiEndpoint,
    ApiEndpointProbeResult,
    CaptchaDimension,
    FingerprintDimension,
    HoneypotDimension,
    IpRepDimension,
    RateLimitDimension,
    WafDimension,
)
from utils.http import UA_CHROME, make_request
from utils.tls_test import run_tls_test

logger = logging.getLogger(__name__)

WAF_HEADER_SIGNALS: dict[str, tuple[int, list[str]]] = {
    "Cloudflare":  (3, ["cf-ray", "__cf_bm"]),
    "DataDome":    (3, ["x-datadome"]),
    "PerimeterX":  (3, ["_px2", "pxcaptcha"]),
    "Akamai":      (3, ["x-akamai-transformed"]),
    "Kasada":      (3, ["x-kasada-info"]),
    "Imperva":     (2, ["incap_ses"]),
    "Sucuri":      (2, ["x-sucuri-id"]),
}

CAPTCHA_SIGNALS: dict[str, tuple[int, list[str]]] = {
    "reCAPTCHA v2": (2, ["data-sitekey"]),
    "reCAPTCHA v3": (3, ["render="]),
    "hCaptcha":     (2, ["hcaptcha.com"]),
    "Turnstile":    (3, ["challenges.cloudflare.com/turnstile"]),
    "FunCaptcha":   (3, ["funcaptcha.com"]),
}

FINGERPRINT_SIGNALS: dict[str, tuple[int, list[str]]] = {
    "FingerprintJS":   (2, ["fpjs.io", "fingerprint.com"]),
    "Canvas FP":       (2, ["toDataURL", "getImageData"]),
    "AudioContext FP": (2, ["AudioContext", "AnalyserNode"]),
    "Webdriver check": (3, ["navigator.webdriver"]),
}

HONEYPOT_SELECTORS = [
    "[style*='display:none'] a",
    "[style*='visibility:hidden'] a",
    "[style*='left:-9999'] a",
    "[style*='left: -9999'] a",
]


async def analyze_antibot(
    url: str,
    timeout: float = 30.0,
    api_endpoints: list[ApiEndpoint] | None = None,
) -> AntibotResult:
    """
    Run all 7 anti-bot detection dimensions and return an AntibotResult.
    Maximum 12 requests base: 1 base + 8 rate-limit + 3 TLS.
    If api_endpoints provided, probes up to 2 REST/GraphQL endpoints (6 requests each).
    """
    # Base fetch for HTML-based dimensions
    status, headers, html, _ = await make_request(url, ua=UA_CHROME, timeout=10.0)
    soup = BeautifulSoup(html, "lxml")
    h = {k.lower(): v for k, v in headers.items()}

    # Run TLS test and rate limiting concurrently
    tls_dim, rate_dim = await asyncio.gather(
        run_tls_test(url, timeout=10.0),
        _test_rate_limiting(url, timeout=10.0),
    )

    waf_dim = _detect_waf(url, h, html)
    captcha_dim = _detect_captcha(html)
    fingerprint_dim = _detect_fingerprinting(html)
    honeypot_dim = _detect_honeypots(soup)
    ip_rep_dim = _assess_ip_reputation(h)

    score = sum([
        waf_dim.score,
        tls_dim.score,
        rate_dim.score,
        captcha_dim.score,
        fingerprint_dim.score,
        honeypot_dim.score,
        ip_rep_dim.score,
    ])

    overall_score = round((score / 21) * 10, 2)

    level = (
        "NONE"    if overall_score == 0  else
        "LOW"     if overall_score < 3   else
        "MEDIUM"  if overall_score < 5   else
        "HIGH"    if overall_score < 8   else
        "EXTREME"
    )

    # Probe API endpoints if provided (max 2, REST/GraphQL only)
    endpoint_probes: list[ApiEndpointProbeResult] = []
    if api_endpoints:
        base = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
        probeable = [
            ep for ep in api_endpoints
            if ep.type in ("REST", "GraphQL") and ep.url.startswith("/")
        ][:2]
        for ep in probeable:
            probe = await _probe_api_endpoint(base + ep.url, ep.type, timeout=10.0)
            endpoint_probes.append(probe)

    return AntibotResult(
        overall_score=overall_score,
        overall_level=level,
        dimensions=AntibotDimensions(
            waf=waf_dim,
            tls_fingerprint=tls_dim,
            rate_limiting=rate_dim,
            captcha=captcha_dim,
            browser_fingerprinting=fingerprint_dim,
            honeypots=honeypot_dim,
            ip_reputation=ip_rep_dim,
        ),
        api_endpoint_probes=endpoint_probes,
    )


def _detect_waf(
    url: str, headers: dict[str, str], html: str
) -> WafDimension:
    """Try wafw00f first, fall back to header-based detection."""
    # Try wafw00f via subprocess
    try:
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            tmp_path = f.name

        result = subprocess.run(
            ["wafw00f", url, "-o", tmp_path, "-f", "json"],
            capture_output=True,
            timeout=15,
        )
        if result.returncode == 0 and Path(tmp_path).exists():
            data = json.loads(Path(tmp_path).read_text())
            if isinstance(data, list) and data:
                entry = data[0]
                detected = entry.get("detected", False)
                firewall = entry.get("firewall")
                if detected and firewall and firewall != "None":
                    return WafDimension(score=3, vendor=firewall, confidence="HIGH")
    except Exception as e:
        logger.debug("wafw00f failed: %s — using header detection", e)

    # Header-based fallback
    for vendor, (score, signals) in WAF_HEADER_SIGNALS.items():
        h_keys = set(headers.keys())
        html_lower = html.lower()
        if any(sig.lower() in h_keys or sig.lower() in html_lower for sig in signals):
            return WafDimension(score=score, vendor=vendor, confidence="MEDIUM")

    return WafDimension(score=0, vendor=None, confidence="NONE")


async def _test_rate_limiting(
    url: str, timeout: float = 10.0
) -> RateLimitDimension:
    """
    Fire 8 requests at 0.3s intervals and detect rate limiting.
    Minimum delay: 0.3s — do not reduce.
    """
    times: list[int] = []
    triggered_at: int | None = None
    error_type: str | None = None
    score = 0

    for i in range(8):
        try:
            status, _, _, ms = await make_request(url, timeout=timeout)
            times.append(ms)
            if status == 429:
                triggered_at = i
                error_type = "HTTP 429"
                score = 3
                break
            if status in (503, 520):
                error_type = f"HTTP {status}"
                score = 2
                break
        except Exception as e:
            error_type = str(e)[:60]
            score = 1
            break
        await asyncio.sleep(0.3)

    # Check for progressive slowdown
    if score == 0 and len(times) >= 2:
        if times[-1] >= times[0] * 3:
            score = 1
            error_type = "Response time degradation"

    return RateLimitDimension(
        score=score,
        triggered_at=triggered_at,
        error_type=error_type,
    )


def _detect_captcha(html: str) -> CaptchaDimension:
    """Detect CAPTCHA providers from HTML."""
    for provider, (score, signals) in CAPTCHA_SIGNALS.items():
        if any(sig in html for sig in signals):
            version = provider.split()[-1] if " " in provider else None
            name = provider.split()[0] if " " in provider else provider
            return CaptchaDimension(score=score, provider=name, version=version)
    return CaptchaDimension(score=0, provider=None, version=None)


def _detect_fingerprinting(html: str) -> FingerprintDimension:
    """Detect browser fingerprinting libraries and techniques."""
    libraries: list[str] = []
    max_score = 0

    for lib, (score, signals) in FINGERPRINT_SIGNALS.items():
        if any(sig in html for sig in signals):
            libraries.append(lib)
            max_score = max(max_score, score)

    return FingerprintDimension(score=max_score, libraries=libraries)


def _detect_honeypots(soup: BeautifulSoup) -> HoneypotDimension:
    """Detect hidden honeypot links."""
    locations: list[str] = []

    for selector in HONEYPOT_SELECTORS:
        try:
            elements = soup.select(selector)
            for el in elements:
                href = el.get("href", "")
                if href:
                    locations.append(href[:80])
        except Exception:
            pass

    count = len(locations)
    score = 0 if count == 0 else 1 if count < 3 else 2 if count < 6 else 3

    return HoneypotDimension(
        score=score,
        count=count,
        locations=locations[:10],
    )


async def _probe_api_endpoint(
    url: str,
    endpoint_type: str,
    timeout: float = 10.0,
) -> ApiEndpointProbeResult:
    """TLS + quick rate-limit probe (3 requests) against a single API endpoint."""
    tls_dim, rate_dim = await asyncio.gather(
        run_tls_test(url, timeout=timeout),
        _test_rate_limiting_quick(url, timeout=timeout),
    )
    return ApiEndpointProbeResult(
        url=url,
        endpoint_type=endpoint_type,
        tls=tls_dim,
        rate_limiting=rate_dim,
    )


async def _test_rate_limiting_quick(
    url: str,
    timeout: float = 10.0,
) -> RateLimitDimension:
    """3-request burst to detect fast rate limiting on API endpoints."""
    triggered_at: int | None = None
    error_type: str | None = None
    score = 0

    for i in range(3):
        try:
            status, _, _, _ = await make_request(url, timeout=timeout)
            if status == 429:
                triggered_at = i
                error_type = "HTTP 429"
                score = 3
                break
            if status in (401, 403):
                error_type = f"HTTP {status} (auth required)"
                score = 1
                break
            if status in (503, 520):
                error_type = f"HTTP {status}"
                score = 2
                break
        except Exception as e:
            error_type = str(e)[:60]
            score = 1
            break
        await asyncio.sleep(0.3)

    return RateLimitDimension(
        score=score,
        triggered_at=triggered_at,
        error_type=error_type,
    )


def _assess_ip_reputation(headers: dict[str, str]) -> IpRepDimension:
    """
    Assess IP reputation signals from headers.
    Geo-block detection is heuristic — based on known geo-restriction headers.
    """
    geo_block = (
        "x-geo-country" in headers
        or "cf-ipcountry" in headers
        or headers.get("x-cache", "").lower() == "miss"
    )

    proxy_recommendation = (
        "Residential proxy in target country recommended"
        if geo_block
        else "Datacenter proxy sufficient"
    )

    return IpRepDimension(
        score=2 if geo_block else 0,
        geo_block=geo_block,
        proxy_recommendation=proxy_recommendation,
    )
