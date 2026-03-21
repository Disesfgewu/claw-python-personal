from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch
from claw.core.storage import Storage


@pytest.fixture
async def storage_init(tmp_path):
    db = str(tmp_path / "test.db")
    storage = Storage(db_path=db, transcript_dir=str(tmp_path / "transcripts"))
    await storage.init()
    return db


@pytest.mark.asyncio
async def test_experiment_record_tool(storage_init):
    from claw.tools.research_tools import experiment_record
    with patch("claw.core.storage.DB_PATH", storage_init):
        # Patch the import inside the function
        import claw.research.ledger as ledger_mod
        orig = ledger_mod.ResearchLedger.__init__
        def patched_init(self, db_path=None):
            orig(self, db_path=storage_init)
        with patch.object(ledger_mod.ResearchLedger, "__init__", patched_init):
            # First create a task directly
            ledger = ledger_mod.ResearchLedger(db_path=storage_init)
            task_id = await ledger.create_task("test question")
            result = await experiment_record(
                task_id=task_id,
                hypothesis="test hyp",
                approach="test approach",
                output="test output",
                status="keep",
                reasoning="good result",
            )
    assert "✅" in result or "recorded" in result.lower()


@pytest.mark.asyncio
async def test_research_status_no_tasks(storage_init):
    from claw.tools.research_tools import research_status
    import claw.research.ledger as ledger_mod
    orig = ledger_mod.ResearchLedger.__init__
    def patched_init(self, db_path=None):
        orig(self, db_path=storage_init)
    with patch.object(ledger_mod.ResearchLedger, "__init__", patched_init):
        with patch("claw.core.storage.DB_PATH", storage_init):
            result = await research_status()
    assert "No running" in result or "task" in result.lower()
