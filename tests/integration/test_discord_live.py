"""
Live Discord integration tests.
Requires: DISCORD_TOKEN, DISCORD_CHANNEL_ID environment variables.
"""
from __future__ import annotations

import os
import pytest
import asyncio
import discord
from datetime import datetime

pytestmark = pytest.mark.skipif(
    os.getenv("LIVE_BACKEND") != "1",
    reason="Discord live tests require LIVE_BACKEND=1"
)


@pytest.fixture
async def discord_client():
    """
    Create a Discord bot client for testing.
    Note: This requires a valid bot token with permissions to send messages.
    """
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        pytest.skip("DISCORD_TOKEN not set")

    bot = discord.Client(intents=discord.Intents.default())
    await bot.login(token)

    yield bot

    await bot.close()


@pytest.mark.asyncio
async def test_discord_send_embed_live(discord_client):
    """
    Test sending an Embed to Discord.

    驗證項目：
    - Embed 可以被正確序列化
    - Discord bot 可以連接
    - 訊息被成功發送（返回有效的 message_id）
    """
    channel_id = int(os.getenv("DISCORD_CHANNEL_ID", "0"))
    if channel_id == 0:
        pytest.skip("DISCORD_CHANNEL_ID not set")

    channel = discord_client.get_channel(channel_id)
    if not channel:
        pytest.skip(f"Channel {channel_id} not accessible")

    # 建立測試 Embed
    embed = discord.Embed(
        title="🧪 Integration Test — Embed Message",
        description="This is an automated test message.",
        color=discord.Color.blue(),
        timestamp=datetime.utcnow()
    )
    embed.add_field(name="Test Type", value="Discord Live Integration", inline=False)
    embed.add_field(name="Status", value="✓ Testing", inline=True)

    try:
        message = await channel.send(embed=embed)
        assert message.id
        print(f"✓ Embed sent successfully: message_id={message.id}")

        # 清理：刪除測試訊息
        await message.delete()
    except discord.Forbidden:
        pytest.skip("Bot lacks permission to send messages in channel")


@pytest.mark.asyncio
async def test_discord_send_file_live(discord_client):
    """
    Test sending a file (chart) to Discord.

    驗證項目：
    - 檔案附件被正確序列化
    - 可以成功上傳到 Discord
    - 訊息包含文件引用
    """
    channel_id = int(os.getenv("DISCORD_CHANNEL_ID", "0"))
    if channel_id == 0:
        pytest.skip("DISCORD_CHANNEL_ID not set")

    channel = discord_client.get_channel(channel_id)
    if not channel:
        pytest.skip(f"Channel {channel_id} not accessible")

    # 建立模擬 PNG 檔案
    from io import BytesIO
    png_data = b'\x89PNG\r\n\x1a\n' + b'\x00' * 1000  # 最小有效 PNG

    try:
        file = discord.File(BytesIO(png_data), filename="test_chart.png")
        message = await channel.send(file=file, content="Test chart upload")
        assert message.id
        assert len(message.attachments) > 0
        print(f"✓ File sent successfully: {message.attachments[0].filename}")

        # 清理
        await message.delete()
    except discord.Forbidden:
        pytest.skip("Bot lacks permission to send messages in channel")


@pytest.mark.asyncio
async def test_discord_stock_report_live(discord_client):
    """
    Test sending a complete stock report (Embed + Data).

    這個測試驗證整個晨報邏輯是否能成功推送到 Discord。
    """
    from claw.tools.stock_tools import stock_fetch, stock_analyze

    channel_id = int(os.getenv("DISCORD_CHANNEL_ID", "0"))
    if channel_id == 0:
        pytest.skip("DISCORD_CHANNEL_ID not set")

    channel = discord_client.get_channel(channel_id)
    if not channel:
        pytest.skip(f"Channel {channel_id} not accessible")

    # 拉取真實數據
    symbol = "2330"
    fetch_result = stock_fetch(symbol, period="1mo")
    report = stock_analyze(symbol, fetch_result.get("ohlcv", []))

    # 建立股票報告 Embed
    embed = discord.Embed(
        title=f"📈 Stock Report — {report.symbol} {report.name}",
        description=f"Live Analysis Report",
        color=discord.Color.green() if "buy" in report.signal else discord.Color.red(),
        timestamp=datetime.utcnow()
    )
    embed.add_field(name="Current Price", value=f"${report.current_price:.2f}", inline=True)
    embed.add_field(name="Signal", value=report.signal.upper(), inline=True)
    embed.add_field(name="Trend", value=report.trend, inline=True)
    embed.add_field(name="RSI", value=f"{report.indicators.rsi:.1f}", inline=True)
    embed.add_field(name="Summary", value=report.summary, inline=False)

    try:
        message = await channel.send(embed=embed)
        assert message.id
        print(f"✓ Stock report sent successfully")

        # 清理
        await message.delete()
    except discord.Forbidden:
        pytest.skip("Bot lacks permission")
