from __future__ import annotations
import logging
import time
from typing import AsyncIterator

try:
    from telegram import Update
    from telegram.ext import Application, MessageHandler, filters, ContextTypes
    _TELEGRAM_AVAILABLE = True
except ImportError:
    _TELEGRAM_AVAILABLE = False

from claw.channels.base import BaseChannel
from claw.core.queue import MessageQueue
from claw.media.store import MediaStore

logger = logging.getLogger(__name__)


class TelegramChannel(BaseChannel):
    def __init__(
        self,
        token: str,
        queue: MessageQueue | None,
        media_store: MediaStore | None,
        llm_router_url: str,
        api_key: str = "",
    ):
        self.token = token
        self.queue = queue
        self.media_store = media_store
        self.llm_router_url = llm_router_url
        self.api_key = api_key
        self.app = None
        self._session_to_chat: dict[str, int] = {}  # session_id → chat_id

    async def start(self) -> None:
        if not _TELEGRAM_AVAILABLE:
            raise ImportError("python-telegram-bot not installed. Run: pip install 'claw-python[channels]'")

        self.app = Application.builder().token(self.token).build()
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._on_message))
        self.app.add_handler(MessageHandler(filters.PHOTO | filters.Document.ALL, self._on_media))
        await self.app.initialize()
        await self.app.start()
        await self.app.updater.start_polling()
        logger.info("TelegramChannel started")

    async def stop(self) -> None:
        if self.app:
            await self.app.updater.stop()
            await self.app.stop()
            await self.app.shutdown()

    async def send(self, session_id: str, text: str) -> None:
        chat_id = self._session_to_chat.get(session_id)
        if chat_id is None:
            logger.warning(f"No chat_id for session {session_id}")
            return
        try:
            await self.app.bot.send_message(chat_id, text[:4000], parse_mode="Markdown")
        except Exception as e:
            logger.error(f"Telegram send error: {e}")

    async def send_stream(self, session_id: str, chunks: AsyncIterator[str]) -> None:
        """Draft mode: send first chunk, then edit on throttled intervals."""
        chat_id = self._session_to_chat.get(session_id)
        if chat_id is None:
            return

        buf = ""
        msg_id = None
        last_update = 0.0

        async for chunk in chunks:
            buf += chunk
            now = time.time()
            if now - last_update > 0.5:  # throttle to 0.5s
                try:
                    if msg_id is None:
                        msg = await self.app.bot.send_message(
                            chat_id, buf[:4000] or "...", parse_mode="Markdown"
                        )
                        msg_id = msg.message_id
                    else:
                        await self.app.bot.edit_message_text(
                            buf[:4000], chat_id, msg_id, parse_mode="Markdown"
                        )
                    last_update = now
                except Exception as e:
                    logger.warning(f"Telegram stream throttle error: {e}")

        # Final update
        if msg_id and buf:
            try:
                await self.app.bot.edit_message_text(
                    buf[:4000], chat_id, msg_id, parse_mode="Markdown"
                )
            except Exception:
                pass

    async def send_typing(self, session_id: str) -> None:
        chat_id = self._session_to_chat.get(session_id)
        if chat_id and self.app:
            try:
                await self.app.bot.send_chat_action(chat_id, "typing")
            except Exception:
                pass

    async def _on_message(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> None:
        text = update.message.text
        session_id = self._resolve_session_id(update)
        if self.queue:
            await self.queue.submit(session_id, text)

    async def _on_media(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> None:
        session_id = self._resolve_session_id(update)

        if update.message.photo:
            file = await update.message.photo[-1].get_file()
        elif update.message.document:
            file = await update.message.document.get_file()
        else:
            return

        try:
            file_data = await file.download_as_bytearray()
            from claw.media.mime import guess_mime
            from claw.media.input import prepare_media_message
            mime = guess_mime(bytes(file_data), file.file_path or "")
            description = await prepare_media_message(
                bytes(file_data), mime, self.media_store, self.llm_router_url, self.api_key
            )
            if self.queue:
                await self.queue.submit(session_id, description)
        except Exception as e:
            logger.error(f"Telegram media processing error: {e}")

    def _resolve_session_id(self, update: "Update") -> str:
        """Map Telegram chat → claw session_id. Side-effect: updates _session_to_chat."""
        chat = update.effective_chat
        if chat.type == "private":
            session_id = "agent:main"
        else:
            session_id = f"agent:tg:group:{chat.id}"
        self._session_to_chat[session_id] = chat.id
        return session_id
