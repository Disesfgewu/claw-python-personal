from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_search_web_tool_returns_structured_json():
    """search_web_tool returns structured JSON per schema."""
    from claw.tools.search import search_web_tool

    mock_payload = {
        "query": "python asyncio tutorial",
        "raw_query": "python asyncio tutorial",
        "used_query": "python asyncio tutorial",
        "engine": "ddgs",
        "max_results": 5,
        "no_results": False,
        "error": "",
        "results": [
            {
                "rank": 1,
                "title": "Test Result",
                "url": "https://example.com",
                "snippet": "some snippet",
                "detail": "",
            }
        ],
    }
    with patch("claw.tools.search._mcp_search_structured_async", AsyncMock(return_value=mock_payload)):
        result = await search_web_tool("python asyncio tutorial")

    decoded = json.loads(result)
    assert decoded["query"] == "python asyncio tutorial"
    assert decoded["engine"] == "ddgs"
    assert len(decoded["results"]) == 1
    assert decoded["results"][0]["url"] == "https://example.com"


@pytest.mark.asyncio
async def test_search_web_empty_results():
    """search_web_tool returns structured JSON with no_results on empty result."""
    from claw.tools.search import search_web_tool

    mock_payload = {
        "query": "obscure query",
        "raw_query": "obscure query",
        "used_query": "obscure query",
        "engine": "ddgs",
        "max_results": 5,
        "no_results": True,
        "error": "",
        "results": [],
    }
    with patch("claw.tools.search._mcp_search_structured_async", AsyncMock(return_value=mock_payload)):
        result = await search_web_tool("obscure query")

    decoded = json.loads(result)
    assert decoded["no_results"] is True
    assert decoded["results"] == []


def test_extract_results_from_text_parses_url_reference_lines():
    """Parser should extract title/url/snippet from MCP text content."""
    from claw.tools.search import _extract_results_from_text

    text = (
        "[1] OpenAI\n"
        "URL: https://openai.com/\n"
        "Snippet: AI research and products\n\n"
        "[2] Example Domain\n"
        "https://example.com\n"
        "A placeholder page"
    )

    results, error = _extract_results_from_text(text)
    assert error is None
    assert len(results) == 2
    assert results[0]["title"] == "OpenAI"
    assert results[0]["url"] == "https://openai.com/"
    assert "AI research" in results[0]["snippet"]
    assert results[1]["url"] == "https://example.com"
