"""Morning report job — daily stock screening and push to Discord."""
from __future__ import annotations

import logging
import json
import inspect
from datetime import datetime
from io import BytesIO

import discord

from claw.tools.stock_tools import stock_screen, stock_fetch
from claw.tools.chart_tools import generate_candlestick_chart
from claw.tools.portfolio_manager import PortfolioManager
from claw.channels.discord import DiscordChannel
from claw.core.config import get_config

logger = logging.getLogger(__name__)


def _get_attr(obj, name: str, default=None):
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


async def _maybe_await(value):
    if inspect.isawaitable(value):
        return await value
    return value


async def morning_report_job(
    storage,
    llm,
    cron_data: dict | None = None,
    discord_channel: DiscordChannel | None = None,
) -> dict:
    """
    Execute morning report: screen Taiwan 50, generate charts, push to Discord.

    Args:
        storage: Storage instance (for logging/persistence)
        llm: LLM client (not used in this phase, kept for future)
        cron_data: Dict with keys:
            - 'config': Full config object
            - 'channel_id': Discord channel ID (optional, use config.discord.stock_channel_id)

    Returns:
        {
            "status": "success",
            "stocks_screened": 15,
            "discord_pushed": True,
            "message_id": "123456789",
            "timestamp": "2026-03-22T08:00:00Z"
        }

    流程：
    1. 呼叫 stock_screen() → 取得前 10-15 個強勢股
    2. 對每個股票呼叫 generate_chart() → 生成 PNG
    3. 組合成 Discord Embed（標題、技術面摘要、圖表）
    4. 呼叫 DiscordChannel.send_to_channel_id() → 推送
    5. 記錄成功/失敗到 storage
    """
    try:
        cfg = get_config()
        channel_id = cron_data.get('channel_id') if cron_data else None
        if not channel_id:
            channel_id = getattr(cfg.discord, 'stock_channel_id', 0)
        if not channel_id:
            return {
                "status": "failed",
                "reason": "No Discord channel_id configured",
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }

        logger.info(f"Starting morning report job → Discord channel {channel_id}")

        # Step 1: Screen stocks
        screened_raw = await _maybe_await(stock_screen())
        if isinstance(screened_raw, str):
            try:
                screened = json.loads(screened_raw)
            except Exception:
                screened = []
        else:
            screened = screened_raw

        if not screened or not isinstance(screened, (list, tuple)):
            logger.warning("No stocks passed screening")
            return {
                "status": "no_stocks",
                "stocks_screened": 0,
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }

        logger.info(f"Screened {len(screened)} stocks")

        # Save top 5 to watchlist.json
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            pm = PortfolioManager()
            top5_records = []
            for r in screened[:5]:
                sym = _get_attr(r, "symbol", "")
                nm = _get_attr(r, "name", sym)
                sig = _get_attr(r, "signal", "hold")
                ind = _get_attr(r, "indicators")
                rsi_v = _get_attr(ind, "rsi_14", 50) if ind else 50
                summ = _get_attr(r, "summary", "")
                top5_records.append({"symbol": sym, "name": nm, "signal": sig, "rsi": round(float(rsi_v), 1), "summary": summ})
            pm.save_watchlist_entry(today, top5_records)
            logger.info(f"Watchlist updated: {[r['symbol'] for r in top5_records]}")
        except Exception as e:
            logger.warning(f"Failed to save watchlist: {e}")

        # Step 2: Generate embeds with charts
        embeds = []
        chart_payloads = []

        # Main embed: 標題 + 概述
        main_embed = discord.Embed(
            title="🌅 台股晨報 — Taiwan 50 強勢股",
            description=(
                f"篩選時間: {datetime.now().strftime('%Y-%m-%d %H:%M')} \n"
                f"共篩選 {len(screened)} 檔強勢股\n\n"
                "**Top 5 Strong Stocks:**"
            ),
            color=discord.Color.green(),
        )

        for i, report in enumerate(screened[:5]):
            symbol = _get_attr(report, "symbol", "")
            name = _get_attr(report, "name", "")
            price = _get_attr(report, "current_price", 0)
            indicators = _get_attr(report, "indicators")
            rsi = _get_attr(indicators, "rsi", None)
            if rsi is None:
                rsi = _get_attr(indicators, "rsi_14", 0)
            trend = _get_attr(report, "trend", "")
            signal = _get_attr(report, "signal", "") or _get_attr(report, "recommendation", "")
            summary = _get_attr(report, "summary", "")
            if not summary and indicators is not None:
                summary = _get_attr(indicators, "rsi_signal", "")

            main_embed.add_field(
                name=f"{i+1}. {symbol} {name}",
                value=(
                    f"💰 {price} TWD | Signal: {signal}\n"
                    f"RSI: {rsi:.1f} | {trend}\n"
                    f"📝 {summary}"
                ),
                inline=False,
            )

        embeds.append(main_embed)

        # Step 3: Generate individual charts
        for report in screened[:3]:  # 只前 3 個生成圖表（避免檔案太多）
            symbol = _get_attr(report, "symbol", "")
            if not symbol:
                continue
            try:
                fetch_result = await _maybe_await(stock_fetch(symbol, period="3mo"))
                ohlcv = fetch_result.get("ohlcv", []) if isinstance(fetch_result, dict) else []
                png_bytes = generate_candlestick_chart(symbol, ohlcv)

                filename = f"chart_{symbol}.png"
                chart_embed = discord.Embed(
                    title=f"📊 {symbol} 走勢圖",
                    description="近 3 個月 K 線圖",
                    color=discord.Color.blue(),
                )
                chart_embed.set_image(url=f"attachment://{filename}")
                chart_payloads.append((chart_embed, png_bytes, filename))

            except Exception as e:
                logger.warning(f"Failed to generate chart for {symbol}: {e}")
                continue

        # Step 4: Push to Discord
        if not discord_channel:
            logger.warning("Discord bot not available for push")
            return {
                "status": "no_bot",
                "reason": "Discord channel instance not provided",
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }

        await discord_channel.send_to_channel_id(
            channel_id=channel_id,
            embed=embeds[0],
            file_bytes=b"",
        )
        for chart_embed, png_bytes, filename in chart_payloads:
            await discord_channel.send_to_channel_id(
                channel_id=channel_id,
                embed=chart_embed,
                file_bytes=png_bytes,
                filename=filename,
            )
        logger.info(f"Morning report pushed to Discord channel {channel_id}")

        return {
            "status": "success",
            "stocks_screened": len(screened),
            "discord_pushed": True,
            "channel_id": channel_id,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }

    except Exception as e:
        logger.error(f"Morning report job failed: {e}", exc_info=True)
        return {
            "status": "failed",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
