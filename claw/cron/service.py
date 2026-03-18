from __future__ import annotations
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from claw.cron.store import CronStore, CronJob
from claw.cron.runner import run_cron_job
from claw.core.storage import Storage
from claw.llm.router_client import LLMRouterClient

logger = logging.getLogger(__name__)


class CronService:
    def __init__(self, store: CronStore, storage: Storage, llm: LLMRouterClient):
        self.store = store
        self.storage = storage
        self.llm = llm
        self._scheduler = AsyncIOScheduler(timezone="UTC")

    async def start(self) -> None:
        jobs = await self.store.list()
        for job in jobs:
            self._add_to_scheduler(job)
        self._scheduler.start()
        logger.info(f"CronService started with {len(jobs)} jobs")

    async def stop(self) -> None:
        self._scheduler.shutdown(wait=False)

    def _add_to_scheduler(self, job: CronJob) -> None:
        self._scheduler.add_job(
            run_cron_job,
            trigger="cron",
            args=[job, self.store, self.storage, self.llm],
            id=job.id,
            **self._parse_cron(job.schedule),
            replace_existing=True,
        )

    @staticmethod
    def _parse_cron(expr: str) -> dict:
        parts = expr.split()
        keys = ["minute", "hour", "day", "month", "day_of_week"]
        return dict(zip(keys, parts))

    async def add_job(self, session_id: str, schedule: str, prompt: str) -> CronJob:
        job = await self.store.add(session_id, schedule, prompt)
        self._add_to_scheduler(job)
        return job

    async def remove_job(self, job_id: str) -> None:
        await self.store.delete(job_id)
        try:
            self._scheduler.remove_job(job_id)
        except Exception:
            pass

    async def list_jobs(self) -> list[CronJob]:
        return await self.store.list()
