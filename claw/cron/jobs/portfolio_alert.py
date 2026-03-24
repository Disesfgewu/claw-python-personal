"""Portfolio alert job — analyzes holdings + top5 screened stocks, pushes buy/sell signals to Discord."""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from io import BytesIO

import discord

from claw.tools.portfolio_manager import PortfolioManager
from claw.tools.stock_tools import stock_screen, stock_chip, stock_news
from claw.tools.chart_tools import generate_candlestick_chart
from claw.channels.discord import DiscordChannel
from claw.core.config import get_config

logger = logging.getLogger(__name__)

# ── Signal thresholds ──────────────────────────────────────────────────────────
SELL_GAIN_THRESHOLD = 0.20   # 持倉漲幅 >= 20%
SELL_RSI_THRESHOLD  = 70.0   # RSI >= 70
BUY_RSI_THRESHOLD   = 35.0   # RSI <= 35
SELL_COLOR = 0xE03131        # Red
BUY_COLOR  = 0x00B94A        # Green
HOLD_COLOR = 0xAAAAAA        # Grey


def compute_signal(analysis: dict, holding: dict | None) -> str:
    """
    Returns "BUY", "SELL", or "HOLD".

    SELL: holding gain >= SELL_GAIN_THRESHOLD AND RSI >= SELL_RSI_THRESHOLD
    BUY:  RSI <= BUY_RSI_THRESHOLD AND MACD > MACD_signal (bullish cross)
    """
    indicators = analysis.get("indicators", {})
    rsi = float(indicators.get("rsi_14", 50))
    macd = float(indicators.get("macd", 0))
    macd_signal = float(indicators.get("macd_signal", 0))
    current_price = float(analysis.get("current_price", 0))

    if holding:
        cost = float(holding.get("cost_per_share", 0))
        if cost > 0:
            gain_pct = (current_price - cost) / cost
            if gain_pct >= SELL_GAIN_THRESHOLD and rsi >= SELL_RSI_THRESHOLD:
                return "SELL"

    if rsi <= BUY_RSI_THRESHOLD and macd > macd_signal:
        return "BUY"

    return "HOLD"


def _fmt(v, decimals=2, suffix=""):
    """Format a number for embed display."""
    if v is None:
        return "N/A"
    try:
        return f"{float(v):,.{decimals}f}{suffix}"
    except (TypeError, ValueError):
        return "N/A"


def _build_alert_embed(
    symbol: str,
    analysis: dict,
    holding: dict | None,
    chip: dict,
    news_list: list[dict],
    signal: str,
) -> discord.Embed:
    """Build a rich Discord Embed for one stock alert."""
    ind = analysis.get("indicators", {})
    name = analysis.get("name", symbol)
    current_price = analysis.get("current_price", 0)

    signal_emoji = {"BUY": "📈", "SELL": "📉", "HOLD": "📊"}.get(signal, "📊")
    color = {"BUY": BUY_COLOR, "SELL": SELL_COLOR, "HOLD": HOLD_COLOR}.get(signal, HOLD_COLOR)

    # Header
    desc_parts = [f"現價 **NT$ {_fmt(current_price)}**"]
    if holding:
        cost = holding.get("cost_per_share", 0)
        shares = holding.get("shares", 0)
        gain_pct = (current_price - cost) / cost * 100 if cost else 0
        gain_amt = (current_price - cost) * shares
        arrow = "▲" if gain_pct >= 0 else "▼"
        desc_parts.append(
            f"成本 {_fmt(cost)} | {arrow} {abs(gain_pct):.2f}% ({'+' if gain_amt >= 0 else ''}{gain_amt:,.0f} 元)"
        )
    desc_parts.append(f"持倉: {'是' if holding else '觀察'}")

    embed = discord.Embed(
        title=f"{signal_emoji} {symbol} {name} — [{signal}]",
        description="\n".join(desc_parts),
        color=color,
        timestamp=datetime.utcnow(),
    )

    # Technical indicators block
    embed.add_field(
        name="📐 均線",
        value=(
            f"MA5: {_fmt(ind.get('ma_5'))} | "
            f"MA10: {_fmt(ind.get('ma_10'))} | "
            f"MA20: {_fmt(ind.get('ma_20'))}"
        ),
        inline=False,
    )
    embed.add_field(
        name="📊 動能",
        value=(
            f"RSI5: {_fmt(ind.get('rsi_5'), 1)} | "
            f"RSI10: {_fmt(ind.get('rsi_10'), 1)} | "
            f"RSI14: {_fmt(ind.get('rsi_14'), 1)}\n"
            f"KD K: {_fmt(ind.get('kd_k'), 1)} | "
            f"KD D: {_fmt(ind.get('kd_d'), 1)}"
        ),
        inline=False,
    )
    embed.add_field(
        name="📉 MACD",
        value=(
            f"DIF: {_fmt(ind.get('macd'), 3)} | "
            f"Signal: {_fmt(ind.get('macd_signal'), 3)} | "
            f"OSC: {_fmt(ind.get('osc'), 3)}"
        ),
        inline=False,
    )
    embed.add_field(
        name="🎯 布林帶",
        value=(
            f"上: {_fmt(ind.get('bollinger_upper'))} | "
            f"中: {_fmt(ind.get('bollinger_middle'))} | "
            f"下: {_fmt(ind.get('bollinger_lower'))}"
        ),
        inline=False,
    )
    embed.add_field(
        name="📦 成交量均線",
        value=(
            f"VOL5: {_fmt(ind.get('vol_5'), 0)} | "
            f"VOL10: {_fmt(ind.get('vol_10'), 0)}"
        ),
        inline=False,
    )

    # Chip data
    embed.add_field(
        name="🏦 籌碼面",
        value=(
            f"外資: {_fmt(chip.get('net_foreign'), 0)}張 | "
            f"投信: {_fmt(chip.get('net_trust'), 0)}張\n"
            f"融資餘額: {_fmt(chip.get('margin_balance'), 0)}張 | "
            f"融券餘額: {_fmt(chip.get('short_balance'), 0)}張"
        ),
        inline=False,
    )

    # News links (up to 3)
    if news_list:
        news_links = " | ".join(
            f"[{n['title'][:20]}…]({n['url']})" if n.get("url") else n["title"][:25]
            for n in news_list[:3]
            if n.get("title")
        )
        if news_links:
            embed.add_field(name="📰 最新新聞", value=news_links, inline=False)

    # Reference links
    embed.add_field(
        name="🔗 參考連結",
        value=(
            f"[TWSE](https://www.twse.com.tw/zh/stock/info?stockNo={symbol}) | "
            f"[Yahoo](https://tw.finance.yahoo.com/quote/{symbol}.TW) | "
            f"[鉅亨](https://www.cnyes.com/twstock/quote/{symbol})"
        ),
        inline=False,
    )

    return embed


async def portfolio_alert_job(
    storage=None,
    llm=None,
    cron_data: dict | None = None,
    discord_channel: DiscordChannel | None = None,
) -> dict:
    """
    Portfolio alert cron job.

    Flow:
    1. Read data/portfolio.json → user's holdings
    2. Run stock_screen() → top 5 screened stocks; save to watchlist.json
    3. Union of portfolio symbols + top 5
    4. For each: stock_analyze() + stock_chip() + stock_news()
    5. Compute signal (BUY / SELL / HOLD)
    6. Push only BUY/SELL signals to Discord with embed + K-line chart

    Args:
        discord_channel: live DiscordChannel instance (needed to push).
                         If None, logs warning and skips Discord push.
    """
    try:
        cfg = get_config()
        channel_id: int = 0
        if cron_data:
            channel_id = int(cron_data.get("channel_id", 0))
        if not channel_id:
            channel_id = getattr(cfg.discord, "stock_channel_id", 0) or \
                         getattr(cfg.discord, "morning_report_channel_id", 0)

        today = datetime.now().strftime("%Y-%m-%d")
        pm = PortfolioManager()

        # ── 1. Portfolio holdings ──────────────────────────────────────────
        holdings = pm.get_holdings()
        portfolio_symbols = {h["symbol"] for h in holdings}
        logger.info(f"[PortfolioAlert] Portfolio: {portfolio_symbols}")

        # ── 2. Screen top 5 ───────────────────────────────────────────────
        screened = []
        try:
            raw = stock_screen()
            screened = raw[:5] if raw else []
        except Exception as e:
            logger.warning(f"[PortfolioAlert] stock_screen failed: {e}")

        # Save to watchlist
        top5_records = []
        for r in screened:
            sym = r.symbol if hasattr(r, "symbol") else r.get("symbol", "")
            nm = r.name if hasattr(r, "name") else r.get("name", sym)
            sig = r.signal if hasattr(r, "signal") else r.get("signal", "hold")
            rsi_v = r.indicators.rsi_14 if hasattr(r, "indicators") else r.get("rsi", 50)
            summ = r.summary if hasattr(r, "summary") else r.get("summary", "")
            top5_records.append({"symbol": sym, "name": nm, "signal": sig, "rsi": round(float(rsi_v), 1), "summary": summ})
        pm.save_watchlist_entry(today, top5_records)

        screen_symbols = {r["symbol"] for r in top5_records}

        # ── 3. Union ──────────────────────────────────────────────────────
        all_symbols = portfolio_symbols | screen_symbols
        logger.info(f"[PortfolioAlert] Analyzing {len(all_symbols)} symbols: {all_symbols}")

        if not all_symbols:
            return {"status": "no_symbols", "timestamp": today}

        # ── 4. Analyze each symbol ────────────────────────────────────────
        from claw.tools.stock_tools import stock_analyze, stock_fetch_data

        async def _analyze_one(sym: str) -> dict | None:
            try:
                raw_json = await stock_analyze(sym)
                analysis = json.loads(raw_json) if isinstance(raw_json, str) else raw_json
                chip = stock_chip(sym)
                news_list = stock_news(sym, limit=3)
                return {"symbol": sym, "analysis": analysis, "chip": chip, "news": news_list}
            except Exception as e:
                logger.warning(f"[PortfolioAlert] analyze {sym} failed: {e}")
                return None

        tasks = [_analyze_one(sym) for sym in all_symbols]
        results_raw = await asyncio.gather(*tasks)
        results = [r for r in results_raw if r is not None]

        # ── 5. Compute signals ────────────────────────────────────────────
        signal_items = []
        for item in results:
            sym = item["symbol"]
            holding = pm.get_holding(sym)
            signal = compute_signal(item["analysis"], holding)
            item["signal"] = signal
            item["holding"] = holding
            if signal in ("BUY", "SELL"):
                signal_items.append(item)

        logger.info(f"[PortfolioAlert] Signals: {[(i['symbol'], i['signal']) for i in signal_items]}")

        if not signal_items:
            return {
                "status": "no_signal",
                "analyzed": len(results),
                "timestamp": today,
            }

        # ── 6. Push to Discord ────────────────────────────────────────────
        if not discord_channel or not channel_id:
            logger.warning("[PortfolioAlert] No Discord channel — skipping push")
            return {
                "status": "no_push",
                "signals": [(i["symbol"], i["signal"]) for i in signal_items],
                "timestamp": today,
            }

        # Header embed
        header = discord.Embed(
            title=f"🔔 投資訊號提醒 — {today}",
            description=(
                f"分析 **{len(results)}** 檔標的（持倉 {len(portfolio_symbols)} + 篩選 {len(screen_symbols)}）\n"
                f"發現 **{len(signal_items)}** 個交易訊號"
            ),
            color=0xF4A800,
        )
        await discord_channel.send_to_channel_id(channel_id, embed=header)

        # Individual signal embeds
        for item in signal_items:
            sym = item["symbol"]
            analysis = item["analysis"]
            chip = item["chip"]
            news_list = item["news"]
            holding = item["holding"]
            signal = item["signal"]

            embed = _build_alert_embed(sym, analysis, holding, chip, news_list, signal)

            # K-line chart
            chart_bytes = None
            try:
                fetch_result = await stock_fetch_data(sym, period="3mo")
                ohlcv = fetch_result.get("ohlcv", [])
                if ohlcv:
                    chart_bytes = generate_candlestick_chart(sym, ohlcv)
                    embed.set_image(url="attachment://chart.png")
            except Exception as e:
                logger.warning(f"[PortfolioAlert] Chart failed for {sym}: {e}")

            await discord_channel.send_to_channel_id(
                channel_id,
                embed=embed,
                file_bytes=chart_bytes or b"",
                filename="chart.png",
            )

        return {
            "status": "success",
            "analyzed": len(results),
            "signals": [(i["symbol"], i["signal"]) for i in signal_items],
            "discord_pushed": True,
            "channel_id": channel_id,
            "timestamp": today,
        }

    except Exception as e:
        logger.error(f"[PortfolioAlert] Job failed: {e}", exc_info=True)
        return {"status": "failed", "error": str(e), "timestamp": datetime.now().isoformat()}
