"""
modules/legal.py
Analyzes robots.txt, sitemap, and Terms of Service for a target URL.
"""
from __future__ import annotations

import logging
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

from bs4 import BeautifulSoup

from models.schemas import LegalResult, RobotsTxtResult, SitemapResult, TosResult
from utils.http import UA_CHROME, UA_GOOGLEBOT, UA_PYTHON, make_request

logger = logging.getLogger(__name__)

TOS_PATHS = ["/terms", "/tos", "/legal", "/terms-of-service", "/privacy"]
TOS_KEYWORDS = [
    "scraping", "crawling", "automated", "bot", "robot",
    "data extraction", "commercial use", "prohibited",
]


async def analyze_legal(url: str, timeout: float = 15.0) -> LegalResult:
    """
    Fetch and analyze robots.txt, sitemap, and ToS for the given URL.
    Returns a LegalResult with structured findings.
    """
    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    target_path = parsed.path or "/"

    robots = await _analyze_robots(base, target_path, timeout)
    sitemap = await _analyze_sitemap(base, timeout)
    tos = await _analyze_tos(base, robots, timeout)

    return LegalResult(robots_txt=robots, sitemap=sitemap, tos=tos)


async def _analyze_robots(
    base: str, target_path: str, timeout: float
) -> RobotsTxtResult:
    """Fetch robots.txt with three UAs and parse access rules."""
    robots_url = f"{base}/robots.txt"
    responses: dict[str, str] = {}

    for ua in [UA_CHROME, UA_GOOGLEBOT, UA_PYTHON]:
        try:
            status, _, text, _ = await make_request(robots_url, ua=ua, timeout=timeout)
            if status == 200 and not text.strip().startswith("<"):
                responses[ua] = text
            elif status == 404:
                pass
            else:
                logger.debug("robots.txt non-standard response %s for UA %s", status, ua)
        except Exception as e:
            logger.debug("robots.txt fetch error for UA %s: %s", ua, e)

    if not responses:
        return RobotsTxtResult(
            found=False,
            ua_specific=False,
            crawl_delay_seconds=None,
            target_path_allowed=True,
            blocked_paths=[],
            sitemap_declared=None,
        )

    # Check if content differs between UAs
    texts = list(responses.values())
    ua_specific = len(set(t.strip() for t in texts)) > 1

    # Parse with the Chrome UA response (or first available)
    primary_text = responses.get(UA_CHROME) or texts[0]
    parser = RobotFileParser()
    parser.parse(primary_text.splitlines())

    # Extract crawl delay
    crawl_delay: int | None = None
    for line in primary_text.splitlines():
        if line.lower().startswith("crawl-delay:"):
            try:
                crawl_delay = int(line.split(":", 1)[1].strip())
            except ValueError:
                pass

    # Extract blocked paths for Chrome UA
    blocked: list[str] = []
    for line in primary_text.splitlines():
        if line.lower().startswith("disallow:"):
            path = line.split(":", 1)[1].strip()
            if path:
                blocked.append(path)

    # Extract sitemap declaration
    sitemap_url: str | None = None
    for line in primary_text.splitlines():
        if line.lower().startswith("sitemap:"):
            sitemap_url = line.split(":", 1)[1].strip()
            break

    allowed = parser.can_fetch(UA_CHROME, target_path)

    return RobotsTxtResult(
        found=True,
        ua_specific=ua_specific,
        crawl_delay_seconds=crawl_delay,
        target_path_allowed=allowed,
        blocked_paths=blocked,
        sitemap_declared=sitemap_url,
    )


async def _analyze_sitemap(base: str, timeout: float) -> SitemapResult:
    """Try /sitemap.xml then /sitemap_index.xml."""
    for path in ["/sitemap.xml", "/sitemap_index.xml"]:
        try:
            status, _, text, _ = await make_request(
                f"{base}{path}", timeout=timeout
            )
            if status != 200 or not text.strip():
                continue

            soup = BeautifulSoup(text, "lxml-xml")

            if soup.find("sitemapindex"):
                count = len(soup.find_all("sitemap"))
                last_mod = None
                lm = soup.find("lastmod")
                if lm:
                    last_mod = lm.get_text(strip=True)
                return SitemapResult(
                    found=True,
                    type="sitemapindex",
                    url_count=count,
                    last_modified=last_mod,
                )

            if soup.find("urlset"):
                count = len(soup.find_all("url"))
                last_mod = None
                lm = soup.find("lastmod")
                if lm:
                    last_mod = lm.get_text(strip=True)
                return SitemapResult(
                    found=True,
                    type="urlset",
                    url_count=count,
                    last_modified=last_mod,
                )
        except Exception as e:
            logger.debug("Sitemap fetch error at %s: %s", path, e)

    return SitemapResult(found=False, type="", url_count=None, last_modified=None)


async def _analyze_tos(
    base: str, robots: RobotsTxtResult, timeout: float
) -> TosResult:
    """Probe known ToS paths, then footer links, then score risk."""
    tos_text: str | None = None
    tos_url: str | None = None

    for path in TOS_PATHS:
        try:
            status, _, text, _ = await make_request(
                f"{base}{path}", timeout=timeout
            )
            if status == 200 and len(text) > 200:
                tos_text = text.lower()
                tos_url = f"{base}{path}"
                break
        except Exception as e:
            logger.debug("ToS probe error at %s: %s", path, e)

    # Fallback: parse footer links from homepage
    if not tos_text:
        try:
            status, _, home_html, _ = await make_request(base, timeout=timeout)
            if status == 200:
                soup = BeautifulSoup(home_html, "lxml")
                footer = soup.find("footer") or soup
                for link in footer.find_all("a", href=True):
                    link_text = link.get_text(strip=True).lower()
                    if any(kw in link_text for kw in ["terms", "tos", "legal", "privacy"]):
                        href = link["href"]
                        if not href.startswith("http"):
                            href = base + href
                        try:
                            s, _, t, _ = await make_request(href, timeout=timeout)
                            if s == 200 and len(t) > 200:
                                tos_text = t.lower()
                                tos_url = href
                                break
                        except Exception:
                            pass
        except Exception as e:
            logger.debug("Homepage fetch for ToS footer: %s", e)

    if not tos_text:
        # No ToS found — risk depends on robots.txt
        if robots.found and not robots.target_path_allowed:
            risk = "MEDIUM"
        else:
            risk = "UNKNOWN"
        return TosResult(found=False, url=None, risk_level=risk, flagged_keywords=[])

    # Score keywords
    flagged = [kw for kw in TOS_KEYWORDS if kw in tos_text]

    if len(flagged) >= 2:
        risk = "HIGH"
    elif len(flagged) == 1:
        risk = "MEDIUM"
    else:
        risk = "LOW"

    return TosResult(found=True, url=tos_url, risk_level=risk, flagged_keywords=flagged)
