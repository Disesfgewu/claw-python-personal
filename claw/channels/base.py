from __future__ import annotations
from abc import ABC, abstractmethod
from typing import AsyncIterator


class BaseChannel(ABC):
    @abstractmethod
    async def start(self) -> None: ...

    @abstractmethod
    async def stop(self) -> None: ...

    @abstractmethod
    async def send(self, session_id: str, text: str) -> None: ...

    async def send_stream(self, session_id: str, chunks: AsyncIterator[str]) -> None:
        buf = ""
        async for chunk in chunks:
            buf += chunk
        await self.send(session_id, buf)

    async def send_typing(self, session_id: str) -> None:
        pass

    async def send_ack(self, session_id: str, emoji: str = "✅") -> None:
        pass
