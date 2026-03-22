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
