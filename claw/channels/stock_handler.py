"""Stock query handler for Discord - detects stock queries and returns formatted embeds."""
from __future__ import annotations

import re
import json
import logging
from datetime import datetime, timezone
from typing import Optional
from io import BytesIO

import discord

from claw.tools.stock_tools import stock_analyze, stock_fetch
from claw.tools.beautify import beautify_to_discord_embed

logger = logging.getLogger(__name__)

# Taiwan stock code patterns: 4 digits or with .TW
STOCK_CODE_PATTERN = re.compile(r'(\d{4})(?:\.TW)?', re.IGNORECASE)

# Common stock name mappings
STOCK_NAME_MAP = {
    "2330": "台積電",
    "2002": "中鋼",
    "1101": "台泥",
    "1102": "亞泥",
    "2317": "鴻海",
    "3008": "大立光",
    "2454": "聯發科",
    "2308": "台灣電",
}


async def detect_stock_query(message: str) -> Optional[str]:
    """
    偵測訊息中的股票代碼。

    Returns:
        股票代碼（4 碼），或 None

    Examples:
        "查一下2330" → "2330"
        "中鋼股價" → "2002"
        "台積電漲多少" → "2330"
    """
    # 嘗試從代碼匹配
    match = STOCK_CODE_PATTERN.search(message)
    if match:
        code = match.group(1).replace(".TW", "")
        return code

    # 嘗試從名稱匹配
    for code, name in STOCK_NAME_MAP.items():
        if name in message:
            return code

    return None


async def handle_stock_query(stock_code: str) -> tuple[Optional[dict], Optional[dict]]:
    """
    處理股票查詢。

    Args:
        stock_code: 4 位股票代碼（如 "2330"）

    Returns:
        (embed_dict, stock_data_dict) —— Embed 和原始股票數據（用於圖表）
    """
    try:
        logger.info(f"[Stock Handler] Querying stock {stock_code}")

        # 並行獲取分析和歷史數據
        analysis_task = stock_analyze(stock_code)
        fetch_task = stock_fetch(stock_code, period="1mo")

        stock_data = await analysis_task
        fetch_result = await fetch_task

        if isinstance(stock_data, str):
            stock_data = json.loads(stock_data)

        if isinstance(fetch_result, str):
            fetch_result = json.loads(fetch_result)

        # 取得股票名稱
        stock_name = stock_data.get("name", stock_code)

        # 將 OHLCV 數據添加到 stock_data（用於圖表生成）
        # fetch_result 可能是 list 或 dict
        if fetch_result:
            if isinstance(fetch_result, list):
                # 轉換格式：[{Date, Open, High, Low, Close, Volume}, ...] → [{date, open, high, low, close, volume}, ...]
                ohlcv_list = []
                for item in fetch_result:
                    ohlcv_list.append({
                        "date": item.get("Date", "").split("T")[0],  # 提取日期部分
                        "open": item.get("Open", 0),
                        "high": item.get("High", 0),
                        "low": item.get("Low", 0),
                        "close": item.get("Close", 0),
                        "volume": item.get("Volume", 0),
                    })
                stock_data["ohlcv"] = ohlcv_list
            elif isinstance(fetch_result, dict):
                stock_data["ohlcv"] = fetch_result.get("ohlcv", [])

        # 用美化工具格式化（beautify 返回 (embed_dict, chart_bytes)，股票用 K 線圖不用 LLM 圖表）
        embed_result, _ = await beautify_to_discord_embed(
            stock_data,
            title=f"{stock_code} {stock_name}",
            data_context="台灣股票技術分析報告，包含技術指標、基本面和投資建議"
        )

        logger.info(f"[Stock Handler] Successfully formatted stock {stock_code}")
        return embed_result, stock_data

    except Exception as e:
        logger.error(f"[Stock Handler] Failed to query stock {stock_code}: {e}")
        return None, None


async def send_embed_to_discord(
    channel: discord.abc.Messageable,
    embed_data: dict,
    stock_code: str | None = None,
    stock_data: dict | None = None,
) -> None:
    """
    發送 Discord Embed 到頻道，包括圖表。

    Args:
        channel: Discord 頻道/DM
        embed_data: beautify 返回的 embed dict
        stock_code: 股票代碼（用於生成參考 URL）
        stock_data: 股票數據（用於生成 K 線圖）
    """
    try:
        from claw.tools.chart_tools import generate_candlestick_chart

        # 從 beautify 結果中提取 embed
        embeds_list = embed_data.get("embeds", [])
        if not embeds_list:
            logger.warning("No embeds in beautify result")
            return

        # 轉換為 discord.Embed 對象
        discord_embeds = []
        chart_bytes = None

        for embed_dict in embeds_list:
            ts = None
            ts_str = embed_dict.get("timestamp")
            if ts_str:
                try:
                    ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    ts = datetime.now(timezone.utc)

            embed = discord.Embed(
                title=embed_dict.get("title"),
                description=embed_dict.get("description"),
                color=embed_dict.get("color", 0xAAAAAA),
                timestamp=ts,
            )

            # 添加欄位
            for field in embed_dict.get("fields", []):
                embed.add_field(
                    name=field.get("name"),
                    value=field.get("value"),
                    inline=field.get("inline", False),
                )

            # 生成 K 線圖（如果有股票數據）
            if stock_data and not chart_bytes:
                ohlcv_list = stock_data.get("ohlcv", [])
                if ohlcv_list:
                    try:
                        logger.info(f"[Stock Handler] Generating K-line chart for {stock_code}")
                        chart_bytes = generate_candlestick_chart(stock_code or "", ohlcv_list)
                        if chart_bytes:
                            embed.set_image(url="attachment://stock_chart.png")
                    except Exception as e:
                        logger.warning(f"Failed to generate K-line chart: {e}")

            # 添加參考 URL（如果有股票代碼）
            if stock_code:
                embed.add_field(
                    name="📊 參考連結",
                    value=f"[TWSE](https://www.twse.com.tw/en/) | "
                          f"[Yahoo](https://tw.finance.yahoo.com/quote/{stock_code}.TW) | "
                          f"[鉅亨](https://www.cnyes.com/twstock/quote/{stock_code})",
                    inline=False,
                )

            discord_embeds.append(embed)

        # 分次發送（Discord 最多 10 個 embed）
        for i in range(0, len(discord_embeds), 10):
            batch = discord_embeds[i:i+10]

            # 如果有圖表，與第一個 embed 一起發送
            if chart_bytes and i == 0:
                file = discord.File(
                    BytesIO(chart_bytes),
                    filename="stock_chart.png"
                )
                await channel.send(embeds=batch, file=file)
            else:
                await channel.send(embeds=batch)

        logger.info(f"[Stock Handler] Sent {len(discord_embeds)} embeds + chart to Discord")

    except Exception as e:
        logger.error(f"[Stock Handler] Failed to send embed: {e}")
        await channel.send(f"發送 Embed 失敗: {e}")
