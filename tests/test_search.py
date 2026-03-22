from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def _mock_mcp_response(results: list) -> MagicMock:
    resp = MagicMock()
    resp.json = MagicMock(return_value={
        "jsonrpc": "2.0",
        "id": 1,
        "result": {
            "content": [{"type": "text", "text": json.dumps(results)}]
        },
    })
    return resp


@pytest.mark.asyncio
async def test_search_web_calls_mcp_messages():
    """search_web_tool posts to /mcp/messages with correct JSON-RPC format."""
    from claw.tools.search import search_web_tool

    mock_results = [
        {"title": "Test Result", "href": "https://example.com", "body": "some snippet"},
    ]
    mock_resp = _mock_mcp_response(mock_results)
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_resp)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await search_web_tool("python asyncio tutorial")

    # Verify correct endpoint was called
    call_args = mock_client.post.call_args
    assert "/mcp/messages" in call_args[0][0]
    payload = call_args[1]["json"]
    assert payload["method"] == "tools/call"
    assert payload["params"]["name"] == "search_web"
    assert payload["params"]["arguments"]["query"] == "python asyncio tutorial"

    # Verify result is formatted correctly
    assert "[1]" in result
    assert "Test Result" in result
    assert "https://example.com" in result


@pytest.mark.asyncio
async def test_search_web_returns_multiple_results():
    """search_web_tool formats multiple results with numbered list."""
    from claw.tools.search import search_web_tool

    mock_results = [
        {"title": "Result A", "href": "https://a.com", "body": "body A"},
        {"title": "Result B", "href": "https://b.com", "body": "body B"},
        {"title": "Result C", "href": "https://c.com", "body": "body C"},
    ]
    mock_resp = _mock_mcp_response(mock_results)
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_resp)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await search_web_tool("test query")

    assert "[1]" in result
    assert "[2]" in result
    assert "[3]" in result


@pytest.mark.asyncio
async def test_search_web_empty_results():
    """search_web_tool returns '(no results)' when MCP returns empty list."""
    from claw.tools.search import search_web_tool

    mock_resp = _mock_mcp_response([])
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_resp)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await search_web_tool("obscure query")

    assert result == "(no results)"
