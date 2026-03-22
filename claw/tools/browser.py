from __future__ import annotations

import asyncio
from pathlib import Path
from playwright.async_api import async_playwright, Browser, Page
from claw.tools.registry import tool


# 全域 session → browser 映射
_session_browsers: dict[str, Browser] = {}
_session_pages: dict[str, Page] = {}


async def _get_browser_for_session(session_id: str) -> Browser:
    """Lazy-load browser instance for session; reuse if exists."""
    if session_id not in _session_browsers:
        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(headless=True)
        _session_browsers[session_id] = browser
    return _session_browsers[session_id]


async def _get_page_for_session(session_id: str) -> Page:
    """Get or create page for session."""
    if session_id not in _session_pages:
        browser = await _get_browser_for_session(session_id)
        _session_pages[session_id] = await browser.new_page()
    return _session_pages[session_id]


async def _close_browser_for_session(session_id: str) -> None:
    """Close browser and page for session on cleanup."""
    if session_id in _session_pages:
        await _session_pages[session_id].close()
        del _session_pages[session_id]
    if session_id in _session_browsers:
        await _session_browsers[session_id].close()
        del _session_browsers[session_id]


@tool(
    name="browser_navigate",
    description="瀏覽網頁。指定 URL，可選 wait_selector 等待頁面渲染。回傳最終 HTML。",
    parameters={
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "要瀏覽的 URL（http:// 或 https://）",
            },
            "wait_selector": {
                "type": "string",
                "description": "可選：CSS selector，等待此元素出現才回傳（最多 30s）",
            },
        },
        "required": ["url"],
    },
    requires_main=False,
)
async def browser_navigate(
    url: str,
    wait_selector: str = "",
    session_id: str = "agent:main",
) -> str:
    """Navigate to URL and return rendered HTML."""
    try:
        page = await _get_page_for_session(session_id)
        await page.goto(url, wait_until="networkidle", timeout=30_000)

        if wait_selector:
            try:
                await page.wait_for_selector(wait_selector, timeout=30_000)
            except Exception as e:
                return f"Warning: selector '{wait_selector}' not found: {e}. Returning page content anyway."

        html = await page.content()
        # Truncate if too large
        if len(html) > 50_000:
            html = html[:50_000] + f"\n[truncated — original {len(html)} bytes]"
        return html
    except Exception as e:
        return f"Error: {type(e).__name__}: {e}"


@tool(
    name="browser_extract",
    description="從當前頁面抽取文本。用 CSS selector 選中元素，回傳選中元素的 textContent。",
    parameters={
        "type": "object",
        "properties": {
            "selector": {
                "type": "string",
                "description": "CSS selector 用來選中元素（例：'h1', '.article-body', '#main-content'）",
            },
        },
        "required": ["selector"],
    },
    requires_main=False,
)
async def browser_extract(
    selector: str,
    session_id: str = "agent:main",
) -> str:
    """Extract text from current page using CSS selector."""
    try:
        page = await _get_page_for_session(session_id)
        element = await page.query_selector(selector)
        if element is None:
            return f"Error: selector '{selector}' not found on current page"

        text = await element.text_content()
        # Truncate if too large
        if text and len(text) > 10_000:
            text = text[:10_000] + f"\n[truncated — original {len(text)} chars]"
        return text or "(element has no text content)"
    except Exception as e:
        return f"Error: {type(e).__name__}: {e}"


@tool(
    name="browser_close",
    description="關閉瀏覽器連線（通常自動在 session 結束時呼叫）。",
    parameters={"type": "object", "properties": {}},
    requires_main=False,
)
async def browser_close(session_id: str = "agent:main") -> str:
    """Close browser for this session."""
    try:
        await _close_browser_for_session(session_id)
        return "✅ Browser closed"
    except Exception as e:
        return f"Error: {type(e).__name__}: {e}"


# Hook: session 結束時自動清理 browser
async def _cleanup_browser_on_session_end(session_id: str) -> None:
    """Called by agent loop on session teardown."""
    await _close_browser_for_session(session_id)
