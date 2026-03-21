from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_web_fetch_get_success():
    """Mock httpx to return 200, verify response includes [HTTP 200]."""
    from claw.tools.web_fetch import web_fetch

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = "Hello, world!"
    mock_response.content = b"Hello, world!"
    mock_response.headers = {"content-type": "text/plain"}

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_response)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await web_fetch("https://example.com")

    assert "[HTTP 200]" in result
    assert "Hello, world!" in result


@pytest.mark.asyncio
async def test_web_fetch_timeout():
    """Mock httpx to raise TimeoutException, verify error message."""
    import httpx
    from claw.tools.web_fetch import web_fetch

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("timed out"))

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await web_fetch("https://example.com", timeout=5)

    assert "timed out" in result.lower()
    assert "example.com" in result


@pytest.mark.asyncio
async def test_web_fetch_truncation():
    """Return content > 10000 chars, verify truncation message."""
    from claw.tools.web_fetch import web_fetch

    large_content = "x" * 15000
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = large_content
    mock_response.content = large_content.encode()
    mock_response.headers = {"content-type": "text/html"}

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_response)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await web_fetch("https://example.com")

    assert "truncated" in result
    assert len(result) < 15000 + 200  # should be significantly shorter than original
