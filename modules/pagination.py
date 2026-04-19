"""
modules/pagination.py
Detects the pagination strategy of a web page.
Priority order: LINK_REL_NEXT > QUERY_PARAM > PATH > CURSOR > LOAD_MORE > INFINITE_SCROLL > NONE
"""
from __future__ import annotations

import json
import logging
import re
from urllib.parse import parse_qs, urljoin, urlparse

from bs4 import BeautifulSoup

from models.schemas import PaginationResult
from utils.http import UA_CHROME, make_request

logger = logging.getLogger(__name__)

QUERY_PARAM_PATTERNS = ["page", "p", "offset", "start", "pg"]
PATH_PATTERNS = [re.compile(r"/page/\d+"), re.compile(r"/p/\d+")]
CURSOR_PATTERNS = ["cursor", "after", "before", "next_token"]
LOAD_MORE_PATTERNS = ["load-more", "btn-next", "ver más", "ver mas", "load_more", "loadmore"]
STATE_KEYS = [
    "__NEXT_DATA__", "window.__INITIAL_STATE__",
    "window.__REDUX_STATE__", "window.__PRELOADED_STATE__",
]


async def detect_pagination(url: str, timeout: float = 15.0) -> PaginationResult:
    """
    Fetch the page and detect its pagination strategy.
    Returns a PaginationResult with type, parameter, example URL, and JS requirement.
    """
    _, _, html, _ = await make_request(url, ua=UA_CHROME, timeout=timeout)
    soup = BeautifulSoup(html, "lxml")
    hrefs = [a.get("href", "") for a in soup.find_all("a", href=True)]

    # 1. LINK_REL_NEXT — highest priority
    link_next = soup.find("link", rel="next")
    if link_next and link_next.get("href"):
        return PaginationResult(
            type="LINK_REL_NEXT",
            parameter=None,
            example_next_url=urljoin(url, link_next["href"]),
            requires_js=False,
        )

    # 2. QUERY_PARAM
    for param in QUERY_PARAM_PATTERNS:
        for href in hrefs:
            parsed = urlparse(href)
            qs = parse_qs(parsed.query)
            if param in qs:
                return PaginationResult(
                    type="QUERY_PARAM",
                    parameter=param,
                    example_next_url=urljoin(url, href),
                    requires_js=False,
                )

    # 3. PATH
    for pattern in PATH_PATTERNS:
        for href in hrefs:
            if pattern.search(href):
                return PaginationResult(
                    type="PATH",
                    parameter=None,
                    example_next_url=urljoin(url, href),
                    requires_js=False,
                )

    # 4. CURSOR — check hrefs and state blobs
    for param in CURSOR_PATTERNS:
        for href in hrefs:
            qs = parse_qs(urlparse(href).query)
            if param in qs:
                return PaginationResult(
                    type="CURSOR",
                    parameter=param,
                    example_next_url=urljoin(url, href),
                    requires_js=False,
                )

    # Check state blobs for cursor signals
    for key in STATE_KEYS:
        if key in html:
            for param in CURSOR_PATTERNS:
                if f'"{param}"' in html or f"'{param}'" in html:
                    return PaginationResult(
                        type="CURSOR",
                        parameter=param,
                        example_next_url=None,
                        requires_js=True,
                    )

    # 5. LOAD_MORE — class/id/text match
    for element in soup.find_all(["button", "a", "div", "span"]):
        text = element.get_text(strip=True).lower()
        elem_id = (element.get("id") or "").lower()
        elem_class = " ".join(element.get("class") or []).lower()
        combined = f"{text} {elem_id} {elem_class}"
        if any(pat in combined for pat in LOAD_MORE_PATTERNS):
            return PaginationResult(
                type="LOAD_MORE",
                parameter=None,
                example_next_url=None,
                requires_js=True,
            )

    # 6. INFINITE_SCROLL — IntersectionObserver or scroll event listener in JS
    scripts = " ".join(
        tag.get_text() for tag in soup.find_all("script")
        if not tag.get("src")
    )
    if "IntersectionObserver" in scripts or (
        "scroll" in scripts and ("load" in scripts or "fetch" in scripts)
    ):
        return PaginationResult(
            type="INFINITE_SCROLL",
            parameter=None,
            example_next_url=None,
            requires_js=True,
        )

    return PaginationResult(
        type="NONE",
        parameter=None,
        example_next_url=None,
        requires_js=False,
    )
