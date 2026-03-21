from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta

from claw.core.logger import get_logger

logger = get_logger(__name__)


class SessionReaper:
    """
    Background task: periodically delete expired sessions.
    TTL and interval are configurable.
    """

    def __init__(
        self,
        storage,            # claw.core.storage.Storage
        ttl_hours: int = 24,
        interval_seconds: int = 60,
        docker_runner=None, # optional: claw.sandbox.docker_runner.DockerRunner
    ):
        self.storage = storage
        self.ttl_hours = ttl_hours
        self.interval_seconds = interval_seconds
        self.docker_runner = docker_runner
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        """Start background reaper task."""
        self._task = asyncio.create_task(self._run())
        logger.info("session_reaper.started", ttl_hours=self.ttl_hours)

    def stop(self) -> None:
        """Cancel background task on shutdown."""
        if self._task:
            self._task.cancel()

    async def _run(self) -> None:
        while True:
            try:
                await self._reap()
            except Exception as e:
                logger.warning("session_reaper.error", error=str(e))
            await asyncio.sleep(self.interval_seconds)

    async def _reap(self) -> None:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=self.ttl_hours)
        sessions = await self.storage.list_sessions()
        removed = 0
        for session in sessions:
            # Parse last_active (ISO format)
            try:
                last_active_str = getattr(session, "last_active", None)
                if last_active_str is None:
                    continue
                last_active = datetime.fromisoformat(
                    last_active_str.replace("Z", "+00:00")
                )
                if last_active < cutoff:
                    # Clean up sandbox container first
                    if self.docker_runner:
                        await self.docker_runner.destroy(session.session_id)
                    await self.storage.delete_session(session.session_id)
                    removed += 1
            except Exception as e:
                logger.warning(
                    "session_reaper.skip",
                    session_id=getattr(session, "session_id", "?"),
                    error=str(e),
                )
        if removed:
            logger.info("session_reaper.reaped", count=removed)
