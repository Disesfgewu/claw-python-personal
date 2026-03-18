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
