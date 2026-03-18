from __future__ import annotations
import asyncio
import logging
import uuid
from claw.core.storage import Storage, SessionRow, now_iso
from claw.llm.router_client import LLMRouterClient
from claw.agent.loop import AgentLoop
from claw.agent.events import TextChunk

logger = logging.getLogger(__name__)


class MultiAgentCoordinator:
    def __init__(self, storage: Storage, llm: LLMRouterClient):
        self.storage = storage
        self.llm = llm

    async def send(self, target_session_id: str, message: str) -> str:
        """Synchronously wait for AgentLoop.run(), concatenate TextChunks."""
        loop = AgentLoop(storage=self.storage, llm=self.llm)
        buf = ""
        async for event in loop.run(target_session_id, message):
            if isinstance(event, TextChunk):
                buf += event.content
        return buf

    async def spawn(self, goal: str, agent_id: str = "default", parent_session_id: str = "agent:main") -> str:
        """Create child session and run asynchronously via asyncio.Task, return child_session_id immediately."""
        child_id = f"agent:child:{uuid.uuid4().hex[:8]}"
        session = SessionRow(
            session_id=child_id,
            scope="child",
            channel=None,
            agent_id=agent_id,
            system_prompt=None,
            queue_mode="collect",
            sandbox=False,
            created_at=now_iso(),
            last_active=now_iso(),
            config={"parent": parent_session_id},
        )
        await self.storage.create_session(session)

        async def _run():
            try:
                loop = AgentLoop(storage=self.storage, llm=self.llm)
                async for _ in loop.run(child_id, goal):
                    pass
            except Exception as e:
                logger.error(f"child agent {child_id} error: {e}")

        asyncio.create_task(_run())
        return child_id

    async def list_sessions(self) -> list[SessionRow]:
        return await self.storage.list_sessions()
