"""
modules/antibot.py
Analyzes anti-bot protections across 9 dimensions:
WAF, TLS fingerprint, rate limiting, captcha, browser fingerprinting (B2/B3/B7),
honeypots, IP reputation, behavioral event listeners (B5), and commerce journey probes (B6).
Produces a score from 0-10.
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
    BehavioralDetectionDimension,
    BehavioralVendor,
    CaptchaDimension,
    FingerprintDimension,
    HoneypotDimension,
    IpRepDimension,
    JourneyDimension,
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
    "Turnstile":    (3, ["challenges.cloudflare.com/turnstile", "turnstile.js"]),
    "Turnstile PoW":(3, ["challenges.cloudflare.com/turnstile", "turboshake.js"]),
    "reCAPTCHA v3": (3, ["render="]),
    "FunCaptcha":   (3, ["funcaptcha.com"]),
    "reCAPTCHA v2": (2, ["data-sitekey"]),
    "hCaptcha":     (2, ["hcaptcha.com"]),
}

FINGERPRINT_SIGNALS: dict[str, tuple[int, list[str]]] = {
    "FingerprintJS":   (2, ["fpjs.io", "fingerprint.com"]),
    "Canvas FP":       (2, ["toDataURL", "getImageData"]),
    "AudioContext FP": (2, ["AudioContext", "AnalyserNode", "createDynamicsCompressor"]),
    "WebGL FP":        (2, ["getParameter", "WEBGL_debug_renderer_info"]),
    "Webdriver check": (3, ["navigator.webdriver"]),
    "Plugins check":   (2, ["navigator.plugins", "navigator.mimeTypes"]),
    "Chrome check":    (2, ["window.chrome", "chrome.runtime"]),
    "WebRTC leak":     (3, ["RTCPeerConnection", "getUserMedia", "createDataChannel"]),
}

HONEYPOT_SELECTORS = [
    "[style*='display:none'] a",
    "[style*='visibility:hidden'] a",
    "[style*='left:-9999'] a",
    "[style*='left: -9999'] a",
]

BEHAVIORAL_VENDOR_PATTERNS: dict[str, dict[str, str]] = {
    "DataDome": {
        "script": r"datadome\.com|window\._dd|_dd_rum|datadome.*\.js",
        "cookie": r"^(px2|px_profile|_dd|_pxAppId)$",
        "header": r"x-datadome|datadome",
    },
    "PerimeterX": {
        "script": r"window\._pxAppId|_pxAppId\s*=|px-cdn\.net|perimeterx|humansec",
        "cookie": r"^(_pxAppId|_pxamb|_pxamb_b)$",
        "header": r"pxcaptcha|_px2",
    },
    "Akamai": {
        "script": r"akamai|bot_manager|_akm|bmak|akam-sw\.js|akamaihd\.net/bot",
        "cookie": r"^(akm_user|abck)$",
        "header": r"x-akamai-transformed",
    },
    "Kasada": {
        "script": r"kasada\.io|kpsdk",
        "cookie": r"^kpsdk.*$",
        "header": r"x-kasada-info",
    },
}

BEHAVIORAL_LISTENER_PATTERNS: dict[str, str] = {
    "mousemove": r"addEventListener\s*\(\s*['\"]mousemove['\"]\s*,\s*|on\s*mousemove\s*=",
    "keydown": r"addEventListener\s*\(\s*['\"]keydown['\"]\s*,\s*|on\s*keydown\s*=",
    "wheel": r"addEventListener\s*\(\s*['\"]wheel['\"]\s*,\s*|on\s*wheel\s*=",
    "scroll": r"addEventListener\s*\(\s*['\"]scroll['\"]\s*,\s*|on\s*scroll\s*=",
    "touchstart": r"addEventListener\s*\(\s*['\"]touchstart['\"]\s*,\s*|on\s*touchstart\s*=",
}


async def analyze_antibot(
    url: str,
    timeout: float = 30.0,
    api_endpoints: list[ApiEndpoint] | None = None,
    ecommerce_signals: dict | None = None,
) -> AntibotResult:
    """
    Run all 9 anti-bot detection dimensions and return an AntibotResult.
    Maximum 12-15 requests base: 1 base + 8 rate-limit + 3 TLS + up to 2 journey probes.
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
    behavioral_vendors = _detect_behavioral_vendors(html, h, soup)
    behavioral_detection_dim = _detect_behavioral_events(html, soup)
    journey_dim = await _detect_journey_probes(url, ecommerce_signals, timeout=15.0)

    score = sum([
        waf_dim.score,
        tls_dim.score,
        rate_dim.score,
        captcha_dim.score,
        fingerprint_dim.score,
        honeypot_dim.score,
        ip_rep_dim.score,
        behavioral_detection_dim.score,
        journey_dim.score,
    ])

    overall_score = round((score / 27) * 10, 2)

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
            behavioral_detection=behavioral_detection_dim,
            journey_probes=journey_dim,
        ),
        api_endpoint_probes=endpoint_probes,
        behavioral_vendors=behavioral_vendors,
    )


def _extract_scripts(html: str, soup: BeautifulSoup) -> list[str]:
    """Extract all script content: inline bodies + src attribute values."""
    scripts = []
    for tag in soup.find_all("script"):
        if tag.string:
            scripts.append(tag.string)
        if tag.get("src"):
            scripts.append(tag.get("src"))
    return scripts


def _extract_cookies(headers: dict[str, str]) -> list[str]:
    """Extract cookie names from Set-Cookie headers."""
    cookies = []
    for value in headers.values():
        if isinstance(value, str):
            parts = value.split(";")
            if parts:
                cookie_pair = parts[0].strip()
                if "=" in cookie_pair:
                    cookie_name = cookie_pair.split("=", 1)[0].strip()
                    cookies.append(cookie_name)
    return cookies


def _detect_datadome(html: str, headers: dict[str, str], soup: BeautifulSoup) -> BehavioralVendor | None:
    """Detect DataDome behavioral vendor via script, cookie, or header patterns."""
    patterns = BEHAVIORAL_VENDOR_PATTERNS.get("DataDome", {})
    detected_via = []

    scripts = _extract_scripts(html, soup)
    script_pattern = patterns.get("script", "")
    if script_pattern and any(re.search(script_pattern, s, re.IGNORECASE) for s in scripts):
        detected_via.append("script")

    cookies = _extract_cookies(headers)
    cookie_pattern = patterns.get("cookie", "")
    if cookie_pattern and any(re.match(cookie_pattern, c, re.IGNORECASE) for c in cookies):
        detected_via.append("cookie")

    header_pattern = patterns.get("header", "")
    if header_pattern and any(re.search(header_pattern, v, re.IGNORECASE) for v in headers.values()):
        detected_via.append("header")

    if not detected_via:
        return None

    confidence = "high" if "script" in detected_via else ("medium" if "cookie" in detected_via else "low")
    return BehavioralVendor(name="DataDome", confidence=confidence, detected_via=detected_via)


def _detect_perimeterx(html: str, headers: dict[str, str], soup: BeautifulSoup) -> BehavioralVendor | None:
    """Detect PerimeterX behavioral vendor via script, cookie, or header patterns."""
    patterns = BEHAVIORAL_VENDOR_PATTERNS.get("PerimeterX", {})
    detected_via = []

    scripts = _extract_scripts(html, soup)
    script_pattern = patterns.get("script", "")
    if script_pattern and any(re.search(script_pattern, s, re.IGNORECASE) for s in scripts):
        detected_via.append("script")

    cookies = _extract_cookies(headers)
    cookie_pattern = patterns.get("cookie", "")
    if cookie_pattern and any(re.match(cookie_pattern, c, re.IGNORECASE) for c in cookies):
        detected_via.append("cookie")

    header_pattern = patterns.get("header", "")
    if header_pattern and any(re.search(header_pattern, v, re.IGNORECASE) for v in headers.values()):
        detected_via.append("header")

    if not detected_via:
        return None

    confidence = "high" if "script" in detected_via else ("medium" if "cookie" in detected_via else "low")
    return BehavioralVendor(name="PerimeterX", confidence=confidence, detected_via=detected_via)


def _detect_akamai(html: str, headers: dict[str, str], soup: BeautifulSoup) -> BehavioralVendor | None:
    """Detect Akamai behavioral vendor via script, cookie, or header patterns."""
    patterns = BEHAVIORAL_VENDOR_PATTERNS.get("Akamai", {})
    detected_via = []

    scripts = _extract_scripts(html, soup)
    script_pattern = patterns.get("script", "")
    if script_pattern and any(re.search(script_pattern, s, re.IGNORECASE) for s in scripts):
        detected_via.append("script")

    cookies = _extract_cookies(headers)
    cookie_pattern = patterns.get("cookie", "")
    if cookie_pattern and any(re.match(cookie_pattern, c, re.IGNORECASE) for c in cookies):
        detected_via.append("cookie")

    header_pattern = patterns.get("header", "")
    if header_pattern and any(re.search(header_pattern, v, re.IGNORECASE) for v in headers.values()):
        detected_via.append("header")

    if not detected_via:
        return None

    confidence = "high" if "script" in detected_via else ("medium" if "cookie" in detected_via else "low")
    return BehavioralVendor(name="Akamai", confidence=confidence, detected_via=detected_via)


def _detect_kasada(html: str, headers: dict[str, str], soup: BeautifulSoup) -> BehavioralVendor | None:
    """Detect Kasada behavioral vendor via script, cookie, or header patterns."""
    patterns = BEHAVIORAL_VENDOR_PATTERNS.get("Kasada", {})
    detected_via = []

    scripts = _extract_scripts(html, soup)
    script_pattern = patterns.get("script", "")
    if script_pattern and any(re.search(script_pattern, s, re.IGNORECASE) for s in scripts):
        detected_via.append("script")

    cookies = _extract_cookies(headers)
    cookie_pattern = patterns.get("cookie", "")
    if cookie_pattern and any(re.match(cookie_pattern, c, re.IGNORECASE) for c in cookies):
        detected_via.append("cookie")

    header_pattern = patterns.get("header", "")
    if header_pattern and any(re.search(header_pattern, v, re.IGNORECASE) for v in headers.values()):
        detected_via.append("header")

    if not detected_via:
        return None

    confidence = "high" if "script" in detected_via else ("medium" if "cookie" in detected_via else "low")
    return BehavioralVendor(name="Kasada", confidence=confidence, detected_via=detected_via)


def _detect_behavioral_vendors(html: str, headers: dict[str, str], soup: BeautifulSoup) -> list[BehavioralVendor]:
    """Orchestrate behavioral vendor detection across all vendors."""
    vendors = []

    try:
        datadome = _detect_datadome(html, headers, soup)
        if datadome:
            vendors.append(datadome)
    except Exception as e:
        logger.debug("DataDome detection failed: %s", e)

    try:
        perimeterx = _detect_perimeterx(html, headers, soup)
        if perimeterx:
            vendors.append(perimeterx)
    except Exception as e:
        logger.debug("PerimeterX detection failed: %s", e)

    try:
        akamai = _detect_akamai(html, headers, soup)
        if akamai:
            vendors.append(akamai)
    except Exception as e:
        logger.debug("Akamai detection failed: %s", e)

    try:
        kasada = _detect_kasada(html, headers, soup)
        if kasada:
            vendors.append(kasada)
    except Exception as e:
        logger.debug("Kasada detection failed: %s", e)

    return sorted(vendors, key=lambda v: {"high": 0, "medium": 1, "low": 2}[v.confidence])


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


def _detect_behavioral_events(html: str, soup: BeautifulSoup) -> BehavioralDetectionDimension:
    """Detect behavioral event listeners for collection (B5)."""
    scripts = _extract_scripts(html, soup)
    listener_types: list[str] = []
    listener_count = 0

    for listener, pattern in BEHAVIORAL_LISTENER_PATTERNS.items():
        found = False
        for script in scripts:
            if re.search(pattern, script, re.IGNORECASE):
                if "isTrusted" in script or listener not in listener_types:
                    found = True
                    break

        if found:
            listener_types.append(listener)
            listener_count += 1

    confidence = "high" if listener_count >= 3 else "medium" if listener_count == 2 else "low"
    score = 0 if listener_count < 2 else (1 if listener_count == 2 else (2 if listener_count < 4 else 3))

    return BehavioralDetectionDimension(
        score=score,
        listener_count=listener_count,
        listener_types=listener_types,
        confidence=confidence,
    )


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


async def _detect_journey_probes(
    url: str,
    ecommerce_signals: dict | None = None,
    timeout: float = 15.0,
) -> JourneyDimension:
    """
    Detect commerce journey protection (B6).
    Probes /checkout and /cart without session; max 2 requests.
    Only probes if ecommerce_signals indicates e-commerce site.
    """
    if not ecommerce_signals or not ecommerce_signals.get("is_ecommerce"):
        return JourneyDimension(
            score=0,
            blocked_at_url=None,
            blocked_type="none",
            probes_sent=0,
        )

    base_url = url.rstrip("/")
    journey_paths = ["/checkout", "/cart"]
    blocked_at = None
    blocked_type = "none"
    probes_sent = 0

    for path in journey_paths[:2]:
        if probes_sent >= 2:
            break

        probe_url = f"{base_url}{path}"
        try:
            status, headers, html, _ = await make_request(probe_url, timeout=timeout)
            probes_sent += 1

            if status == 403:
                blocked_at = probe_url
                blocked_type = "403"
                break
            elif status in (401, 407):
                blocked_at = probe_url
                blocked_type = "challenge"
                break
            elif status in (301, 302, 303, 307, 308):
                blocked_at = probe_url
                blocked_type = "redirect"
                break
            elif status >= 429:
                blocked_at = probe_url
                blocked_type = "rate_limit"
                break
        except Exception as e:
            logger.debug("Journey probe failed for %s: %s", path, e)

    score = 0 if blocked_type == "none" else (1 if probes_sent == 1 else 2 if blocked_type == "redirect" else 3)

    return JourneyDimension(
        score=score,
        blocked_at_url=blocked_at,
        blocked_type=blocked_type,
        probes_sent=probes_sent,
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
