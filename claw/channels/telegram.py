from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING, Any

import httpx

logger = logging.getLogger(__name__)


class TelegramChannel:
    def __init__(
        self,
        token: str,
        base_url: str = "http://localhost:8000",
        polling: bool = True,
    ):
        self.token = token
        self.base_url = base_url.rstrip("/")
        self.polling = polling
        self.app = None

    async def start(self) -> None:
        try:
            from telegram.ext import Application, MessageHandler, filters  # type: ignore
        except Exception as e:
            raise ImportError("python-telegram-bot not installed") from e

        self.app = Application.builder().token(self.token).build()
        self.app.add_handler(
            MessageHandler(
                filters.TEXT | filters.PHOTO | filters.Document.ALL,
                self.on_message,
            )
        )
        await self.app.initialize()
        await self.app.start()
        if self.polling:
            updater = self.app.updater
            if updater is not None:
                await updater.start_polling()
                logger.info("TelegramChannel polling started successfully")
            else:
                logger.warning("No updater available, polling mode disabled")
        else:
            logger.info("TelegramChannel started in webhook mode (not implemented)")

    async def stop(self) -> None:
        if not self.app:
            return
        if self.polling and self.app.updater:
            await self.app.updater.stop()
        await self.app.stop()
        await self.app.shutdown()

    async def on_message(self, update: Any, context: Any) -> None:
        if not update or not update.message:
            return
        text = update.message.text
        if not text:
            return

        chat_id = update.message.chat.id
        session_id = self._get_session_id(update)
        try:
            response_text = await self._call_gateway(session_id, text)
            if response_text:
                await self._send_response(chat_id, response_text)
        except asyncio.TimeoutError:
            logger.error(f"Gateway timeout for session {session_id}")
            await self._send_response(chat_id, "Error: Request timeout, please try again")
        except httpx.HTTPStatusError as e:
            logger.error(f"Gateway HTTP error: {e.response.status_code} - {e.response.text}")
            await self._send_response(chat_id, f"Error: Gateway returned {e.response.status_code}")
        except Exception as e:
            logger.error(f"Unexpected error in telegram handler", exc_info=True)
            await self._send_response(chat_id, "Error: Internal server error")

    def _get_session_id(self, update: Any) -> str:
        if update.message.chat.type == "private":
            return f"agent:tg:user:{update.message.from_user.id}"
        return f"agent:tg:group:{update.message.chat.id}"

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

    async def _send_response(self, chat_id: int, text: str) -> None:
        if not text:
            return
        for i in range(0, len(text), 4096):
            await asyncio.sleep(0.5)
            chunk = text[i:i + 4096]
            try:
                await self._bot_send_message(chat_id, chunk)
            except Exception as e:
                logger.error(f"Telegram send error: {e}")

    async def _bot_send_message(self, chat_id: int, text: str) -> None:
        if not self.app:
            raise RuntimeError("Telegram application not started")
        await self.app.bot.send_message(chat_id, text)
