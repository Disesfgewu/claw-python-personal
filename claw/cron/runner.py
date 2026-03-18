from __future__ import annotations
import logging
from claw.cron.store import CronJob, CronStore
from claw.core.storage import Storage, SessionRow, now_iso
from claw.llm.router_client import LLMRouterClient
from claw.agent.loop import AgentLoop
from claw.agent.events import TextChunk

logger = logging.getLogger(__name__)


async def run_cron_job(
    job: CronJob,
    store: CronStore,
    storage: Storage,
    llm: LLMRouterClient,
) -> None:
    """Execute a cron job in an isolated cron session."""
    from claw.cron.schedule import next_run_dt

    session = await storage.get_session(job.session_id)
    if session is None:
        session = SessionRow(
            session_id=job.session_id,
            scope="cron",
            channel=None,
            agent_id="default",
            system_prompt=None,
            queue_mode="collect",
            sandbox=False,
            created_at=now_iso(),
            last_active=now_iso(),
            config={},
        )
        await storage.create_session(session)

    loop = AgentLoop(storage=storage, llm=llm)
    full = ""
    try:
        async for event in loop.run(job.session_id, job.prompt):
            if isinstance(event, TextChunk):
                full += event.content
    except Exception as e:
        logger.error(f"cron job {job.id} failed: {e}")

    ts = now_iso()
    next_r = next_run_dt(job.schedule).isoformat()
    await store.update_last_run(job.id, ts, next_r)
    logger.info(f"cron job {job.id} done, next={next_r}")
