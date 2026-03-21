from __future__ import annotations

import uuid
import aiosqlite
from datetime import datetime, timezone
from pathlib import Path

from claw.core.storage import DB_PATH
from claw.research.experiment import ExperimentResult, ExperimentStatus, ResearchTask


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ResearchLedger:
    """SQLite-backed experiment ledger for AutoResearch tasks."""

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = str(Path(db_path).expanduser())

    async def create_task(
        self,
        question: str,
        criteria: str | None = None,
        eval_cmd: str | None = None,
        max_experiments: int = 20,
    ) -> str:
        task_id = uuid.uuid4().hex[:12]
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT INTO research_tasks(task_id, question, criteria, eval_cmd,
                   status, max_exp, created_at)
                   VALUES (?, ?, ?, ?, 'running', ?, ?)""",
                (task_id, question, criteria, eval_cmd, max_experiments, _now()),
            )
            await db.commit()
        return task_id

    async def record_experiment(self, result: ExperimentResult) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT INTO research_experiments
                   (task_id, hypothesis, approach, output, metric, status, reasoning, ts)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    result.task_id,
                    result.hypothesis,
                    result.approach,
                    result.output[:1000],
                    result.metric,
                    result.status.value,
                    result.reasoning,
                    result.ts,
                ),
            )
            await db.commit()

    async def complete_task(self, task_id: str, status: str = "completed") -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE research_tasks SET status=?, completed_at=? WHERE task_id=?",
                (status, _now(), task_id),
            )
            await db.commit()

    async def get_task(self, task_id: str) -> ResearchTask | None:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT * FROM research_tasks WHERE task_id=?", (task_id,)
            )
            row = await cur.fetchone()
            if not row:
                return None
            task = ResearchTask(
                task_id=row["task_id"],
                question=row["question"],
                criteria=row["criteria"],
                eval_cmd=row["eval_cmd"],
                status=row["status"],
                max_experiments=row["max_exp"],
                created_at=row["created_at"],
                completed_at=row["completed_at"],
            )
            cur2 = await db.execute(
                "SELECT * FROM research_experiments WHERE task_id=? ORDER BY ts ASC",
                (task_id,),
            )
            rows = await cur2.fetchall()
            task.experiments = [
                ExperimentResult(
                    task_id=r["task_id"],
                    hypothesis=r["hypothesis"],
                    approach=r["approach"],
                    output=r["output"],
                    metric=r["metric"],
                    status=ExperimentStatus(r["status"]),
                    reasoning=r["reasoning"],
                    ts=r["ts"],
                )
                for r in rows
            ]
            return task

    async def list_running_tasks(self) -> list[ResearchTask]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT * FROM research_tasks WHERE status='running' ORDER BY created_at DESC"
            )
            rows = await cur.fetchall()
            return [
                ResearchTask(
                    task_id=r["task_id"],
                    question=r["question"],
                    criteria=r["criteria"],
                    eval_cmd=r["eval_cmd"],
                    status=r["status"],
                    max_experiments=r["max_exp"],
                    created_at=r["created_at"],
                    completed_at=r["completed_at"],
                )
                for r in rows
            ]

    async def kept_experiments(self, task_id: str) -> list[ExperimentResult]:
        """Return only KEEP status experiments for a task."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT * FROM research_experiments WHERE task_id=? AND status='keep' ORDER BY ts ASC",
                (task_id,),
            )
            rows = await cur.fetchall()
            return [
                ExperimentResult(
                    task_id=r["task_id"],
                    hypothesis=r["hypothesis"],
                    approach=r["approach"],
                    output=r["output"],
                    metric=r["metric"],
                    status=ExperimentStatus(r["status"]),
                    reasoning=r["reasoning"],
                    ts=r["ts"],
                )
                for r in rows
            ]
