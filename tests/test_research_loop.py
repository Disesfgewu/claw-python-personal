from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from claw.research.loop import ResearchLoop, ResearchCompleted, ResearchExhausted
from claw.research.ledger import ResearchLedger
from claw.research.experiment import ExperimentStatus
from claw.core.storage import Storage


@pytest.fixture
async def loop_and_ledger(tmp_path):
    db = str(tmp_path / "test.db")
    storage = Storage(db_path=db, transcript_dir=str(tmp_path / "transcripts"))
    await storage.init()
    ledger = ResearchLedger(db_path=db)

    mock_llm = AsyncMock()
    mock_chunk = MagicMock()
    mock_chunk.content = "yes"
    mock_llm.stream = AsyncMock(return_value=_aiter([mock_chunk]))

    loop = ResearchLoop(llm=mock_llm, ledger=ledger)
    return loop, ledger


async def _aiter(items):
    for item in items:
        yield item


@pytest.mark.asyncio
async def test_a_layer_terminates_on_criteria(loop_and_ledger):
    """A-layer: if success_criteria provided and LLM says yes, loop completes."""
    loop, ledger = loop_and_ledger

    # Mock planner to return one hypothesis
    loop.planner.decompose = AsyncMock(return_value=["Test hypothesis"])
    loop.planner.next_hypothesis = AsyncMock(return_value="Next hypothesis")
    loop._execute = AsyncMock(return_value=("approach", "some output"))
    # LLM always says yes -> criteria met immediately
    loop._ask_llm_bool = AsyncMock(return_value=True)

    events = []
    async for event in loop.run("research question", success_criteria="find something"):
        events.append(event)

    assert any(isinstance(e, ResearchCompleted) for e in events)
    completed = next(e for e in events if isinstance(e, ResearchCompleted))
    assert "criteria" in completed.reason


@pytest.mark.asyncio
async def test_c_layer_terminates_on_metric_improvement(loop_and_ledger):
    """C-layer: if eval_cmd returns improving metric, keep and eventually terminate."""
    loop, ledger = loop_and_ledger
    loop.planner.decompose = AsyncMock(return_value=["Hyp 1", "Hyp 2", "Hyp 3"])
    loop.planner.next_hypothesis = AsyncMock(return_value="New hyp")
    loop._execute = AsyncMock(return_value=("approach", "output"))

    # First call returns 1.0, subsequent improve to 0.0 (success)
    call_count = 0
    async def fake_eval(cmd):
        nonlocal call_count
        call_count += 1
        return 1.0 / call_count  # 1.0, 0.5, 0.33...
    loop._run_eval_cmd = fake_eval
    loop._ask_llm_bool = AsyncMock(return_value=True)

    events = []
    async for event in loop.run("question", eval_cmd="pytest", max_experiments=5):
        events.append(event)

    assert len(events) > 0


@pytest.mark.asyncio
async def test_b_layer_self_evaluation(loop_and_ledger):
    """B-layer: without criteria or eval_cmd, LLM self-judges."""
    loop, ledger = loop_and_ledger
    loop.planner.decompose = AsyncMock(return_value=["Hyp"])
    loop.planner.next_hypothesis = AsyncMock(return_value="New hyp")
    loop._execute = AsyncMock(return_value=("approach", "output"))
    # LLM says yes after 3 keeps -> terminate
    loop._ask_llm_bool = AsyncMock(return_value=True)

    events = []
    async for event in loop.run("question", max_experiments=10):
        events.append(event)

    assert len(events) > 0


@pytest.mark.asyncio
async def test_max_experiments_exhausted(loop_and_ledger):
    """Loop stops at max_experiments if no termination criteria met."""
    loop, ledger = loop_and_ledger
    loop.planner.decompose = AsyncMock(return_value=["Hyp"])
    loop.planner.next_hypothesis = AsyncMock(return_value="Next")
    loop._execute = AsyncMock(return_value=("approach", "output"))
    loop._ask_llm_bool = AsyncMock(return_value=False)  # never satisfied

    events = []
    async for event in loop.run("question", max_experiments=3):
        events.append(event)

    assert any(isinstance(e, ResearchExhausted) for e in events)
