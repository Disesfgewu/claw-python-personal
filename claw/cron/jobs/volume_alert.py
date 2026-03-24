"""Volume surge alert job — runs at 17:30 weekdays, pushes if abnormal volume detected."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from claw.channels.discord import DiscordChannel

import discord as discord_lib

from claw.tools.stock_tools import stock_screen, stock_chip
from claw.core.config import get_config

logger = logging.getLogger(__name__)

_SURGE_THRESHOLD = 2.0   # volume_ratio ≥ 2× average → alert
_MIN_PRICE_CHANGE = 0.5  # only alert if price also moved ≥ 0.5%


async def volume_alert_job(
    discord_channel: "DiscordChannel | None" = None,
) -> dict:
    """
    After-market scan (17:30 weekdays): detect abnormal volume surges.

    Criteria:
        - 量比 (today / avg_10d) ≥ 2.0
        - AND (price ▲ ≥ 0.5% OR net_foreign > 500)

    Pushes an alert embed listing triggered stocks.
    """
    if not discord_channel:
        logger.warning("[VolumeAlert] No discord_channel injected — skipping push")
        return {"status": "no_channel"}

    try:
        cfg = get_config()
        channel_id = getattr(cfg.discord, "stock_channel_id", 0)
        if not channel_id:
            return {"status": "no_channel_id"}

        import asyncio

        # Screen with broad criteria (no signal filter, we'll filter by volume)
        all_reports = await asyncio.to_thread(
            stock_screen,
            {"rsi_min": 0, "rsi_max": 100, "volume_threshold": 0, "signal": None},
        )

        # Detect surges
        alerts = []
        for r in all_reports:
            vol_today = getattr(r, "volume", 0) or 0
            vol_10 = float(r.indicators.vol_10 or 0)
            vol_5  = float(r.indicators.vol_5  or 0)
            avg_vol = vol_10 or vol_5
            if not avg_vol:
                continue
            ratio = vol_today / avg_vol
            if ratio < _SURGE_THRESHOLD:
                continue
            chg = getattr(r, "change_pct", 0.0)
            if abs(chg) < _MIN_PRICE_CHANGE:
                # Volume surge but price flat — less interesting
                # still include if RSI or KD signals are interesting
                if not (r.indicators.kd_k > r.indicators.kd_d and r.indicators.rsi_14 < 65):
                    continue

            # Fetch chip data quickly
            try:
                chip = await asyncio.to_thread(stock_chip, r.symbol)
                net_f = chip.get("net_foreign", 0)
            except Exception:
                chip = None
                net_f = 0

            alerts.append({
                "report": r,
                "vol_ratio": ratio,
                "net_foreign": net_f,
                "chip": chip,
            })

        if not alerts:
            logger.info("[VolumeAlert] No surge alerts triggered")
            return {"status": "no_alerts"}

        # Sort by volume ratio descending
        alerts.sort(key=lambda x: x["vol_ratio"], reverse=True)
        top_alerts = alerts[:5]

        # Build header embed
        today = datetime.now().strftime("%Y-%m-%d")
        header = discord_lib.Embed(
            title="⚡ 異常成交量警示",
            description=(
                f"偵測到以下個股成交量異常放大（{today} 收盤後）\n"
                f"可能有大戶佈局訊號，共 **{len(alerts)}** 檔觸發條件"
            ),
            color=0xDA373C,
            timestamp=datetime.now(),
        )
        for a in top_alerts:
            r = a["report"]
            chg = getattr(r, "change_pct", 0.0)
            arrow = "▲" if chg >= 0 else "▼"
            net_f = a["net_foreign"]
            f_label = f"外資{'買超▲' if net_f > 0 else '賣超▼'} {abs(net_f):,}張" if net_f else "外資資料 —"
            header.add_field(
                name=f"{r.symbol} {r.name}",
                value=(
                    f"量比 **+{(a['vol_ratio']-1)*100:.0f}%**（{a['vol_ratio']:.1f}× 均量）\n"
                    f"{f_label}\n"
                    f"收 ${r.current_price:,.2f} {arrow}{abs(chg):.2f}%"
                ),
                inline=True,
            )
        # Pad to multiple of 3 for clean grid
        while len(top_alerts) % 3 != 0:
            header.add_field(name="\u200b", value="\u200b", inline=True)

        header.set_footer(text="⚠️ 量化模型輸出，不構成買賣建議 · 資料：TWSE 收盤後")

        # Push header
        await discord_channel.send_to_channel_id(
            channel_id=channel_id,
            embed=header,
        )

        # Push one detailed embed per alert (up to 3)
        for a in top_alerts[:3]:
            r = a["report"]
            ind = r.indicators
            chg = getattr(r, "change_pct", 0.0)
            arrow = "▲" if chg >= 0 else "▼"
            kd_trend = "金叉▲" if ind.kd_k > ind.kd_d else "死叉▼"
            macd_trend = "偏多▲" if ind.macd > ind.macd_signal else "偏空▼"

            det = discord_lib.Embed(
                title=f"📊 {r.symbol} {r.name} — 量能異常詳情",
                description=(
                    f"量比 **{a['vol_ratio']:.1f}×** 均量 "
                    f"({int(a['vol_ratio']*100-100)}% 超出10日均量)"
                ),
                color=0xE67E22,
            )
            vol_zhang = (getattr(r, "volume", 0) or 0) // 1000
            det.add_field(name="💰 收盤價", value=f"NT$ {r.current_price:,.2f}", inline=True)
            det.add_field(name="📈 漲跌", value=f"{arrow} {abs(chg):.2f}%", inline=True)
            det.add_field(name="📦 成交量", value=f"{vol_zhang:,}張", inline=True)
            det.add_field(name="📊 RSI(14)", value=f"{ind.rsi_14:.1f}", inline=True)
            det.add_field(name="📐 KD", value=f"K:{ind.kd_k:.1f} D:{ind.kd_d:.1f} {kd_trend}", inline=True)
            det.add_field(name="📉 MACD", value=macd_trend, inline=True)
            if a["net_foreign"]:
                det.add_field(
                    name="🏦 外資",
                    value=f"{'買超▲' if a['net_foreign'] > 0 else '賣超▼'} {abs(a['net_foreign']):,}張",
                    inline=True,
                )
            det.add_field(
                name="🔗 參考連結",
                value=(
                    f"[TWSE](https://www.twse.com.tw/zh/stock/info?stockNo={r.symbol}) | "
                    f"[Yahoo](https://tw.finance.yahoo.com/quote/{r.symbol}.TW)"
                ),
                inline=False,
            )
            det.set_footer(text=f"更新時間 {datetime.now().strftime('%H:%M')} · TWSE 收盤後資料")

            await discord_channel.send_to_channel_id(
                channel_id=channel_id,
                embed=det,
            )

        logger.info(f"[VolumeAlert] Pushed {len(top_alerts)} alerts to channel {channel_id}")
        return {"status": "success", "alerts": len(alerts), "pushed": len(top_alerts)}

    except Exception as e:
        logger.error(f"[VolumeAlert] Job failed: {e}", exc_info=True)
        return {"status": "failed", "error": str(e)}
