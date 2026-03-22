# Phase 13 Worker Prompt — Browser Tool (Playwright)

你是實作 claw-python Phase 13 的 worker。工作目錄：`/home/martin/Desktop/claw-python-personal/`。
當前狀態：160 tests 通過（Phase 12 完成），0 failures。**嚴格按照順序，每步驗證後再繼續。**

---

## 背景說明

AutoResearch 框架需要瀏覽 JavaScript 渲染的網頁。目前 `web_fetch` 只能抓 HTML 源碼，不執行 JS。本 Phase 實作 Playwright 頭部瀏覽器工具讓 agent 可以取得渲染後的頁面內容並截圖。

---

## 設計規格

- **Transport**: Headless Chromium (Playwright async API)
- **Workspace**: Session 專屬目錄 `~/.claw/workspaces/{session_id}/screenshots/`
- **Tools**: 兩個工具
  - `browser_navigate(url, wait_selector)` → 等待選擇器出現後回傳 HTML
  - `browser_extract(css_selector)` → 從當前頁面抽取選中元素的文本
  - 隱含 `browser_close()` 在工作流末尾自動呼叫
- **Sandbox**: 每個 session 最多一個瀏覽器實例，session 結束時自動關閉

---

## Task 1 — 安裝 Playwright

檢查 `pyproject.toml`，在 `dependencies` 加入：

```toml
"playwright>=1.40.0",
```

然後執行：

```bash
pip install playwright
playwright install chromium  # 下載 Chromium binary
```

---

## Task 2 — 建立 `claw/tools/browser.py`

```python
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
```

---

## Task 3 — 在 `claw/tools/__init__.py` 加入 import

在末尾加入：

```python
import claw.tools.browser as _browser  # noqa: F401
```

---

## Task 4 — 在 `claw/main.py` 加入 import

在工具 import 區塊加入：

```python
import claw.tools.browser         # 觸發 browser_navigate/extract/close 工具注冊
```

---

## Task 5 — 建立測試 `tests/test_browser.py`（4 tests）

```python
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, ANY


@pytest.mark.asyncio
async def test_browser_navigate_success():
    """browser_navigate loads a URL and returns HTML."""
    from claw.tools.browser import browser_navigate

    mock_page = AsyncMock()
    mock_page.content = AsyncMock(return_value="<html><body>Test</body></html>")
    mock_page.goto = AsyncMock()
    mock_page.wait_for_selector = AsyncMock()

    with patch("claw.tools.browser._get_page_for_session", return_value=mock_page):
        result = await browser_navigate("https://example.com")

    assert "<html>" in result
    mock_page.goto.assert_called_once()


@pytest.mark.asyncio
async def test_browser_navigate_with_wait():
    """browser_navigate waits for selector before returning."""
    from claw.tools.browser import browser_navigate

    mock_page = AsyncMock()
    mock_page.content = AsyncMock(return_value="<div id='loaded'>Content</div>")
    mock_page.goto = AsyncMock()
    mock_page.wait_for_selector = AsyncMock()

    with patch("claw.tools.browser._get_page_for_session", return_value=mock_page):
        result = await browser_navigate("https://example.com", wait_selector="#loaded")

    mock_page.wait_for_selector.assert_called_once_with("#loaded", timeout=30_000)


@pytest.mark.asyncio
async def test_browser_extract_success():
    """browser_extract finds element and returns text."""
    from claw.tools.browser import browser_extract

    mock_element = AsyncMock()
    mock_element.text_content = AsyncMock(return_value="Hello World")

    mock_page = AsyncMock()
    mock_page.query_selector = AsyncMock(return_value=mock_element)

    with patch("claw.tools.browser._get_page_for_session", return_value=mock_page):
        result = await browser_extract("h1")

    assert "Hello World" in result


@pytest.mark.asyncio
async def test_browser_extract_not_found():
    """browser_extract returns error if selector not found."""
    from claw.tools.browser import browser_extract

    mock_page = AsyncMock()
    mock_page.query_selector = AsyncMock(return_value=None)

    with patch("claw.tools.browser._get_page_for_session", return_value=mock_page):
        result = await browser_extract("h1")

    assert "not found" in result.lower()
```

---

## Task 6 — 執行測試

```bash
cd /home/martin/Desktop/claw-python-personal
python -m pytest tests/ -x --tb=short
```

預期：**164 tests 通過，0 failures**（160 + 4 新增）

---

## 交付清單

完成後回報：
1. 每個新建/修改的檔案絕對路徑
2. pytest 最終輸出最後 5 行
3. 遇到的問題和解決方式

---

## 預期測試計數

| 來源 | 數量 |
|---|---|
| Phase 12（現有） | 160 |
| test_browser.py | +4 |
| **目標** | **164** |
