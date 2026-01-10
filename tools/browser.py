"""
Browser Tool - Playwright automation.
"""
from playwright.sync_api import sync_playwright, Page, Browser, Playwright
from typing import Optional
import time

class BrowserTool:
    """Tool for controlling a web browser."""
    
    def __init__(self, headless: bool = False):
        self.headless = headless
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._page: Optional[Page] = None
        self._context = None
        
    def _ensure_browser(self):
        """Start browser if not running."""
        if not self._playwright:
            self._playwright = sync_playwright().start()
        
        if not self._browser:
            self._browser = self._playwright.chromium.launch(headless=self.headless)
            self._context = self._browser.new_context(
                viewport={'width': 1280, 'height': 720},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            )
            self._page = self._context.new_page()
    
    def navigate(self, url: str) -> str:
        """Navigate to a URL."""
        try:
            self._ensure_browser()
            if not url.startswith('http'):
                url = 'https://' + url
            self._page.goto(url, wait_until='domcontentloaded')
            return f"Navigated to {url}. Page title: {self._page.title()}"
        except Exception as e:
            return f"Error navigating: {e}"

    def click(self, selector: str = None, x: int = None, y: int = None) -> str:
        """Click element or coordinates."""
        try:
            self._ensure_browser()
            if selector:
                self._page.click(selector)
                return f"Clicked element: {selector}"
            elif x is not None and y is not None:
                self._page.mouse.click(x, y)
                return f"Clicked coordinates: ({x}, {y})"
            else:
                return "Error: Must specify selector or x,y coordinates"
        except Exception as e:
            return f"Error clicking: {e}"

    def type_text(self, text: str, selector: str = None) -> str:
        """Type text into element or active element."""
        try:
            self._ensure_browser()
            if selector:
                self._page.fill(selector, text)
            else:
                self._page.keyboard.type(text)
            return f"Typed text: {text}"
        except Exception as e:
            return f"Error typing: {e}"

    def press_key(self, key: str) -> str:
        """Press a keyboard key."""
        try:
            self._ensure_browser()
            self._page.keyboard.press(key)
            return f"Pressed key: {key}"
        except Exception as e:
            return f"Error pressing key: {e}"

    def screenshot(self) -> str:
        """Take a screenshot."""
        try:
            self._ensure_browser()
            path = "browser_screenshot.png"
            self._page.screenshot(path=path)
            return f"Screenshot saved to {path}"
        except Exception as e:
            return f"Error taking screenshot: {e}"

    def get_content(self) -> str:
        """Get current page text content."""
        try:
            self._ensure_browser()
            # Get text but limit length to avoid overwhelming LLM
            content = self._page.inner_text("body")
            if not content or not content.strip():
                return "The page loaded but has no visible text content. It might be an empty page, a canvas, or a loading screen."
            return content[:2000] + ("..." if len(content) > 2000 else "")
        except Exception as e:
            return f"Error getting content: {e}"
    
    def close(self):
        """Close browser resources."""
        if self._browser:
            self._browser.close()
            self._browser = None
        if self._playwright:
            self._playwright.stop()
            self._playwright = None


# Singleton instance
_browser_tool: Optional[BrowserTool] = None

def get_browser() -> BrowserTool:
    """Get the browser tool singleton."""
    global _browser_tool
    if _browser_tool is None:
        _browser_tool = BrowserTool(headless=False)  # Show browser by default for "pro" visual agent
    return _browser_tool
