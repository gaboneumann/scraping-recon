"""
modules/api_detector.py
Detects internal API endpoints, state blobs, and GraphQL introspection
from static HTML analysis. Flags incomplete results for DYNAMIC sites.
"""
from __future__ import annotations

import json
import logging
import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from models.schemas import ApiDetectorResult, ApiEndpoint, SearchApiResult
from utils.http import UA_CHROME, make_request

logger = logging.getLogger(__name__)

API_PATTERNS: list[re.Pattern] = [
    re.compile(r'fetch\(["\']([^"\']+)["\']'),
    re.compile(r'axios\.(?:get|post|put|delete)\(["\']([^"\']+)["\']'),
    re.compile(r'XMLHttpRequest.*?\.open\(["\'](?:GET|POST)["\'],\s*["\']([^"\']+)["\']'),
    re.compile(r'\$\.ajax\(.*?url:\s*["\']([^"\']+)["\']'),
    re.compile(r'((?:/api/|/v\d+/|/graphql)[a-zA-Z0-9/_\-]+)'),
    re.compile(r'(wss?://[^\s"\'<>]+)'),
]

STATE_PATTERNS = [
    "__NEXT_DATA__",
    "window.__INITIAL_STATE__",
    "window.__REDUX_STATE__",
    "window.__PRELOADED_STATE__",
]

ASSET_EXTENSIONS = {".js", ".css", ".png", ".jpg", ".jpeg", ".gif", ".svg",
                    ".woff", ".woff2", ".ttf", ".ico", ".webp", ".map"}

INTROSPECTION_QUERY = '{"query":"{__typename}"}'

# E2 Search API patterns
SEARCH_API_PATTERNS: dict[str, list[str]] = {
    "algolia": [
        "algoliasearch", "algolia.com", "AA.PLACES_INDEX_NAME",
        "algoliaConfig", "window.algolia"
    ],
    "elasticsearch": [
        "elasticsearch", "kibana", "_search", "elastic.co",
        "opensearch", "opensearch_dashboards"
    ],
    "custom": [
        "/api/search", "/api/products", "/api/catalog",
        "/api/catalog/search", "/search/api"
    ],
}


async def detect_apis(
    url: str,
    timeout: float = 15.0,
    classifier_type: str = "UNKNOWN",
) -> ApiDetectorResult:
    """
    Scan the page for internal API endpoints, state blobs, and GraphQL.
    Sets endpoints_may_be_incomplete=True when site is DYNAMIC/API_DRIVEN.
    """
    status, headers, html, _ = await make_request(url, ua=UA_CHROME, timeout=timeout)

    endpoints_raw: set[str] = set()
    ws_endpoints: set[str] = set()
    state_blobs: list[str] = []

    # Scan raw HTML with regex patterns
    for pattern in API_PATTERNS:
        for match in pattern.finditer(html):
            found = match.group(1)
            if _is_asset(found):
                continue
            if found.startswith("wss://") or found.startswith("ws://"):
                ws_endpoints.add(found)
            else:
                endpoints_raw.add(found)

    # Detect state blobs
    for blob_key in STATE_PATTERNS:
        if blob_key in html:
            state_blobs.append(blob_key)

    # Build endpoint list, classify each
    endpoints: list[ApiEndpoint] = []
    graphql_candidates: list[str] = []

    base = f"{urlparse(url).scheme}://{urlparse(url).netloc}"

    for raw in endpoints_raw:
        ep_type = _classify_endpoint(raw)
        if ep_type == "GraphQL":
            graphql_candidates.append(raw)
        endpoints.append(ApiEndpoint(
            url=raw,
            type=ep_type,
            authenticated=None,
        ))

    for ws in ws_endpoints:
        endpoints.append(ApiEndpoint(url=ws, type="WebSocket", authenticated=None))

    # GraphQL introspection probe (max 2 requests)
    for gql_path in graphql_candidates[:2]:
        gql_url = gql_path if gql_path.startswith("http") else base + gql_path
        try:
            s, _, resp_text, _ = await make_request(
                gql_url,
                ua=UA_CHROME,
                timeout=timeout,
            )
            # Use POST for introspection
            import httpx
            async with httpx.AsyncClient(timeout=timeout, verify=False) as client:
                resp = await client.post(
                    gql_url,
                    content=INTROSPECTION_QUERY,
                    headers={"Content-Type": "application/json"},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("data", {}).get("__typename"):
                        logger.info("GraphQL introspection enabled at %s", gql_url)
        except Exception as e:
            logger.debug("GraphQL probe error at %s: %s", gql_url, e)

    internal_api_found = len(endpoints) > 0

    # Flag incomplete results for DYNAMIC sites
    may_be_incomplete = classifier_type in ("DYNAMIC", "API_DRIVEN") and not internal_api_found

    recommendation = _build_recommendation(
        endpoints, state_blobs, may_be_incomplete
    )

    return ApiDetectorResult(
        internal_api_found=internal_api_found,
        endpoints=endpoints,
        state_blobs_found=state_blobs,
        recommendation=recommendation,
        endpoints_may_be_incomplete=may_be_incomplete,
    )


async def _detect_search_api(
    html: str,
    endpoints: list[ApiEndpoint],
    base_url: str,
    timeout: float,
) -> SearchApiResult:
    """
    E2: Detect search API provider (Algolia, Elasticsearch, custom).
    Pattern detection first (0 HTTP cost); optional probe if endpoint found.
    Returns SearchApiResult with confidence scoring.
    """
    api_found = False
    api_type = None
    endpoint_url = None
    authenticated = None
    confidence = "low"
    detection_method = "pattern"

    # Pattern-based detection
    for provider, patterns in SEARCH_API_PATTERNS.items():
        for pattern in patterns:
            if pattern in html:
                api_found = True
                api_type = provider
                confidence = "medium"
                break
        if api_found:
            break

    # Try to find endpoint URL from detected endpoints or state blobs
    if api_found and api_type:
        # Look for matching endpoint in discovered API list
        search_candidates = [
            e.url for e in endpoints
            if any(term in e.url.lower() for term in ["search", "algolia", "elasticsearch"])
        ]

        if search_candidates:
            endpoint_url = search_candidates[0]

            # Optional: probe the endpoint if it looks valid
            if endpoint_url and not any(x in endpoint_url for x in ["localhost", "example.com", "test"]):
                try:
                    # Construct test query
                    probe_url = endpoint_url
                    if "?" not in endpoint_url:
                        probe_url = f"{endpoint_url}?q=test" if "/" not in endpoint_url.split("://")[1] else endpoint_url

                    import httpx
                    async with httpx.AsyncClient(timeout=timeout, verify=False) as client:
                        resp = await client.get(probe_url)
                        if resp.status_code == 200:
                            confidence = "high"
                            authenticated = False
                            detection_method = "probe"
                        elif resp.status_code in (401, 403):
                            confidence = "high"
                            authenticated = True
                            detection_method = "probe"
                except Exception as e:
                    logger.debug("Search API probe failed: %s", e)

    return SearchApiResult(
        found=api_found,
        api_type=api_type,
        endpoint_url=endpoint_url,
        authenticated=authenticated,
        confidence=confidence,
        detection_method=detection_method,
    )


def _is_asset(url: str) -> bool:
    """Return True if the URL is a static asset."""
    path = urlparse(url).path.lower()
    return any(path.endswith(ext) for ext in ASSET_EXTENSIONS)


def _classify_endpoint(url: str) -> str:
    """Classify an endpoint URL as REST, GraphQL, WebSocket, or Unknown."""
    lower = url.lower()
    if "graphql" in lower:
        return "GraphQL"
    if lower.startswith("wss://") or lower.startswith("ws://"):
        return "WebSocket"
    if re.search(r'/api/|/v\d+/', lower):
        return "REST"
    return "Unknown"


def _build_recommendation(
    endpoints: list[ApiEndpoint],
    state_blobs: list[str],
    may_be_incomplete: bool,
) -> str:
    """Build a human-readable recommendation string."""
    parts = []
    if state_blobs:
        parts.append(f"State blobs found ({', '.join(state_blobs)}) — parse JSON directly.")
    if any(e.type == "GraphQL" for e in endpoints):
        parts.append("GraphQL endpoint detected — use gql client for structured queries.")
    if any(e.type == "REST" for e in endpoints):
        parts.append("REST API detected — scrape API directly instead of HTML.")
    if any(e.type == "WebSocket" for e in endpoints):
        parts.append("WebSocket detected — real-time data stream available.")
    if may_be_incomplete:
        parts.append(
            "Site renders via JS — intercept XHR with Playwright (--deep) for complete endpoint map."
        )
    return " ".join(parts) if parts else "No internal APIs detected."
