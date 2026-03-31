"""
modules/recommender.py
Pure function that produces a RecommenderResult from a partial ReconReport.
No I/O — all fields in the report may be None.
"""
from __future__ import annotations

from models.schemas import RecommenderResult, ReconReport


def build_recommendation(report: ReconReport) -> RecommenderResult:
    """
    Analyze the ReconReport and produce a library recommendation.
    Follows the decision tree exactly. Each field may be None — handled gracefully.
    """
    antibot    = report.antibot
    classifier = report.classifier
    api        = report.api_detector
    pagination = report.pagination
    auth       = report.auth

    primary: str = "httpx"
    secondary: str | None = None
    managed_api_suggested = False
    managed_api_options: list[str] = []
    flags: list[str] = []

    # ── Decision tree ──────────────────────────────────────────────

    # 1. No antibot data
    if antibot is None:
        primary = "httpx"
        secondary = None
        complexity = 3
        dev_time = "1-2 days"

    # 2. Extreme protection
    elif antibot.overall_score >= 8:
        primary = "playwright + playwright-stealth"
        secondary = "curl_cffi + residential proxy"
        managed_api_suggested = True
        managed_api_options = ["ZenRows", "ScraperAPI", "Scrapfly"]
        complexity = 9
        dev_time = "1-2 weeks"

    # 3. Static site
    elif classifier and classifier.type == "STATIC":
        if antibot.overall_score == 0:
            primary = "httpx + BeautifulSoup4"
            secondary = "Scrapy"
            complexity = 2
            dev_time = "hours"
        else:
            primary = "curl_cffi + BeautifulSoup4"
            secondary = "httpx rotating UA"
            complexity = 4
            dev_time = "1-3 days"

    # 4. Dynamic or API-driven
    elif classifier and classifier.type in ("DYNAMIC", "API_DRIVEN"):
        if api and api.internal_api_found:
            primary = "httpx direct to API"
            secondary = "curl_cffi" if (
                antibot.dimensions.tls_fingerprint.score >= 2
            ) else None
            complexity = 5
            dev_time = "2-4 days"
        else:
            primary = "Playwright async"
            secondary = "Selenium"
            complexity = 7
            dev_time = "3-7 days"

    # 5. Hybrid
    elif classifier and classifier.type == "HYBRID":
        primary = "httpx SSR + Playwright opcional"
        secondary = "Scrapy + Playwright plugin"
        complexity = 6
        dev_time = "3-5 days"

    # Fallback
    else:
        primary = "httpx + BeautifulSoup4"
        secondary = None
        complexity = 3
        dev_time = "1-2 days"

    # ── Additional flags (always evaluated) ────────────────────────

    if antibot:
        if antibot.dimensions.rate_limiting.score >= 2:
            flags.append("Exponential backoff + 2-8s random delays mandatory")
        if antibot.dimensions.tls_fingerprint.score >= 2:
            flags.append("curl_cffi Chrome/Safari impersonation required")
        if antibot.dimensions.captcha.score >= 2:
            flags.append("Consider 2Captcha or Anti-Captcha integration")
        if antibot.dimensions.honeypots.count > 0:
            flags.append(
                f"Filter display:none anchors — "
                f"{antibot.dimensions.honeypots.count} honeypots detected"
            )
        if antibot.dimensions.ip_reputation.geo_block:
            flags.append("Residential proxies in target country required")
        if (
            classifier is not None
            and classifier.type in ("DYNAMIC", "API_DRIVEN")
            and antibot.overall_score < 5.0
        ):
            flags.append(
                "⚠ Antibot score may be underestimated — site renders via JS, "
                "runtime protections (fingerprinting, CAPTCHA, rate-limits) are not "
                "detectable statically. Use --deep for accurate assessment."
            )

    if pagination and pagination.requires_js:
        flags.append("Browser automation mandatory for full crawl")

    if auth:
        if auth.required:
            if auth.type == "FORM":
                flags.append("Session management required — login + persistent cookie jar")
            elif auth.type == "OAUTH":
                flags.append("OAuth flow required — use Playwright to automate login")
            elif auth.type == "API_KEY":
                flags.append("API key auth — pass via header or query param")
        if auth.paywall_type == "HARD":
            flags.append("Hard paywall — subscription account required")
        elif auth.paywall_type == "METERED":
            flags.append("Metered paywall — rotate sessions or incognito profiles")
        if auth.cookie_consent_blocking:
            flags.append("Cookie consent wall — click accept before scraping content")

    if classifier:
        if classifier.structured_data.scraping_shortcut:
            types = ", ".join(classifier.structured_data.schema_types)
            flags.append(f"JSON-LD available ({types}) — parse structured data instead of HTML")
        if classifier.mobile_differs:
            flags.append("Mobile UA serves different content — test with UA_MOBILE for richer data")
        if classifier.estimated_pages == ">5000":
            flags.append("Large site (>5000 pages estimated) — implement queue + deduplication layer")

    if api and api.endpoints_may_be_incomplete:
        flags.append(
            "DYNAMIC site — run with --deep flag (Playwright) for complete XHR endpoint map"
        )

    # ── Full stack summary ─────────────────────────────────────────

    full_stack = _build_summary(primary, secondary, managed_api_suggested, flags, complexity)

    return RecommenderResult(
        primary_library=primary,
        secondary_library=secondary,
        managed_api_suggested=managed_api_suggested,
        managed_api_options=managed_api_options,
        additional_flags=flags,
        estimated_complexity=complexity,
        estimated_dev_time=dev_time,
        full_stack_recommendation=full_stack,
    )


def _build_summary(
    primary: str,
    secondary: str | None,
    managed: bool,
    flags: list[str],
    complexity: int,
) -> str:
    """Build a concise one-paragraph recommendation."""
    parts = [f"Use {primary}"]
    if secondary:
        parts.append(f"with {secondary} as fallback")
    if managed:
        parts.append("— or delegate to a managed scraping API")
    summary = " ".join(parts) + "."
    if flags:
        summary += f" Key considerations: {'; '.join(flags[:3])}."
    summary += f" Complexity: {complexity}/10."
    return summary
