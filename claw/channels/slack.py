from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from slack_bolt.async_app import AsyncApp
    from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler

logger = logging.getLogger(__name__)


class SlackChannel:
    def __init__(
        self,
        bot_token: str,
        app_token: str,
        base_url: str = "http://localhost:8000",
    ):
        self.bot_token = bot_token
        self.app_token = app_token
        self.base_url = base_url.rstrip("/")
        self.app: "AsyncApp | None" = None
        self._socket_handler: "AsyncSocketModeHandler | None" = None

    async def start(self) -> None:
        try:
            from slack_bolt.async_app import AsyncApp
            from slack_bolt.adapter.socket_mode import AsyncSocketModeHandler
        except Exception as e:
            raise ImportError("slack-bolt not installed") from e

        self.app = AsyncApp(token=self.bot_token)

        @self.app.event("app_mention")
        async def _handle_mention(event, say):
            await self._on_app_mention(event)

        @self.app.event("message")
        async def _handle_message(event, say):
            if event.get("channel", "").startswith("D"):
                await self._on_direct_message(event)

        self._socket_handler = AsyncSocketModeHandler(self.app, self.app_token)
        if hasattr(self._socket_handler, "start_async"):
            await self._socket_handler.start_async()
        else:
            await self._socket_handler.start()
        logger.info("SlackChannel started")

    async def stop(self) -> None:
        if not self._socket_handler:
            return
        if hasattr(self._socket_handler, "close_async"):
            await self._socket_handler.close_async()
        else:
            await self._socket_handler.close()

    async def _on_app_mention(self, event: dict) -> None:
        channel = event.get("channel")
        text = event.get("text", "")
        thread_ts = event.get("thread_ts")
        if not channel or not text:
            return

        session_id = self._get_session_id(event)
        try:
            response_text = await self._call_gateway(session_id, text)
            if response_text:
                await self._send_response(channel, response_text, thread_ts=thread_ts)
        except Exception as e:
            logger.error(f"Slack gateway error: {e}")
            await self._send_response(channel, f"Error: {e}", thread_ts=thread_ts)

    async def _on_direct_message(self, event: dict) -> None:
        channel = event.get("channel")
        text = event.get("text", "")
        if not channel or not text:
            return

        session_id = self._get_session_id(event)
        try:
            response_text = await self._call_gateway(session_id, text)
            if response_text:
                await self._send_response(channel, response_text, thread_ts=event.get("thread_ts"))
        except Exception as e:
            logger.error(f"Slack gateway error: {e}")
            await self._send_response(channel, f"Error: {e}", thread_ts=event.get("thread_ts"))

    def _get_session_id(self, event: dict) -> str:
        channel = event["channel"]
        user = event["user"]
        if channel.startswith("D"):
            return f"agent:slack:dm:{user}"
        return f"agent:slack:channel:{channel}"

    async def _call_gateway(self, session_id: str, text: str) -> str:
        url = f"{self.base_url}/v1/chat/completions"
        payload = {
            "session_id": session_id,
            "messages": [{"role": "user", "content": text}],
            "stream": True,
        }
        chunks: list[str] = []
        async with httpx.AsyncClient() as client:
            async with client.stream("POST", url, json=payload, timeout=30.0) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if not data or data == "[DONE]":
                        continue
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    delta = chunk.get("choices", [{}])[0].get("delta", {})
                    piece = delta.get("content")
                    if piece:
                        chunks.append(piece)
        return "".join(chunks)

    async def _send_response(self, channel: str, text: str, thread_ts: str | None = None) -> None:
        if not text:
            return
        try:
            await self._client_send_message(channel, text, thread_ts=thread_ts)
        except Exception as e:
            logger.error(f"Slack send error: {e}")

    async def _client_send_message(
        self,
        channel: str,
        text: str,
        thread_ts: str | None = None,
    ) -> None:
        if not self.app:
            raise RuntimeError("Slack app not started")
        await self.app.client.chat_postMessage(
            channel=channel,
            text=text,
            thread_ts=thread_ts,
        )
