"""
Browser Worker - Async Playwright operations for the wizard.

Provides async browser automation for:
- Selector detection
- URL validation
- Login flow handling
"""

import asyncio
from typing import Dict, Optional, List
from pathlib import Path

from playwright.async_api import async_playwright, Page, Browser, BrowserContext


# Common selectors to try for each element type
TEXTAREA_SELECTORS = [
    "textarea.llm__textarea",
    "textarea[placeholder*='message']",
    "textarea[placeholder*='type']",
    "textarea[placeholder*='ask']",
    "textarea[placeholder*='chat']",
    ".chat-input textarea",
    "#chat-input",
    "textarea",
]

SUBMIT_SELECTORS = [
    "button.llm__submit",
    "button[type='submit']",
    "button[aria-label*='send']",
    "button[aria-label*='submit']",
    ".send-button",
    "#send-button",
    "button:has(svg)",  # Common pattern for icon buttons
]

BOT_MESSAGE_SELECTORS = [
    ".llm__bubbleSet--ai",
    ".bot-message",
    ".assistant-message",
    ".ai-message",
    "[data-role='assistant']",
    "[class*='bot']",
    "[class*='assistant']",
]

LOADING_SELECTORS = [
    ".llm__busyIndicator",
    ".loading",
    ".typing-indicator",
    "[class*='loading']",
    "[class*='typing']",
    "[class*='dots']",
]

CONTAINER_SELECTORS = [
    "section.llm__thread",
    ".chat-thread",
    ".message-container",
    ".chat-container",
    "#chat-container",
    "[class*='thread']",
    "[class*='messages']",
]


async def detect_selectors(
    url: str,
    quick_mode: bool = True,
    headless: bool = False,
    timeout: int = 30000,
) -> Optional[Dict[str, str]]:
    """
    Detect CSS selectors for chatbot UI elements.

    Args:
        url: The chatbot URL to analyze
        quick_mode: If True, just auto-detect. If False, wait for user interaction.
        headless: Run browser in headless mode
        timeout: Page load timeout in milliseconds

    Returns:
        Dictionary of selector_key -> selector_value, or None if failed
    """
    browser = None
    playwright = None

    try:
        playwright = await async_playwright().start()

        # Launch browser
        browser = await playwright.chromium.launch(
            headless=headless,
        )

        context = await browser.new_context(
            viewport={"width": 1280, "height": 720},
        )

        page = await context.new_page()

        # Navigate to URL
        await page.goto(url, wait_until="networkidle", timeout=timeout)

        # Wait a bit for dynamic content
        await asyncio.sleep(1)

        # Detect selectors
        detected = {}

        # Textarea
        detected["textarea"] = await _find_first_visible(page, TEXTAREA_SELECTORS)

        # Submit button
        detected["submit_button"] = await _find_first_visible(page, SUBMIT_SELECTORS)

        # Bot messages (might not exist yet)
        detected["bot_messages"] = await _find_first_visible(page, BOT_MESSAGE_SELECTORS)

        # Loading indicator (often hidden initially)
        detected["loading_indicator"] = await _find_first_selector(page, LOADING_SELECTORS)

        # Thread container
        detected["thread_container"] = await _find_first_visible(page, CONTAINER_SELECTORS)

        # Content inner - often same as container or child
        detected["content_inner"] = detected.get("thread_container", "")

        if not quick_mode:
            # In interactive mode, wait for user to close browser
            # This allows manual interaction with the page
            await page.wait_for_timeout(60000)  # 1 minute max

        await context.close()
        await browser.close()
        await playwright.stop()

        return detected

    except Exception as e:
        if browser:
            try:
                await browser.close()
            except:
                pass
        if playwright:
            try:
                await playwright.stop()
            except:
                pass
        raise e


async def _find_first_visible(page: Page, selectors: List[str]) -> str:
    """Find the first visible element matching any of the selectors."""
    for selector in selectors:
        try:
            element = await page.query_selector(selector)
            if element:
                is_visible = await element.is_visible()
                if is_visible:
                    return selector
        except:
            continue
    return ""


async def _find_first_selector(page: Page, selectors: List[str]) -> str:
    """Find the first element matching any selector (visible or not)."""
    for selector in selectors:
        try:
            element = await page.query_selector(selector)
            if element:
                return selector
        except:
            continue
    return ""


async def validate_url(url: str, timeout: int = 10000) -> tuple[bool, str]:
    """
    Validate that a URL is accessible and appears to be a chatbot.

    Args:
        url: URL to validate
        timeout: Request timeout in milliseconds

    Returns:
        Tuple of (is_valid, error_message)
    """
    playwright = None
    browser = None

    try:
        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        response = await page.goto(url, wait_until="domcontentloaded", timeout=timeout)

        if not response:
            return (False, "No response from server")

        if response.status >= 400:
            return (False, f"HTTP error: {response.status}")

        # Check for common chatbot indicators
        has_textarea = await page.query_selector("textarea") is not None
        has_input = await page.query_selector("input[type='text']") is not None

        if not (has_textarea or has_input):
            return (True, "Warning: No text input found - might not be a chatbot")

        await context.close()
        await browser.close()
        await playwright.stop()

        return (True, "")

    except Exception as e:
        if browser:
            try:
                await browser.close()
            except:
                pass
        if playwright:
            try:
                await playwright.stop()
            except:
                pass
        return (False, str(e))


async def test_selector(
    url: str,
    selector: str,
    timeout: int = 10000,
) -> tuple[bool, str]:
    """
    Test if a CSS selector finds elements on the page.

    Args:
        url: Page URL
        selector: CSS selector to test
        timeout: Page load timeout

    Returns:
        Tuple of (found, description)
    """
    playwright = None
    browser = None

    try:
        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        await page.goto(url, wait_until="networkidle", timeout=timeout)

        elements = await page.query_selector_all(selector)
        count = len(elements)

        if count == 0:
            result = (False, "No elements found")
        elif count == 1:
            is_visible = await elements[0].is_visible()
            result = (True, f"1 element found (visible: {is_visible})")
        else:
            result = (True, f"{count} elements found")

        await context.close()
        await browser.close()
        await playwright.stop()

        return result

    except Exception as e:
        if browser:
            try:
                await browser.close()
            except:
                pass
        if playwright:
            try:
                await playwright.stop()
            except:
                pass
        return (False, str(e))
