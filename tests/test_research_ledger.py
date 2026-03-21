from __future__ import annotations

import pytest
import os
import tempfile
from claw.research.ledger import ResearchLedger
from claw.research.experiment import ExperimentResult, ExperimentStatus
from claw.core.storage import Storage
from datetime import datetime, timezone


@pytest.fixture
async def ledger(tmp_path):
    db = str(tmp_path / "test.db")
    storage = Storage(db_path=db, transcript_dir=str(tmp_path / "transcripts"))
    await storage.init()
    return ResearchLedger(db_path=db)


@pytest.mark.asyncio
async def test_create_task(ledger):
    task_id = await ledger.create_task("What is the best sorting algorithm?")
    assert len(task_id) == 12
    task = await ledger.get_task(task_id)
    assert task is not None
    assert task.question == "What is the best sorting algorithm?"
    assert task.status == "running"


@pytest.mark.asyncio
async def test_record_experiment(ledger):
    task_id = await ledger.create_task("Test question")
    result = ExperimentResult(
        task_id=task_id,
        hypothesis="Try approach A",
        approach="Used web_fetch",
        output="Found that A works well",
        metric=None,
        status=ExperimentStatus.KEEP,
        reasoning="Clear improvement",
        ts=datetime.now(timezone.utc).isoformat(),
    )
    await ledger.record_experiment(result)
    task = await ledger.get_task(task_id)
    assert task is not None
    assert len(task.experiments) == 1
    assert task.experiments[0].status == ExperimentStatus.KEEP


@pytest.mark.asyncio
async def test_kept_experiments(ledger):
    task_id = await ledger.create_task("Test question")
    ts = datetime.now(timezone.utc).isoformat()
    for status, hyp in [
        (ExperimentStatus.KEEP, "good hypothesis"),
        (ExperimentStatus.DISCARD, "bad hypothesis"),
        (ExperimentStatus.KEEP, "another good one"),
    ]:
        await ledger.record_experiment(ExperimentResult(
            task_id=task_id, hypothesis=hyp, approach="approach",
            output="output", metric=None, status=status, reasoning="r", ts=ts,
        ))
    kept = await ledger.kept_experiments(task_id)
    assert len(kept) == 2
    assert all(e.status == ExperimentStatus.KEEP for e in kept)


@pytest.mark.asyncio
async def test_complete_task(ledger):
    task_id = await ledger.create_task("Complete me")
    await ledger.complete_task(task_id, "completed")
    task = await ledger.get_task(task_id)
    assert task is not None
    assert task.status == "completed"
    assert task.completed_at is not None
