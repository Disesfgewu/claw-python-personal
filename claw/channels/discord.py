from __future__ import annotations

import logging
import asyncio
import json
import io
from typing import TYPE_CHECKING

import discord
from discord.ext import commands
from claw.core.protocol import ConnectFrame, ResponseFrame, EventFrame

if TYPE_CHECKING:
    from datetime import datetime

logger = logging.getLogger(__name__)


class DiscordChannel:
    def __init__(self, token: str, base_url: str):
        """
        Args:
            token: Discord bot token
            base_url: Base URL of gateway (e.g., "http://localhost:18790")
        """
        self.token = token
        self.base_url = base_url
        self.intents = discord.Intents.default()
        self.intents.message_content = True  # Read message content
        self.bot = commands.Bot(command_prefix="!", intents=self.intents)
        self._session_clients: dict[str, discord.abc.Messageable] = {}

        # Register event handlers
        @self.bot.event
        async def on_ready():
            logger.info(f"Discord bot logged in as {self.bot.user}")

        @self.bot.event
        async def on_message(message: discord.Message):
            # Ignore bot's own messages
            if message.author == self.bot.user:
                return
            await self._handle_message(message)

    async def start(self) -> None:
        """Start the Discord bot."""
        logger.info("Starting Discord channel")
        asyncio.create_task(self.bot.start(self.token))
        # Wait for bot to be ready
        await self.bot.wait_until_ready()
        logger.info("Discord channel started successfully")

    async def stop(self) -> None:
        """Stop the Discord bot."""
        logger.info("Stopping Discord channel")
        await self.bot.close()

    async def _handle_message(self, message: discord.Message) -> None:
        """Process incoming Discord message."""
        # Determine session_id based on message context
        if isinstance(message.channel, discord.DMChannel):
            session_id = f"agent:discord:user:{message.author.id}"
        else:
            session_id = f"agent:discord:channel:{message.channel.id}"

        # Remember the message channel for sending replies
        self._session_clients[session_id] = message.channel

        # Build ConnectFrame for gateway
        connect_frame = ConnectFrame(
            session_id=session_id,
            user_id=f"discord:{message.author.id}",
            channel="discord",
            scope="user" if isinstance(message.channel, discord.DMChannel) else "channel",
            config={},
        )

        # Send connect frame and user message to gateway
        # (In real implementation, would POST to gateway /v1/chat/completions)
        user_message = message.content

        try:
            import httpx

            async with httpx.AsyncClient() as client:
                # Connect
                resp = await client.post(
                    f"{self.base_url}/v1/chat/completions",
                    json={
                        "session_id": session_id,
                        "messages": [
                            {
                                "role": "user",
                                "content": user_message,
                            }
                        ],
                        "stream": True,
                    },
                    timeout=300,
                )

            if resp.status_code != 200:
                await message.reply(f"Error: {resp.status_code}")
                return

            # Stream response and collect text
            response_text = ""
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    try:
                        event = json.loads(line[6:])
                        if event.get("type") == "text":
                            response_text += event.get("content", "")
                    except json.JSONDecodeError:
                        pass

            # Send response back to Discord (chunked if > 2000 chars)
            if response_text:
                await self.send_stream(session_id, response_text)
            else:
                await message.reply("(no response)")

        except Exception as e:
            logger.error(f"Discord message processing error: {e}")
            await message.reply(f"Error: {type(e).__name__}: {e}")

    async def send(self, session_id: str, text: str) -> None:
        """Send a message to Discord."""
        channel = self._session_clients.get(session_id)
        if channel is None:
            logger.warning(f"No channel found for session {session_id}")
            return

        # Truncate to Discord limit (2000 chars)
        if len(text) > 2000:
            text = text[:1997] + "..."

        try:
            await channel.send(text)
        except Exception as e:
            logger.error(f"Failed to send message to {session_id}: {e}")

    async def send_stream(self, session_id: str, text: str) -> None:
        """Send text stream (buffered) to Discord."""
        channel = self._session_clients.get(session_id)
        if channel is None:
            logger.warning(f"No channel found for session {session_id}")
            return

        # Buffer and send in chunks <= 2000 chars
        chunks = [text[i : i + 2000] for i in range(0, len(text), 2000)]
        for chunk in chunks:
            try:
                await channel.send(chunk)
            except Exception as e:
                logger.error(f"Failed to send stream chunk to {session_id}: {e}")

    async def send_typing(self, session_id: str) -> None:
        """Show typing indicator."""
        channel = self._session_clients.get(session_id)
        if channel is not None:
            try:
                async with channel.typing():
                    await asyncio.sleep(2)
            except Exception as e:
                logger.error(f"Failed to show typing indicator: {e}")

    async def send_embed(
        self,
        session_id: str,
        embed: discord.Embed
    ) -> None:
        """Send a Discord Embed to session's channel."""
        channel = self._session_clients.get(session_id)
        if channel is None:
            logger.warning(f"No channel found for session {session_id}")
            return
        try:
            await channel.send(embed=embed)
        except Exception as e:
            logger.error(f"Failed to send embed to {session_id}: {e}")

    async def send_file(
        self,
        session_id: str,
        file_bytes: bytes,
        filename: str,
        caption: str = ""
    ) -> None:
        """Send a file attachment (e.g., chart image) to session's channel."""
        channel = self._session_clients.get(session_id)
        if channel is None:
            logger.warning(f"No channel found for session {session_id}")
            return
        try:
            file = discord.File(
                io.BytesIO(file_bytes),
                filename=filename
            )
            await channel.send(content=caption, file=file)
        except Exception as e:
            logger.error(f"Failed to send file to {session_id}: {e}")

    async def send_embed_with_file(
        self,
        session_id: str,
        embed: discord.Embed,
        file_bytes: bytes,
        filename: str
    ) -> None:
        """Send Embed + File together (for stock reports with charts)."""
        channel = self._session_clients.get(session_id)
        if channel is None:
            logger.warning(f"No channel found for session {session_id}")
            return
        try:
            file = discord.File(
                io.BytesIO(file_bytes),
                filename=filename
            )
            await channel.send(embed=embed, file=file)
        except Exception as e:
            logger.error(f"Failed to send embed+file to {session_id}: {e}")

    async def send_to_channel_id(
        self,
        channel_id: int,
        embed: discord.Embed = None,
        text: str = None,
        file_bytes: bytes = None,
        filename: str = None
    ) -> None:
        """
        Proactive push to a specific channel ID (for Cron jobs).
        Used by scheduled tasks to push morning/evening reports.
        """
        try:
            channel = await self.bot.fetch_channel(channel_id)
            if embed and file_bytes:
                file = discord.File(
                    io.BytesIO(file_bytes),
                    filename=filename
                )
                await channel.send(embed=embed, file=file)
            elif embed:
                await channel.send(embed=embed)
            elif file_bytes:
                file = discord.File(
                    io.BytesIO(file_bytes),
                    filename=filename
                )
                await channel.send(content=text or "", file=file)
            elif text:
                await channel.send(text)
        except Exception as e:
            logger.error(f"Failed to send to channel {channel_id}: {e}")
