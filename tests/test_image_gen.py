from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_image_gen_success():
    """image_gen successfully posts to LLM-Router /v1/images/generations."""
    from claw.tools.image_gen import image_gen

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json = MagicMock(return_value={
        "data": [{"url": "https://example.com/image.png"}]
    })
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_response)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await image_gen("a cat sitting on a table")

    assert "URL" in result
    assert "example.com/image.png" in result
    mock_client.post.assert_called_once()
    call_args = mock_client.post.call_args
    assert "/v1/images/generations" in call_args[0][0]
    payload = call_args[1]["json"]
    assert payload["prompt"] == "a cat sitting on a table"


@pytest.mark.asyncio
async def test_image_gen_b64_response():
    """image_gen handles base64 response format."""
    from claw.tools.image_gen import image_gen

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json = MagicMock(return_value={
        "data": [{"b64_json": "iVBORw0KGg..." + "X" * 100}]
    })
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_response)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await image_gen("test", response_format="b64_json")

    assert "Base64" in result
    assert "truncated" in result


@pytest.mark.asyncio
async def test_image_gen_timeout():
    """image_gen handles timeout gracefully."""
    import httpx
    from claw.tools.image_gen import image_gen

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("timeout"))

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await image_gen("test")

    assert "timed out" in result.lower()
