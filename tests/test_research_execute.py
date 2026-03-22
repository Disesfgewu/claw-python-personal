from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock
from claw.research.loop import ResearchLoop
from claw.research.ledger import ResearchLedger
from claw.core.storage import Storage
from claw.agent.events import TextChunk, ToolCallResult, RunComplete


async def _aiter(items):
    for item in items:
        yield item


@pytest.fixture
async def storage(tmp_path):
    db = str(tmp_path / "test.db")
    s = Storage(db_path=db, transcript_dir=str(tmp_path / "transcripts"))
    await s.init()
    return s


@pytest.mark.asyncio
async def test_execute_fallback_without_agent_loop(storage):
    """Without agent_loop, _execute falls back to direct LLM."""
    mock_llm = AsyncMock()
    chunk = MagicMock()
    chunk.content = "LLM fallback output"
    mock_llm.stream = MagicMock(return_value=_aiter([chunk]))

    loop = ResearchLoop(llm=mock_llm, ledger=ResearchLedger(db_path=storage.db_path))
    assert loop.agent_loop is None

    approach, output = await loop._execute_via_llm("test hypothesis")
    assert approach == "direct-llm"
    assert "LLM fallback output" in output


@pytest.mark.asyncio
async def test_execute_via_agent_creates_sub_session(storage):
    """With agent_loop, _execute creates a sub-session and collects events."""
    mock_llm = AsyncMock()
    mock_agent_loop = MagicMock()
    mock_agent_loop.storage = storage

    text_event = TextChunk(content="Found relevant data")
    tool_event = ToolCallResult(name="web_fetch", tool_call_id="1", result="page content here")
    complete_event = RunComplete(full_content="done", usage={"total_tokens": 50})

    mock_agent_loop.run = MagicMock(return_value=_aiter([text_event, tool_event, complete_event]))

    loop = ResearchLoop(llm=mock_llm, ledger=ResearchLedger(db_path=storage.db_path), agent_loop=mock_agent_loop)
    approach, output = await loop._execute_via_agent("research hypothesis about X", "agent:main")

    assert approach == "AgentLoop sub-session with tools"
    assert "web_fetch" in output
    assert "Found relevant data" in output


@pytest.mark.asyncio
async def test_execute_dispatches_to_correct_method(storage):
    """_execute() routes to _execute_via_agent when agent_loop present, else _execute_via_llm."""
    mock_llm = AsyncMock()

    # Without agent_loop
    loop_no_agent = ResearchLoop(llm=mock_llm, ledger=ResearchLedger(db_path=storage.db_path))
    loop_no_agent._execute_via_llm = AsyncMock(return_value=("direct-llm", "output"))
    loop_no_agent._execute_via_agent = AsyncMock(return_value=("agent", "output"))

    await loop_no_agent._execute("hyp", "agent:main")
    loop_no_agent._execute_via_llm.assert_called_once()
    loop_no_agent._execute_via_agent.assert_not_called()

    # With agent_loop
    mock_agent_loop = MagicMock()
    mock_agent_loop.storage = storage
    loop_with_agent = ResearchLoop(llm=mock_llm, ledger=ResearchLedger(db_path=storage.db_path), agent_loop=mock_agent_loop)
    loop_with_agent._execute_via_llm = AsyncMock(return_value=("direct-llm", "output"))
    loop_with_agent._execute_via_agent = AsyncMock(return_value=("agent", "output"))

    await loop_with_agent._execute("hyp", "agent:main")
    loop_with_agent._execute_via_agent.assert_called_once()
    loop_with_agent._execute_via_llm.assert_not_called()
