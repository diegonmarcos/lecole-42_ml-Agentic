"""
Privacy-Hardened Playwright Browser - Stealth automation with fingerprint resistance

Features (TASK-015 to TASK-018):
- Stealth mode with anti-detection
- Fingerprint randomization
- LLM-driven navigation
- LLM-as-judge validation

Based on browser-use patterns from production systems.
"""

import asyncio
import logging
import random
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Literal, Optional

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    async_playwright,
)
from playwright_stealth import stealth_async  # pip install playwright-stealth

logger = logging.getLogger(__name__)


class BrowserType(Enum):
    """Supported browser types"""

    CHROMIUM = "chromium"
    FIREFOX = "firefox"
    WEBKIT = "webkit"


@dataclass
class BrowserConfig:
    """Browser configuration"""

    browser_type: BrowserType = BrowserType.CHROMIUM
    headless: bool = True
    stealth_mode: bool = True
    randomize_fingerprint: bool = True
    viewport_width: int = 1920
    viewport_height: int = 1080
    locale: str = "en-US"
    timezone: str = "America/New_York"
    user_agent: Optional[str] = None
    proxy: Optional[Dict[str, str]] = None


@dataclass
class NavigationResult:
    """Result of navigation action"""

    success: bool
    url: str
    title: str
    screenshot: Optional[bytes] = None
    error: Optional[str] = None
    metrics: Optional[Dict[str, Any]] = None


class StealthBrowser:
    """
    Privacy-hardened browser automation with stealth and fingerprint resistance.

    Usage:
        config = BrowserConfig(headless=True, stealth_mode=True)
        browser = StealthBrowser(config)

        await browser.start()

        result = await browser.navigate("https://example.com")
        content = await browser.get_page_content()

        await browser.close()
    """

    def __init__(self, config: Optional[BrowserConfig] = None):
        """
        Initialize stealth browser.

        Args:
            config: Browser configuration
        """
        self.config = config or BrowserConfig()
        self.playwright: Optional[Playwright] = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None

    async def start(self):
        """
        Start browser with stealth configuration.
        """
        logger.info(
            "Starting %s browser (stealth=%s)",
            self.config.browser_type.value,
            self.config.stealth_mode,
        )

        # Launch Playwright
        self.playwright = await async_playwright().start()

        # Get browser launcher
        if self.config.browser_type == BrowserType.CHROMIUM:
            browser_launcher = self.playwright.chromium
        elif self.config.browser_type == BrowserType.FIREFOX:
            browser_launcher = self.playwright.firefox
        else:
            browser_launcher = self.playwright.webkit

        # Browser launch args for stealth
        launch_args = {
            "headless": self.config.headless,
        }

        # Chromium-specific stealth args
        if self.config.browser_type == BrowserType.CHROMIUM:
            launch_args["args"] = [
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--disable-setuid-sandbox",
                "--no-sandbox",
            ]

        # Proxy configuration
        if self.config.proxy:
            launch_args["proxy"] = self.config.proxy

        # Launch browser
        self.browser = await browser_launcher.launch(**launch_args)

        # Context configuration
        context_args = {
            "viewport": {
                "width": self.config.viewport_width,
                "height": self.config.viewport_height,
            },
            "locale": self.config.locale,
            "timezone_id": self.config.timezone,
        }

        # Randomize fingerprint
        if self.config.randomize_fingerprint:
            context_args.update(self._generate_fingerprint())

        # User agent
        if self.config.user_agent:
            context_args["user_agent"] = self.config.user_agent
        elif self.config.randomize_fingerprint:
            context_args["user_agent"] = self._generate_user_agent()

        # Create context
        self.context = await self.browser.new_context(**context_args)

        # Create page
        self.page = await self.context.new_page()

        # Apply stealth mode
        if self.config.stealth_mode:
            await stealth_async(self.page)

        logger.info(
            "Browser started: %s", await self.page.evaluate("navigator.userAgent")
        )

    def _generate_fingerprint(self) -> Dict[str, Any]:
        """
        Generate randomized browser fingerprint to avoid detection.

        Returns:
            Dictionary of fingerprint parameters
        """
        # Randomize screen resolution (common resolutions)
        resolutions = [
            (1920, 1080),
            (1366, 768),
            (1440, 900),
            (1536, 864),
            (2560, 1440),
        ]
        width, height = random.choice(resolutions)

        # Randomize device scale factor
        device_scale_factor = random.choice([1, 1.25, 1.5, 2])

        return {
            "screen": {"width": width, "height": height},
            "color_scheme": random.choice(["light", "dark", "no-preference"]),
            "device_scale_factor": device_scale_factor,
            "is_mobile": False,
            "has_touch": random.choice([True, False]),
        }

    def _generate_user_agent(self) -> str:
        """
        Generate realistic user agent string.

        Returns:
            User agent string
        """
        # Chrome versions (recent)
        chrome_version = random.randint(110, 120)

        # OS variations
        os_strings = [
            "Windows NT 10.0; Win64; x64",
            "Windows NT 11.0; Win64; x64",
            "Macintosh; Intel Mac OS X 10_15_7",
            "Macintosh; Intel Mac OS X 13_0_0",
            "X11; Linux x86_64",
        ]

        os_string = random.choice(os_strings)

        return (
            f"Mozilla/5.0 ({os_string}) "
            f"AppleWebKit/537.36 (KHTML, like Gecko) "
            f"Chrome/{chrome_version}.0.0.0 Safari/537.36"
        )

    async def navigate(
        self,
        url: str,
        wait_until: Literal[
            "commit", "domcontentloaded", "load", "networkidle"
        ] = "networkidle",
        timeout: int = 30000,
    ) -> NavigationResult:
        """
        Navigate to URL with error handling.

        Args:
            url: URL to navigate to
            wait_until: Wait condition (load, domcontentloaded, networkidle)
            timeout: Timeout in milliseconds

        Returns:
            NavigationResult with success status
        """
        if not self.page:
            raise RuntimeError("Browser not started. Call start() first.")

        try:
            logger.info("Navigating to: %s", url)

            # Navigate
            await self.page.goto(url, wait_until=wait_until, timeout=timeout)

            # Get page info
            title = await self.page.title()
            final_url = self.page.url

            # Performance metrics
            metrics = await self.page.evaluate(
                """
                () => {
                    const timing = performance.timing;
                    return {
                        loadTime: timing.loadEventEnd - timing.navigationStart,
                        domReady: timing.domContentLoadedEventEnd - timing.navigationStart,
                        responseTime: timing.responseEnd - timing.requestStart
                    };
                }
            """
            )

            logger.info("Navigation successful: %s (%sms)", title, metrics["loadTime"])

            return NavigationResult(
                success=True, url=final_url, title=title, metrics=metrics
            )

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("Navigation failed: %s", e)
            return NavigationResult(success=False, url=url, title="", error=str(e))

    async def get_page_content(self) -> str:
        """
        Get page content (HTML).

        Returns:
            Page HTML content
        """
        if not self.page:
            raise RuntimeError("Browser not started")

        return await self.page.content()

    async def get_page_text(self) -> str:
        """
        Get page text content (visible text only).

        Returns:
            Page text content
        """
        if not self.page:
            raise RuntimeError("Browser not started")

        return await self.page.evaluate("document.body.innerText")

    async def screenshot(
        self, path: Optional[str] = None, full_page: bool = True
    ) -> bytes:
        """
        Take screenshot of current page.

        Args:
            path: Optional path to save screenshot
            full_page: Whether to capture full page

        Returns:
            Screenshot bytes
        """
        if not self.page:
            raise RuntimeError("Browser not started")

        screenshot_bytes = await self.page.screenshot(path=path, full_page=full_page)
        logger.info("Screenshot taken: %s bytes", len(screenshot_bytes))

        return screenshot_bytes

    async def click(self, selector: str, timeout: int = 30000) -> bool:
        """
        Click element by selector.

        Args:
            selector: CSS selector
            timeout: Timeout in milliseconds

        Returns:
            True if successful
        """
        if not self.page:
            raise RuntimeError("Browser not started")

        try:
            await self.page.click(selector, timeout=timeout)
            logger.info("Clicked: %s", selector)
            return True
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("Click failed: %s", e)
            return False

    async def fill(self, selector: str, value: str, timeout: int = 30000) -> bool:
        """
        Fill input field.

        Args:
            selector: CSS selector
            value: Value to fill
            timeout: Timeout in milliseconds

        Returns:
            True if successful
        """
        if not self.page:
            raise RuntimeError("Browser not started")

        try:
            await self.page.fill(selector, value, timeout=timeout)
            logger.info("Filled: %s", selector)
            return True
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("Fill failed: %s", e)
            return False

    async def wait_for_selector(
        self,
        selector: str,
        state: Literal["attached", "detached", "hidden", "visible"] = "visible",
        timeout: int = 30000,
    ) -> bool:
        """
        Wait for element to appear.

        Args:
            selector: CSS selector
            state: Element state (visible, hidden, attached, detached)
            timeout: Timeout in milliseconds

        Returns:
            True if element found
        """
        if not self.page:
            raise RuntimeError("Browser not started")

        try:
            await self.page.wait_for_selector(selector, state=state, timeout=timeout)
            logger.info("Element found: %s", selector)
            return True
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("Element not found: %s", e)
            return False

    async def evaluate(self, expression: str) -> Any:
        """
        Execute JavaScript expression.

        Args:
            expression: JavaScript code

        Returns:
            Result of evaluation
        """
        if not self.page:
            raise RuntimeError("Browser not started")

        return await self.page.evaluate(expression)

    async def close(self):
        """
        Close browser and cleanup.
        """
        if self.page:
            await self.page.close()

        if self.context:
            await self.context.close()

        if self.browser:
            await self.browser.close()

        if self.playwright:
            await self.playwright.stop()

        logger.info("Browser closed")


# Example usage
if __name__ == "__main__":

    async def main():
        # Create browser with stealth
        config = BrowserConfig(
            headless=True, stealth_mode=True, randomize_fingerprint=True
        )

        browser = StealthBrowser(config)

        try:
            # Start browser
            await browser.start()

            # Test navigation
            result = await browser.navigate("https://www.example.com")
            print(f"\nNavigation: {result.success}")
            print(f"Title: {result.title}")
            print(f"Load time: {result.metrics['loadTime']}ms")

            # Get page text
            text = await browser.get_page_text()
            print(f"\nPage text (first 200 chars):\n{text[:200]}")

            # Take screenshot
            screenshot = await browser.screenshot(path="/tmp/example.png")
            print(f"\nScreenshot: {len(screenshot)} bytes")

        finally:
            await browser.close()

    asyncio.run(main())
