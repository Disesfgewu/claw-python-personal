from __future__ import annotations

import json
import logging
import asyncio
from typing import TYPE_CHECKING, Any, cast

import httpx

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
        self.app: Any = None
        self._socket_handler: Any = None

    async def start(self) -> None:
        try:
            from slack_bolt.async_app import AsyncApp  # type: ignore
            from slack_bolt.adapter.socket_mode import AsyncSocketModeHandler  # type: ignore
        except Exception as e:
            raise ImportError("slack-bolt not installed") from e

        self.app = AsyncApp(token=self.bot_token)
        app_any = cast(Any, self.app)

        @app_any.event("app_mention")
        async def _handle_mention(event, say):
            await self._on_app_mention(event)

        @app_any.event("message")
        async def _handle_message(event, say):
            if event.get("channel", "").startswith("D"):
                await self._on_direct_message(event)

        self._socket_handler = AsyncSocketModeHandler(self.app, self.app_token)
        try:
            await self._socket_handler.start_async()
            logger.info("SlackChannel started with start_async() (new API)")
        except AttributeError:
            logger.info("Using legacy SlackChannel.start() method (old API)")
            await self._socket_handler.start()

    async def stop(self) -> None:
        if not self._socket_handler:
            return
        if hasattr(self._socket_handler, "close_async"):
            await self._socket_handler.close_async()
        else:
            await self._socket_handler.close()

    async def _on_app_mention(self, event: dict[str, Any]) -> None:
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
        except asyncio.TimeoutError:
            logger.error(f"Gateway timeout for session {session_id}")
            await self._send_response(channel, "Error: Request timeout", thread_ts=thread_ts)
        except httpx.HTTPStatusError as e:
            logger.error(f"Gateway HTTP error: {e.response.status_code}")
            await self._send_response(channel, f"Error: Gateway returned {e.response.status_code}", thread_ts=thread_ts)
        except Exception as e:
            logger.error(f"Unexpected error in slack handler", exc_info=True)
            await self._send_response(channel, "Error: Internal server error", thread_ts=thread_ts)

    async def _on_direct_message(self, event: dict[str, Any]) -> None:
        channel = event.get("channel")
        text = event.get("text", "")
        if not channel or not text:
            return

        session_id = self._get_session_id(event)
        try:
            response_text = await self._call_gateway(session_id, text)
            if response_text:
                await self._send_response(channel, response_text, thread_ts=event.get("thread_ts"))
        except asyncio.TimeoutError:
            logger.error(f"Gateway timeout for session {session_id}")
            await self._send_response(channel, "Error: Request timeout", thread_ts=event.get("thread_ts"))
        except httpx.HTTPStatusError as e:
            logger.error(f"Gateway HTTP error: {e.response.status_code}")
            await self._send_response(channel, f"Error: Gateway returned {e.response.status_code}", thread_ts=event.get("thread_ts"))
        except Exception as e:
            logger.error(f"Unexpected error in slack handler", exc_info=True)
            await self._send_response(channel, "Error: Internal server error", thread_ts=event.get("thread_ts"))

    def _get_session_id(self, event: dict[str, Any]) -> str:
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
            "stream": False,
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=payload, timeout=30.0)
            resp.raise_for_status()
            result = resp.json()
            content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
            if isinstance(content, list):
                parts = []
                for part in content:
                    if isinstance(part, dict):
                        text_part = part.get("text")
                        if isinstance(text_part, str):
                            parts.append(text_part)
                    elif isinstance(part, str):
                        parts.append(part)
                content = "".join(parts)
            return (content or "").strip()

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
