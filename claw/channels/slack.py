from __future__ import annotations
import logging

try:
    from slack_bolt.async_app import AsyncApp
    _SLACK_AVAILABLE = True
except ImportError:
    _SLACK_AVAILABLE = False
    AsyncApp = None  # type: ignore

from claw.channels.base import BaseChannel
from claw.core.queue import MessageQueue

logger = logging.getLogger(__name__)


class SlackChannel(BaseChannel):
    def __init__(self, bot_token: str, signing_secret: str, queue: MessageQueue | None):
        if not _SLACK_AVAILABLE:
            raise ImportError(
                "slack-bolt not installed. Run: pip install 'claw-python[channels]'"
            )
        self.app = AsyncApp(token=bot_token, signing_secret=signing_secret)
        self.queue = queue
        self._session_to_channel: dict[str, str] = {}
        self._register_handlers()

    def _register_handlers(self) -> None:
        @self.app.event("app_mention")
        async def on_mention(event, say):
            text = event["text"]
            channel = event["channel"]
            session_id = f"agent:slack:ch:{channel}"
            self._session_to_channel[session_id] = channel
            if self.queue:
                await self.queue.submit(session_id, text)

        @self.app.event("message")
        async def on_dm(event, say):
            if event.get("channel_type") == "im":
                session_id = "agent:main"
                channel = event["channel"]
                self._session_to_channel[session_id] = channel
                if self.queue:
                    await self.queue.submit(session_id, event.get("text", ""))

    async def start(self) -> None:
        await self.app.start(port=3000)
        logger.info("SlackChannel started on port 3000")

    async def stop(self) -> None:
        try:
            await self.app.stop()
        except Exception:
            pass

    async def send(self, session_id: str, text: str) -> None:
        channel_id = self._session_to_channel.get(session_id)
        if channel_id:
            try:
                await self.app.client.chat_postMessage(channel=channel_id, text=text)
            except Exception as e:
                logger.error(f"Slack send error: {e}")
