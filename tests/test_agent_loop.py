import pytest

from claw.agent.loop import AgentLoop, MAX_TOOL_ROUNDS
from claw.agent.events import TextChunk, ToolCallStart, ToolCallResult, RunComplete, RunError
from claw.core.storage import Storage, SessionRow, now_iso
from claw.llm.router_client import StreamChunk, ChatMessage
from claw.tools import registry


class FakeLLM:
    def __init__(self, sequences):
        self.sequences = sequences
        self.calls = 0

    async def stream(self, req):
        seq = self.sequences[self.calls]
        self.calls += 1
        for item in seq:
            yield item


@pytest.mark.asyncio
async def test_agent_loop_text_only(tmp_path):
    registry._registry = {}
    storage = Storage(db_path=str(tmp_path / "claw.db"))
    storage.transcript_dir = str(tmp_path / "transcripts")
    await storage.init()

    await storage.create_session(SessionRow(
        session_id="agent:main",
        scope="main",
        channel=None,
        agent_id="default",
        system_prompt=None,
        queue_mode="collect",
        sandbox=False,
        created_at=now_iso(),
        last_active=now_iso(),
        config={},
    ))

    fake_llm = FakeLLM([[StreamChunk(content="hi"), StreamChunk(usage={"input": 1})]])
    loop = AgentLoop(storage=storage, llm=fake_llm)

    events = []
    async for e in loop.run("agent:main", "hello"):
        events.append(e)

    assert any(isinstance(e, TextChunk) for e in events)
    assert any(isinstance(e, RunComplete) for e in events)


@pytest.mark.asyncio
async def test_agent_loop_tool_call(tmp_path):
    registry._registry = {}

    @registry.tool(
        name="mock",
        description="mock",
        parameters={"type": "object", "properties": {"x": {"type": "integer"}}},
        requires_main=True,
    )
    async def mock_tool(x: int = 0):
        return f"tool:{x}"

    storage = Storage(db_path=str(tmp_path / "claw.db"))
    storage.transcript_dir = str(tmp_path / "transcripts")
    await storage.init()

    await storage.create_session(SessionRow(
        session_id="agent:main",
        scope="main",
        channel=None,
        agent_id="default",
        system_prompt=None,
        queue_mode="collect",
        sandbox=False,
        created_at=now_iso(),
        last_active=now_iso(),
        config={},
    ))

    seq1 = [
        StreamChunk(tool_call_delta=[{
            "index": 0,
            "id": "call1",
            "function": {"name": "mock", "arguments": "{\"x\": 1}"},
        }])
    ]
    seq2 = [StreamChunk(content="done"), StreamChunk(usage={"input": 1})]

    fake_llm = FakeLLM([seq1, seq2])
    loop = AgentLoop(storage=storage, llm=fake_llm)

    events = []
    async for e in loop.run("agent:main", "hello"):
        events.append(e)

    assert any(isinstance(e, ToolCallStart) for e in events)
    assert any(isinstance(e, ToolCallResult) for e in events)
    assert any(isinstance(e, TextChunk) for e in events)
    assert any(isinstance(e, RunComplete) for e in events)


@pytest.mark.asyncio
async def test_agent_loop_max_tool_rounds(tmp_path):
    registry._registry = {}

    @registry.tool(
        name="mock",
        description="mock",
        parameters={"type": "object", "properties": {}},
        requires_main=True,
    )
    async def mock_tool():
        return "ok"

    storage = Storage(db_path=str(tmp_path / "claw.db"))
    storage.transcript_dir = str(tmp_path / "transcripts")
    await storage.init()

    await storage.create_session(SessionRow(
        session_id="agent:main",
        scope="main",
        channel=None,
        agent_id="default",
        system_prompt=None,
        queue_mode="collect",
        sandbox=False,
        created_at=now_iso(),
        last_active=now_iso(),
        config={},
    ))

    seqs = []
    for i in range(MAX_TOOL_ROUNDS + 1):
        seqs.append([
            StreamChunk(tool_call_delta=[{
                "index": 0,
                "id": f"call{i}",
                "function": {"name": "mock", "arguments": "{}"},
            }])
        ])

    fake_llm = FakeLLM(seqs)
    loop = AgentLoop(storage=storage, llm=fake_llm)

    events = []
    async for e in loop.run("agent:main", "hello"):
        events.append(e)

    assert fake_llm.calls == MAX_TOOL_ROUNDS + 1
    assert any(isinstance(e, RunComplete) for e in events)


@pytest.mark.asyncio
async def test_agent_loop_llm_error(tmp_path):
    registry._registry = {}

    class ErrorLLM:
        async def stream(self, req):
            raise RuntimeError("boom")
            yield  # pragma: no cover

    storage = Storage(db_path=str(tmp_path / "claw.db"))
    storage.transcript_dir = str(tmp_path / "transcripts")
    await storage.init()

    await storage.create_session(SessionRow(
        session_id="agent:main",
        scope="main",
        channel=None,
        agent_id="default",
        system_prompt=None,
        queue_mode="collect",
        sandbox=False,
        created_at=now_iso(),
        last_active=now_iso(),
        config={},
    ))

    loop = AgentLoop(storage=storage, llm=ErrorLLM())

    events = []
    async for e in loop.run("agent:main", "hello"):
        events.append(e)

    assert any(isinstance(e, RunError) for e in events)


@pytest.mark.asyncio
async def test_agent_loop_memory_recall_empty_list():
    """Memory recall 返回空列表時應不報錯"""
    from unittest.mock import AsyncMock, MagicMock
    from types import SimpleNamespace

    # 準備 mock
    mock_storage = MagicMock()
    mock_storage.get_session = AsyncMock(return_value=SimpleNamespace(system_prompt="sys"))
    mock_storage.get_messages = AsyncMock(return_value=[])
    mock_storage.append_transcript = MagicMock()
    mock_storage.add_message = AsyncMock()
    mock_storage.update_last_active = AsyncMock()

    seq = [StreamChunk(content="done"), StreamChunk(usage={"input": 1})]
    mock_llm = FakeLLM([seq])
    
    mock_memory = AsyncMock()
    mock_memory.search = AsyncMock(return_value=[])  # 空列表

    loop = AgentLoop(storage=mock_storage, llm=mock_llm, memory=mock_memory)

    # 運行 agent
    events = []
    async for event in loop.run(session_id="test", user_message="hello"):
        events.append(event)

    # 應完成執行，不報錯
    assert any(isinstance(e, RunComplete) for e in events)
