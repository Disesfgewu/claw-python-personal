import json
import pytest
import httpx
import respx
from unittest.mock import AsyncMock, MagicMock

from claw.llm.router_client import (
    LLMRouterClient, CompletionRequest, ChatMessage, StreamChunk, LLMRouterError
)


@respx.mock
@pytest.mark.asyncio
async def test_complete():
    client = LLMRouterClient(base_url="http://test")
    respx.post("http://test/v1/chat/completions").mock(
        return_value=httpx.Response(200, json={
            "choices": [{
                "message": {
                    "content": "ok",
                    "tool_calls": [
                        {"id": "1", "function": {"name": "t", "arguments": "{\"a\": 1}"}}
                    ],
                },
                "finish_reason": "stop",
            }],
            "model": "m",
            "usage": {"input": 1},
        })
    )

    req = CompletionRequest(messages=[ChatMessage(role="user", content="hi")])
    resp = await client.complete(req)
    assert resp.content == "ok"
    assert resp.model == "m"
    assert resp.tool_calls[0].name == "t"
    assert resp.tool_calls[0].arguments == {"a": 1}
    await client.close()


@respx.mock
@pytest.mark.asyncio
async def test_stream_parsing():
    client = LLMRouterClient(base_url="http://test")

    data1 = {"choices": [{"delta": {"content": "he"}}]}
    data2 = {"choices": [{"delta": {"content": "llo"}}], "usage": {"input": 1}}
    body = "".join([
        f"data: {json.dumps(data1)}\n\n",
        f"data: {json.dumps(data2)}\n\n",
        "data: [DONE]\n\n",
    ])

    respx.post("http://test/v1/chat/completions").mock(
        return_value=httpx.Response(200, content=body.encode("utf-8"))
    )

    req = CompletionRequest(messages=[ChatMessage(role="user", content="hi")])
    chunks = []
    async for c in client.stream(req):
        chunks.append(c)

    assert "".join([c.content for c in chunks]) == "hello"
    assert chunks[-1].usage == {"input": 1}
    await client.close()


@respx.mock
@pytest.mark.asyncio
async def test_stream_tool_call_delta():
    client = LLMRouterClient(base_url="http://test")

    data1 = {
        "choices": [{
            "delta": {
                "tool_calls": [
                    {"index": 0, "id": "c1", "function": {"name": "bash", "arguments": "{\"cmd\":"}}
                ]
            }
        }]
    }
    data2 = {
        "choices": [{
            "delta": {
                "tool_calls": [
                    {"index": 0, "function": {"arguments": "\"ls\"}"}}
                ]
            }
        }]
    }
    body = "".join([
        f"data: {json.dumps(data1)}\n\n",
        f"data: {json.dumps(data2)}\n\n",
        "data: [DONE]\n\n",
    ])

    respx.post("http://test/v1/chat/completions").mock(
        return_value=httpx.Response(200, content=body.encode("utf-8"))
    )

    req = CompletionRequest(messages=[ChatMessage(role="user", content="hi")])
    chunks = []
    async for c in client.stream(req):
        chunks.append(c)

    assert any(c.tool_call_delta for c in chunks)
    await client.close()


@respx.mock
@pytest.mark.asyncio
async def test_health_check_error():
    client = LLMRouterClient(base_url="http://test")
    respx.post("http://test/v1/chat/completions").mock(
        return_value=httpx.Response(500, json={"error": "boom"})
    )
    with pytest.raises(LLMRouterError):
        await client.health_check()
    await client.close()


@pytest.mark.asyncio
async def test_llm_router_get_embedding_success(monkeypatch):
    """get_embedding() 應正確返回嵌入向量"""
    client = LLMRouterClient(base_url="http://localhost:8000")

    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "data": [{"embedding": [0.1, 0.2, 0.3]}]
    }
    mock_resp.raise_for_status = MagicMock()

    mock_post = AsyncMock(return_value=mock_resp)
    monkeypatch.setattr(client._client, "post", mock_post)

    result = await client.get_embedding("test text")

    assert result == [0.1, 0.2, 0.3]
    mock_post.assert_called_once()
