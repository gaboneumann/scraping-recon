"""
utils/playwright_helper.py
Playwright browser lifecycle and XHR route interception helpers.
Used for E7 deep-mode detection to observe runtime behavior.
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

logger = logging.getLogger(__name__)


@asynccontextmanager
async def get_browser_context(timeout: float = 10.0, headless: bool = True) -> AsyncGenerator:
    """Manage Playwright browser context with timeout enforcement.

    Context manager that handles browser launch, context/page creation, and cleanup.
    Launches a headless Chromium browser with automation detection disabled.

    Args:
        timeout: Request timeout in seconds (applied to all page operations).
        headless: If True, browser runs headless (no UI window).

    Yields:
        (page, context) tuple for use within async with block.

    Raises:
        PlaywrightException: If browser launch fails (caller should catch and degrade).

    Example:
        async with get_browser_context(timeout=10.0) as (page, context):
            await page.goto(url)
            # ... perform observations ...
    """
    browser = None
    context = None
    page = None

    try:
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            # Launch Chromium with automation detection disabled
            browser = await p.chromium.launch(
                headless=headless,
                args=["--disable-blink-features=AutomationControlled"],
            )
            context = await browser.new_context()
            page = await context.new_page()

            # Set timeout on all page operations
            page.set_default_timeout(int(timeout * 1000))

            yield page, context

    except ImportError as e:
        logger.warning(f"Playwright import failed: {e.__class__.__name__}")
        raise
    except Exception as e:
        logger.warning(f"Browser initialization failed: {e.__class__.__name__}")
        raise
    finally:
        if browser:
            try:
                await browser.close()
            except Exception as close_err:
                logger.warning(f"Browser close error: {close_err}")


async def setup_xhr_interception(
    page,
    patterns: dict[str, list[str]],
) -> dict[str, list[dict]]:
    """Intercept XHR/fetch requests matching patterns.

    Sets up route interception on the page to capture metadata for requests
    matching provided regex patterns. Does not capture request/response bodies
    (privacy, memory efficiency).

    Args:
        page: Playwright Page object.
        patterns: Dict mapping signal type to list of regex patterns.
                 Example: {"price": ["/api/price", "/graphql"],
                          "cart": ["/api/cart"]}

    Returns:
        Dict mapping signal type to list of captured request metadata dicts.
        Each captured request is: {"url": str, "method": str, "has_auth": bool}

    Example:
        patterns = {
            "price": [r"/api/price", r"/graphql"],
            "pagination": [r"/api/products"],
            "cart": [r"/api/cart"],
        }
        captured = await setup_xhr_interception(page, patterns)
        # captured["price"] = [{"url": "...", "method": "GET", "has_auth": False}, ...]
    """
    intercepted: dict[str, list[dict]] = {
        signal_type: [] for signal_type in patterns.keys()
    }

    async def handle_route(route):
        """Route handler: check URL against patterns and capture metadata."""
        try:
            request = route.request
            url = request.url
            headers = request.headers

            # Check if request matches any pattern
            for signal_type, regex_patterns in patterns.items():
                for pattern in regex_patterns:
                    if pattern in url:
                        # Capture metadata only (no bodies)
                        intercepted[signal_type].append(
                            {
                                "url": url,
                                "method": request.method,
                                "has_auth": any(
                                    h in headers
                                    for h in ["authorization", "cookie", "x-api-key"]
                                ),
                            }
                        )
                        break

            # Continue request normally (non-blocking)
            await route.continue_()
        except Exception as e:
            logger.warning(f"Route handler error: {e.__class__.__name__}")
            try:
                await route.continue_()
            except Exception:
                pass

    try:
        await page.route("**/*", handle_route)
    except Exception as e:
        logger.warning(f"XHR interception setup failed: {e.__class__.__name__}")
        # Return empty dict on setup failure; caller continues gracefully
        return intercepted

    return intercepted


async def scroll_page_to_bottom(
    page,
    max_scrolls: int = 5,
    scroll_delay_ms: int = 500,
) -> int:
    """Trigger infinite scroll and return number of scroll events performed.

    Scrolls the page to bottom in a loop to trigger lazy-loading or infinite
    scroll pagination. Stops early if page height stops changing (no more content).

    Args:
        page: Playwright Page object.
        max_scrolls: Maximum number of scrolls to perform.
        scroll_delay_ms: Delay (ms) between scrolls to allow content load.

    Returns:
        Number of scrolls actually performed (0 to max_scrolls).

    Note:
        Returns gracefully on timeout; logs warning instead of raising.
    """
    scrolls = 0
    delay_sec = scroll_delay_ms / 1000.0

    try:
        previous_height = await page.evaluate("document.body.scrollHeight")

        while scrolls < max_scrolls:
            try:
                # Scroll to bottom
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await asyncio.sleep(delay_sec)

                # Check if height changed
                current_height = await page.evaluate("document.body.scrollHeight")
                if current_height == previous_height:
                    # No more content to load
                    break

                previous_height = current_height
                scrolls += 1

            except asyncio.TimeoutError:
                logger.warning(f"Scroll {scrolls + 1} timed out")
                break
            except Exception as e:
                logger.warning(f"Scroll error: {e.__class__.__name__}")
                break

    except Exception as e:
        logger.warning(f"Page scroll evaluation failed: {e.__class__.__name__}")

    return scrolls


async def find_and_click_cart_button(page, gentle: bool = True) -> bool:
    """Gently probe cart button (hover by default, don't click).

    Attempts to locate a cart button using common e-commerce selectors and
    hover over it (or click if gentle=False). Used to trigger cart API calls
    without actually modifying the cart.

    Args:
        page: Playwright Page object.
        gentle: If True, hover only; if False, click the button.

    Returns:
        True if button found and hovered/clicked; False otherwise.

    Note:
        Returns False gracefully on not found or click failure; never raises.
    """
    selectors = [
        "[class*='cart']",
        "[class*='bag']",
        "[id*='cart']",
        "button:has-text('Cart')",
        "button:has-text('Add to Cart')",
        "button:has-text('Add to Bag')",
        "[aria-label*='cart' i]",
    ]

    for selector in selectors:
        try:
            element = page.locator(selector).first
            if await element.is_visible(timeout=1000):
                if gentle:
                    await element.hover(timeout=1000)
                else:
                    await element.click(timeout=1000)
                logger.debug(f"Cart button found and {'hovered' if gentle else 'clicked'}")
                return True
        except Exception as e:
            # Selector not found or interaction failed; try next
            logger.debug(f"Selector {selector} failed: {e.__class__.__name__}")
            continue

    logger.debug("No cart button found with standard selectors")
    return False
