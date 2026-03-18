import pytest
import asyncio
import json
from claw.agent.multi_agent import MultiAgentCoordinator
from claw.core.storage import Storage, SessionRow, now_iso
from claw.llm.router_client import StreamChunk


class FakeLLM:
    async def stream(self, req):
        yield StreamChunk(content="hello from child")
        yield StreamChunk(usage={"input": 1})


@pytest.mark.asyncio
async def test_sessions_send_returns_response(tmp_path):
    storage = Storage(db_path=str(tmp_path / "claw.db"))
    storage.transcript_dir = str(tmp_path / "t")
    await storage.init()
    await storage.create_session(SessionRow(
        session_id="agent:main", scope="main", channel=None, agent_id="default",
        system_prompt=None, queue_mode="collect", sandbox=False,
        created_at=now_iso(), last_active=now_iso(), config={},
    ))
    coord = MultiAgentCoordinator(storage=storage, llm=FakeLLM())
    result = await coord.send("agent:main", "hello")
    assert "hello from child" in result


@pytest.mark.asyncio
async def test_sessions_spawn_creates_session(tmp_path):
    storage = Storage(db_path=str(tmp_path / "claw.db"))
    storage.transcript_dir = str(tmp_path / "t")
    await storage.init()
    coord = MultiAgentCoordinator(storage=storage, llm=FakeLLM())
    child_id = await coord.spawn("do something")
    await asyncio.sleep(0.05)
    sessions = await coord.list_sessions()
    ids = [s.session_id for s in sessions]
    assert child_id in ids


@pytest.mark.asyncio
async def test_sessions_list(tmp_path):
    storage = Storage(db_path=str(tmp_path / "claw.db"))
    storage.transcript_dir = str(tmp_path / "t")
    await storage.init()
    await storage.create_session(SessionRow(
        session_id="agent:main", scope="main", channel=None, agent_id="default",
        system_prompt=None, queue_mode="collect", sandbox=False,
        created_at=now_iso(), last_active=now_iso(), config={},
    ))
    coord = MultiAgentCoordinator(storage=storage, llm=FakeLLM())
    result = await coord.list_sessions()
    assert any(s.session_id == "agent:main" for s in result)
