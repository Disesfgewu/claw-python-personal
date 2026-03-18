from __future__ import annotations
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
import aiosqlite
from claw.core.storage import now_iso


@dataclass
class CronJob:
    id: str
    session_id: str
    schedule: str       # cron expression "min hour day month dow"
    prompt: str
    enabled: bool = True
    created_at: str = field(default_factory=now_iso)
    last_run: str | None = None
    next_run: str | None = None


class CronStore:
    def __init__(self, db_path: str):
        self.db_path = db_path

    async def init(self) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS cron_jobs (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    schedule TEXT NOT NULL,
                    prompt TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    last_run TEXT,
                    next_run TEXT
                )
            """)
            await db.commit()

    async def add(self, session_id: str, schedule: str, prompt: str) -> CronJob:
        job = CronJob(
            id=str(uuid.uuid4()),
            session_id=session_id,
            schedule=schedule,
            prompt=prompt,
        )
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO cron_jobs VALUES (?,?,?,?,?,?,?,?)",
                (job.id, job.session_id, job.schedule, job.prompt,
                 1, job.created_at, job.last_run, job.next_run)
            )
            await db.commit()
        return job

    async def list(self) -> list[CronJob]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM cron_jobs WHERE enabled=1") as cur:
                rows = await cur.fetchall()
        return [CronJob(**dict(r)) for r in rows]

    async def delete(self, job_id: str) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM cron_jobs WHERE id=?", (job_id,))
            await db.commit()

    async def update_last_run(self, job_id: str, ts: str, next_run: str) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE cron_jobs SET last_run=?, next_run=? WHERE id=?",
                (ts, next_run, job_id)
            )
            await db.commit()
