from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import discord
import io


@pytest.mark.asyncio
async def test_discord_send_embed():
    """send_embed() sends an Embed to session's channel."""
    from claw.channels.discord import DiscordChannel

    channel = DiscordChannel(token="test_token", base_url="http://localhost:18790")
    mock_discord_channel = AsyncMock()
    channel._session_clients["test_session"] = mock_discord_channel

    embed = discord.Embed(title="Test", description="Test Embed")
    await channel.send_embed("test_session", embed)

    mock_discord_channel.send.assert_called_once()
    call_args = mock_discord_channel.send.call_args
    assert call_args[1]["embed"] == embed


@pytest.mark.asyncio
async def test_discord_send_file():
    """send_file() sends a file attachment."""
    from claw.channels.discord import DiscordChannel

    channel = DiscordChannel(token="test_token", base_url="http://localhost:18790")
    mock_discord_channel = AsyncMock()
    channel._session_clients["test_session"] = mock_discord_channel

    file_bytes = b"PNG_DATA_HERE"
    await channel.send_file("test_session", file_bytes, "chart.png", "Stock Chart")

    mock_discord_channel.send.assert_called_once()
    call_args = mock_discord_channel.send.call_args
    assert call_args[1]["content"] == "Stock Chart"
    # File object 被傳入，檢查是否呼叫了 send


@pytest.mark.asyncio
async def test_discord_send_embed_with_file():
    """send_embed_with_file() sends both Embed and File."""
    from claw.channels.discord import DiscordChannel

    channel = DiscordChannel(token="test_token", base_url="http://localhost:18790")
    mock_discord_channel = AsyncMock()
    channel._session_clients["test_session"] = mock_discord_channel

    embed = discord.Embed(title="Stock Report")
    file_bytes = b"PNG_DATA"
    await channel.send_embed_with_file("test_session", embed, file_bytes, "chart.png")

    mock_discord_channel.send.assert_called_once()
    call_args = mock_discord_channel.send.call_args
    assert call_args[1]["embed"] == embed


@pytest.mark.asyncio
async def test_discord_send_to_channel_id():
    """send_to_channel_id() uses bot.fetch_channel() for proactive push."""
    from claw.channels.discord import DiscordChannel

    channel = DiscordChannel(token="test_token", base_url="http://localhost:18790")

    mock_fetched_channel = AsyncMock()
    channel.bot.fetch_channel = AsyncMock(return_value=mock_fetched_channel)

    embed = discord.Embed(title="Morning Report")
    await channel.send_to_channel_id(123456, embed=embed)

    channel.bot.fetch_channel.assert_called_once_with(123456)
    mock_fetched_channel.send.assert_called_once()
