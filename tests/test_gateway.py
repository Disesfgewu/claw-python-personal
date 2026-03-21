import json
import pytest
import httpx

import claw.core.gateway as gateway_module
from claw.core.storage import Storage
from claw.core.queue import MessageQueue
from claw.llm.router_client import StreamChunk


class FakeLLM:
    def __init__(self, chunks):
        self.chunks = chunks

    async def stream(self, req):
        for c in self.chunks:
            yield c

    async def health_check(self):
        return {"ok": True}


@pytest.mark.asyncio
async def test_health(tmp_path):
    storage = Storage(db_path=str(tmp_path / "claw.db"))
    storage.transcript_dir = str(tmp_path / "transcripts")
    await storage.init()

    gateway_module.storage = storage
    gateway_module.queue = MessageQueue()
    gateway_module.llm = FakeLLM([StreamChunk(content="hi")])

    transport = httpx.ASGITransport(app=gateway_module.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_chat_completions_non_stream(tmp_path):
    storage = Storage(db_path=str(tmp_path / "claw.db"))
    storage.transcript_dir = str(tmp_path / "transcripts")
    await storage.init()

    gateway_module.storage = storage
    gateway_module.queue = MessageQueue()
    gateway_module.llm = FakeLLM([StreamChunk(content="hi"), StreamChunk(usage={"input": 1})])

    transport = httpx.ASGITransport(app=gateway_module.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/v1/chat/completions", json={
            "session_id": "agent:main",
            "messages": [{"role": "user", "content": "hello"}],
            "model": "auto",
            "stream": False,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["choices"][0]["message"]["content"] == "hi"


@pytest.mark.asyncio
async def test_chat_completions_stream(tmp_path):
    storage = Storage(db_path=str(tmp_path / "claw.db"))
    storage.transcript_dir = str(tmp_path / "transcripts")
    await storage.init()

    gateway_module.storage = storage
    gateway_module.queue = MessageQueue()
    gateway_module.llm = FakeLLM([StreamChunk(content="hi"), StreamChunk(usage={"input": 1})])

    transport = httpx.ASGITransport(app=gateway_module.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        async with client.stream("POST", "/v1/chat/completions", json={
            "session_id": "agent:main",
            "messages": [{"role": "user", "content": "hello"}],
            "model": "auto",
            "stream": True,
        }) as resp:
            assert resp.status_code == 200
            lines = []
            async for line in resp.aiter_lines():
                if line:
                    lines.append(line)

    assert any(line.startswith("data: ") for line in lines)
    assert any("[DONE]" in line for line in lines)


@pytest.mark.asyncio
async def test_require_dependencies_with_all_none():
    """_require_dependencies 在所有依賴都是 None 時應拋出異常"""
    import claw.core.gateway as gw
    original_storage = gw.storage
    original_queue = gw.queue
    original_llm = gw.llm

    try:
        gw.storage = None
        gw.queue = None
        gw.llm = None

        with pytest.raises(RuntimeError, match="dependencies are not configured"):
            gw._require_dependencies()
    finally:
        gw.storage = original_storage
        gw.queue = original_queue
        gw.llm = original_llm
