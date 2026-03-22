# Phase 14 Worker Prompt — Discord Channel

你是實作 claw-python Phase 14 的 worker。工作目錄：`/home/martin/Desktop/claw-python-personal/`。
當前狀態：164 tests 通過（Phase 13 完成），0 failures。**嚴格按照順序，每步驗證後再繼續。**

---

## 背景說明

claw-python 已支援 Telegram 和 Slack 頻道。本 Phase 實作 Discord 頻道讓 agent 可透過 Discord bot 接收訊息。使用 discord.py。

---

## 設計規格

- **Channel class**: `DiscordChannel` (extends `BaseChannel`)
- **Bot**: Discord.py `discord.Bot`，intents = `message_content` + `messages`
- **Events**: `on_message`（所有訊息）、`on_ready`（登入完成）
- **Session mapping**: DM user `user_{id}`，群組 `channel_{id}`
- **Integration**: 同 Telegram/Slack，轉發到 gateway `/v1/chat/completions`

---

## Task 1 — 安裝 discord.py

在 `pyproject.toml` dependencies 加入：

```toml
"discord.py>=2.3.0",
```

執行 `pip install discord.py`

---

## Task 2 — 建立 `claw/channels/discord.py`

```python
from __future__ import annotations

import logging
import asyncio
import json
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
```

---

## Task 3 — 更新 `claw/main.py` 加入 Discord 啟動邏輯

在 Slack 處理後面加入（同一模式）：

```python
    if cfg.discord.enabled:
        if not cfg.discord.token or not cfg.discord.token.strip():
            logger.error(
                "Discord is enabled but token is empty. "
                "Set DISCORD_TOKEN environment variable or "
                "configure discord.token in config/default.yaml"
            )
        else:
            try:
                from claw.channels.discord import DiscordChannel
                discord = DiscordChannel(
                    token=cfg.discord.token.strip(),
                    base_url=f"http://localhost:{cfg.gateway.port}",
                )
                await discord.start()
                channels.append(discord)
                logger.info("Discord channel started successfully")
            except Exception as e:
                logger.error(f"Failed to start Discord channel: {e}")
```

---

## Task 4 — 更新 `config/default.yaml` 加入 Discord 設定

末尾加入：

```yaml
discord:
  enabled: false
  token: ""
  # Set DISCORD_TOKEN env var or token here
```

---

## Task 5 — 建立測試 `tests/test_discord.py`（3 tests）

```python
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_discord_channel_init():
    """DiscordChannel initializes with token and base_url."""
    from claw.channels.discord import DiscordChannel

    channel = DiscordChannel(token="test_token", base_url="http://localhost:18790")
    assert channel.token == "test_token"
    assert channel.base_url == "http://localhost:18790"
    assert channel.bot is not None


@pytest.mark.asyncio
async def test_discord_send():
    """send() method sends message to Discord channel."""
    from claw.channels.discord import DiscordChannel

    channel = DiscordChannel(token="test_token", base_url="http://localhost:18790")
    mock_discord_channel = AsyncMock()
    channel._session_clients["test_session"] = mock_discord_channel

    await channel.send("test_session", "Hello Discord")

    mock_discord_channel.send.assert_called_once_with("Hello Discord")


@pytest.mark.asyncio
async def test_discord_send_truncation():
    """send() truncates long messages to 2000 chars."""
    from claw.channels.discord import DiscordChannel

    channel = DiscordChannel(token="test_token", base_url="http://localhost:18790")
    mock_discord_channel = AsyncMock()
    channel._session_clients["test_session"] = mock_discord_channel

    long_text = "x" * 3000
    await channel.send("test_session", long_text)

    call_arg = mock_discord_channel.send.call_args[0][0]
    assert len(call_arg) <= 2000
    assert call_arg.endswith("...")
```

---

## Task 6 — 執行測試

```bash
cd /home/martin/Desktop/claw-python-personal
python -m pytest tests/ -x --tb=short
```

預期：**167 tests 通過，0 failures**（164 + 3 新增）

---

## 交付清單

完成後回報：
1. 每個新建/修改的檔案絕對路徑
2. pytest 最終輸出最後 5 行
3. 遇到的問題和解決方式

---

## 預期測試計數

| 來源 | 數量 |
|---|---|
| Phase 13（現有） | 164 |
| test_discord.py | +3 |
| **目標** | **167** |
