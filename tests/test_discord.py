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
