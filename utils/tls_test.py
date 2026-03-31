"""
utils/tls_test.py
Compares TLS fingerprint sensitivity by fetching the same URL
with different HTTP clients and impersonation profiles.
"""
from __future__ import annotations

import logging

from models.schemas import TlsDimension
from utils.http import make_request, TLS_IMPERSONATION_AVAILABLE

logger = logging.getLogger(__name__)


async def run_tls_test(url: str, timeout: float = 10.0) -> TlsDimension:
    """
    Fetch the URL with httpx, curl_cffi chrome110, and curl_cffi safari17_0.
    Compares (status_code, body_length) across clients.
    Returns a TlsDimension with sensitivity score.
    """
    client_results: dict[str, str] = {}

    # httpx baseline
    try:
        status, _, text, _ = await make_request(url, timeout=timeout)
        client_results["httpx"] = f"{status}/{len(text)}"
    except Exception as e:
        client_results["httpx"] = f"error: {e}"

    if TLS_IMPERSONATION_AVAILABLE:
        for profile in ["chrome110", "safari17_0"]:
            try:
                status, _, text, _ = await make_request(
                    url, timeout=timeout, impersonate=profile
                )
                client_results[profile] = f"{status}/{len(text)}"
            except Exception as e:
                client_results[profile] = f"error: {e}"
    else:
        logger.warning("curl_cffi not available — TLS impersonation skipped")

    score, sensitivity = _score_tls(client_results)

    return TlsDimension(
        score=score,
        sensitivity=sensitivity,
        client_results=client_results,
    )


def _score_tls(results: dict[str, str]) -> tuple[int, str]:
    """
    Score TLS sensitivity based on divergence between clients.
    Returns (score 0-3, sensitivity label).
    """
    values = [v for v in results.values() if not v.startswith("error")]
    if len(values) < 2:
        return 0, "UNKNOWN"

    unique = set(values)
    if len(unique) == 1:
        return 0, "NONE"

    # Check if httpx differs from curl_cffi results
    httpx_val = results.get("httpx", "")
    curl_vals = [v for k, v in results.items() if k != "httpx"]
    httpx_differs = any(v != httpx_val for v in curl_vals if not v.startswith("error"))

    if httpx_differs:
        # Check if status codes differ (more severe) or just body length
        httpx_status = httpx_val.split("/")[0] if "/" in httpx_val else ""
        status_differs = any(
            v.split("/")[0] != httpx_status
            for v in curl_vals
            if "/" in v and not v.startswith("error")
        )
        if status_differs:
            return 3, "HIGH"
        return 2, "MEDIUM"

    return 1, "LOW"
