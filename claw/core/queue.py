import asyncio
from dataclasses import dataclass
from typing import Callable, Awaitable, Any
from enum import Enum


class QueueMode(str, Enum):
    COLLECT   = "collect"   # 等目前 run 結束，把累積的訊息一起處理
    FOLLOWUP  = "followup"  # 等目前 run 結束，立即啟動下一個 run
    DROP      = "drop"      # 丟棄（busy 時不接受新訊息）


@dataclass
class QueuedMessage:
    session_id: str
    user_message: str
    # 未來可加：附件、metadata


class SessionLane:
    """單一 session 的訊息 lane"""

    def __init__(self, session_id: str, mode: QueueMode = QueueMode.COLLECT):
        self.session_id = session_id
        self.mode = mode
        self._queue: asyncio.Queue[QueuedMessage] = asyncio.Queue()
        self._running = False

    @property
    def is_busy(self) -> bool:
        return self._running

    async def enqueue(self, msg: QueuedMessage) -> bool:
        """
        回傳 True = 成功入隊，False = 被 drop
        """
        if self._running:
            if self.mode == QueueMode.DROP:
                return False
            # COLLECT / FOLLOWUP：都放入 queue，等待處理
        await self._queue.put(msg)
        return True

    async def run_loop(
        self,
        handler: Callable[[str, str], Awaitable[Any]]
    ) -> None:
        """
        持續從 queue 取訊息執行 handler（agent loop）。
        handler signature: async def handler(session_id, user_message)
        """
        while True:
            msg = await self._queue.get()
            self._running = True
            try:
                await handler(msg.session_id, msg.user_message)
            finally:
                self._running = False
                self._queue.task_done()


class MessageQueue:
    """全域 queue，管理所有 session lanes"""

    def __init__(self):
        self._lanes: dict[str, SessionLane] = {}
        self._tasks: dict[str, asyncio.Task] = {}

    def get_or_create_lane(
        self, session_id: str, mode: QueueMode = QueueMode.COLLECT
    ) -> SessionLane:
        if session_id not in self._lanes:
            self._lanes[session_id] = SessionLane(session_id, mode)
        return self._lanes[session_id]

    async def submit(
        self,
        session_id: str,
        user_message: str,
        handler: Callable[[str, str], Awaitable[Any]],
        mode: QueueMode = QueueMode.COLLECT,
    ) -> bool:
        """
        提交一則訊息到 session lane。
        如果 lane 的 run_loop 還沒啟動，自動啟動。
        回傳 True = 成功入隊
        """
        lane = self.get_or_create_lane(session_id, mode)
        queued = await lane.enqueue(QueuedMessage(session_id, user_message))
        if not queued:
            return False
        # 確保 run_loop task 存在
        if session_id not in self._tasks or self._tasks[session_id].done():
            self._tasks[session_id] = asyncio.create_task(
                lane.run_loop(handler)
            )
        return True

    def remove_lane(self, session_id: str) -> None:
        if session_id in self._tasks:
            self._tasks[session_id].cancel()
            del self._tasks[session_id]
        self._lanes.pop(session_id, None)
