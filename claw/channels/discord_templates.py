"""Discord response templates — each class handles one ResponseType."""
from __future__ import annotations

import io
import json
import logging
import re
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Optional

import discord

from claw.channels.discord_response import DiscordResponse
from claw.channels.discord_components import Emoji, make_stock_view, make_event_view

logger = logging.getLogger(__name__)


# ─── Shared helpers ───────────────────────────────────────────────────────────

def _parse_ts(ts_str: str | None) -> Optional[datetime]:
    if not ts_str:
        return None
    try:
        return datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return datetime.now(timezone.utc)


def _dict_to_embed(embed_dict: dict) -> discord.Embed:
    """Convert a LLM-generated embed dict to a discord.Embed object."""
    embed = discord.Embed(
        title=embed_dict.get("title"),
        description=embed_dict.get("description"),
        color=embed_dict.get("color", 0xAAAAAA),
        timestamp=_parse_ts(embed_dict.get("timestamp")),
    )
    for field in embed_dict.get("fields", []):
        embed.add_field(
            name=field.get("name", "\u200b"),
            value=field.get("value", "\u200b"),
            inline=field.get("inline", False),
        )
    return embed


def _dicts_to_embeds(embed_data: dict) -> list[discord.Embed]:
    return [_dict_to_embed(e) for e in embed_data.get("embeds", [])]


def _signal_to_color(signal: str) -> int:
    return {
        "buy": 0x23A559, "strong_buy": 0x23A559,
        "sell": 0xDA373C, "strong_sell": 0xDA373C,
    }.get((signal or "").lower(), 0x5865F2)


def _fmt(v, d: int = 2, suffix: str = "") -> str:
    if v is None:
        return "N/A"
    try:
        return f"{float(v):,.{d}f}{suffix}"
    except (TypeError, ValueError):
        return "N/A"


# ─── Abstract base ────────────────────────────────────────────────────────────

class DiscordTemplate(ABC):
    """
    Base class for all Discord response templates.

    Subclasses implement build() which returns a DiscordResponse.
    Templates are stateless — a new instance is used for each message.
    """

    @abstractmethod
    async def build(self, context: dict) -> DiscordResponse:
        """
        Build the full Discord response for this context.

        Args:
            context: dict from DiscordFormatter.classify()
                - query: str
                - llm_response: str
                - stock_code: str | None  (STOCK only)

        Returns:
            DiscordResponse with embeds, chart, view, reactions
        """

    async def _beautify(
        self,
        data,
        title: str,
        data_context: str,
    ) -> tuple[dict, Optional[bytes]]:
        """Call beautify_to_discord_embed and return (embed_dict, chart_bytes)."""
        from claw.tools.beautify import beautify_to_discord_embed
        try:
            return await beautify_to_discord_embed(data, title=title, data_context=data_context)
        except Exception as e:
            logger.error(f"[{self.__class__.__name__}] beautify failed: {e}")
            fallback = {"embeds": [{"title": title, "description": str(data)[:500], "color": 0xAAAAAA}]}
            return fallback, None


# ─── Stock Template ───────────────────────────────────────────────────────────

class StockTemplate(DiscordTemplate):
    """
    Stock query template.

    Features:
    - Embed with technical indicators + fundamentals
    - 1-month K-line chart attached
    - 🔄 refresh button
    - Time range select (1W / 1M / 3M / 6M / 1Y)
    - Reference URLs (TWSE / Yahoo / 鉅亨)
    - 📈/📉 reaction based on signal
    """

    async def build(self, context: dict) -> DiscordResponse:
        import asyncio

        stock_code = context.get("stock_code")
        if not stock_code:
            return await GeneralTemplate().build(context)

        period = context.get("period", "1mo")

        try:
            from claw.tools.stock_tools import stock_analyze, stock_fetch, stock_chip, stock_news
            from claw.tools.chart_tools import generate_candlestick_chart

            # Parallel fetch: analyze + OHLCV + chip + news
            stock_data_raw, ohlcv_raw, chip, news_list = await asyncio.gather(
                stock_analyze(stock_code),
                stock_fetch(stock_code, period=period),
                asyncio.to_thread(stock_chip, stock_code),
                asyncio.to_thread(stock_news, stock_code, 3),
            )

            stock_data = json.loads(stock_data_raw) if isinstance(stock_data_raw, str) else stock_data_raw
            ohlcv_list = json.loads(ohlcv_raw) if isinstance(ohlcv_raw, str) else ohlcv_raw

            # Normalize OHLCV
            ohlcv = []
            for item in (ohlcv_list if isinstance(ohlcv_list, list) else []):
                ohlcv.append({
                    "date": item.get("Date", item.get("date", "")).split("T")[0],
                    "open": float(item.get("Open", item.get("open", 0))),
                    "high": float(item.get("High", item.get("high", 0))),
                    "low": float(item.get("Low", item.get("low", 0))),
                    "close": float(item.get("Close", item.get("close", 0))),
                    "volume": int(item.get("Volume", item.get("volume", 0))),
                })

        except Exception as e:
            logger.error(f"[StockTemplate] Data fetch failed: {e}")
            return DiscordResponse(text=f"無法查詢股票 {stock_code}: {e}")

        # ── Extract fields ───────────────────────────────────────────────
        ind = stock_data.get("indicators", {})
        fund = stock_data.get("fundamental", {})
        signal = stock_data.get("signal", "hold")
        stock_name = stock_data.get("name", stock_code)
        current_price = float(stock_data.get("current_price", 0))

        # Change % and volume from OHLCV
        # yfinance volume is in shares; 1 張 = 1000 shares
        change_pct = 0.0
        volume_zhang = 0
        if len(ohlcv) >= 2:
            prev_close = ohlcv[-2]["close"]
            if prev_close:
                change_pct = (ohlcv[-1]["close"] - prev_close) / prev_close * 100
        if ohlcv:
            volume_zhang = ohlcv[-1]["volume"] // 1000

        # Sentiment-analyze news in-place (sets 'sentiment' field on each item)
        if news_list:
            try:
                from claw.tools.stock_tools import sentiment_analyze
                sentiment_analyze(news_list)
            except Exception:
                pass

        # Pre-compute indicator values for description
        rsi14 = float(ind.get("rsi_14", 0))
        kdk = float(ind.get("kd_k", 0))
        kdd = float(ind.get("kd_d", 0))
        macd_v = float(ind.get("macd", 0))
        macd_sig_v = float(ind.get("macd_signal", 0))
        boll_lower = float(ind.get("bollinger_lower") or 0)
        boll_upper = float(ind.get("bollinger_upper") or 0)

        # ── AI opinion via Gemma (with rule-based fallback) ──────────────
        _router_url = context.get("_router_url", "")
        _intent_model = context.get("_intent_model", "")

        description = ""
        if _router_url and _intent_model:
            # Build compact data summary for Gemma
            news_headlines = "; ".join(
                (n.get("title", "")[:40] for n in (news_list or [])[:3] if n.get("title")),
            ) or "無"
            chip_summary = ""
            if chip and chip.get("source") not in ("mock", "", None):
                chip_summary = f"外資 {chip.get('net_foreign', 0):+,}張 / 投信 {chip.get('net_trust', 0):+,}張"
            else:
                chip_summary = "法人資料暫無"
            opinion_prompt = (
                f"股票：{stock_code} {stock_name}  現價：{current_price:.2f}  "
                f"漲跌：{change_pct:+.2f}%  成交量：{volume_zhang:,}張\n"
                f"技術訊號：{signal}  RSI:{rsi14:.1f}  KD K/D:{kdk:.1f}/{kdd:.1f}  "
                f"MACD DIF/Signal:{macd_v:.4f}/{macd_sig_v:.4f}\n"
                f"法人籌碼：{chip_summary}\n"
                f"最新新聞：{news_headlines}\n\n"
                "請用繁體中文，60 字以內，給出：①買賣建議（買進/賣出/觀察）②主要理由 ③主要風險。"
            )
            description = await _call_llm_direct(
                _router_url, _intent_model, opinion_prompt,
                system="你是專業台股 AI 分析師，根據技術指標、籌碼和新聞給出簡潔買賣建議。",
                max_tokens=120, temperature=0.5,
            )

        if not description:
            # Rule-based fallback
            _signal_text = {
                "strong_buy": "技術強勢，多指標共振偏多",
                "buy": "技術偏多，具買進潛力",
                "hold": "技術中性，建議觀察",
                "sell": "技術偏空，留意風險",
                "strong_sell": "技術弱勢，多指標轉空",
            }
            desc_parts = [_signal_text.get(signal, "技術中性")]
            if kdk > kdd:   desc_parts.append("KD 金叉")
            elif kdk < kdd: desc_parts.append("KD 死叉")
            if macd_v > macd_sig_v:   desc_parts.append("MACD 偏多")
            elif macd_v < macd_sig_v: desc_parts.append("MACD 偏空")
            if rsi14 < 30:  desc_parts.append("RSI 超賣區")
            elif rsi14 > 70: desc_parts.append("RSI 超買區")
            description = "，".join(desc_parts) + "。"

        # ── Build embed ──────────────────────────────────────────────────
        embed = discord.Embed(
            title=f"📊 {stock_code} {stock_name} — 個股分析報告",
            description=description,
            color=_signal_to_color(signal),
            timestamp=datetime.now(timezone.utc),
        )

        # Row 1 (inline×3): 現價 | 漲跌 | 成交量
        arrow = "▲" if change_pct >= 0 else "▼"
        embed.add_field(name="💰 現價", value=f"NT$ {current_price:,.2f}", inline=True)
        embed.add_field(name="📈 漲跌", value=f"{arrow} {abs(change_pct):.2f}%", inline=True)
        embed.add_field(name="📦 成交量", value=f"{volume_zhang:,}張", inline=True)

        # Row 2 (inline×3): RSI | KD | MACD  (vars already computed above for description)
        kd_trend = "金叉▲" if kdk > kdd else ("死叉▼" if kdk < kdd else "持平")
        macd_trend = "▲ 正面" if macd_v > macd_sig_v else "▼ 負面"
        macd_decimals = 4 if current_price < 100 else 3
        embed.add_field(name="📊 RSI(14)", value=f"{rsi14:.1f}", inline=True)
        embed.add_field(name="📐 KD", value=f"K:{kdk:.1f} D:{kdd:.1f} {kd_trend}", inline=True)
        embed.add_field(name="📉 MACD", value=f"DIF:{_fmt(macd_v, macd_decimals)} {macd_trend}", inline=True)


        # Row 3 (inline×3): MA5/MA20 | 布林帶上 | 布林帶下
        embed.add_field(
            name="📏 MA5 / MA20",
            value=f"{_fmt(ind.get('ma_5'))} / {_fmt(ind.get('ma_20'))}",
            inline=True,
        )
        embed.add_field(name="🎯 布林帶上", value=_fmt(ind.get("bollinger_upper")), inline=True)
        embed.add_field(name="🎯 布林帶下", value=_fmt(ind.get("bollinger_lower")), inline=True)

        # Row 4 (inline×3): 外資 | 投信 | 本益比
        net_f = chip.get("net_foreign", 0) if chip else 0
        net_t = chip.get("net_trust", 0) if chip else 0
        pe = fund.get("pe_ratio")

        chip_source = chip.get("source", "mock") if chip else "mock"
        chip_date = chip.get("date", "") if chip else ""
        is_real_chip = chip_source not in ("mock", "")

        if not is_real_chip:
            f_val = t_val = "—"
        else:
            f_val = ("買超▲" if net_f > 0 else ("賣超▼" if net_f < 0 else "持平")) + f" {abs(net_f):,}張"
            t_val = ("買超▲" if net_t > 0 else ("賣超▼" if net_t < 0 else "持平")) + f" {abs(net_t):,}張"
        pe_val = f"{float(pe):.2f}x" if pe else "N/A"

        embed.add_field(name="🏦 外資", value=f_val, inline=True)
        embed.add_field(name="📊 投信", value=t_val, inline=True)
        embed.add_field(name="📋 本益比", value=pe_val, inline=True)

        # Row 5: 相關新聞 (inline=False) — title + source + sentiment per item
        if news_list:
            _sent_emoji = {"positive": "🟢 正面", "negative": "🔴 負面", "neutral": "⚪ 中立"}
            news_lines = []
            for n in news_list[:3]:
                if not n.get("title"):
                    continue
                title = n["title"][:32] + ("…" if len(n["title"]) > 32 else "")
                url = n.get("url", "")
                source = n.get("source", "")
                date = (n.get("publish_date") or "")[:10]
                sent = _sent_emoji.get(n.get("sentiment", "neutral"), "⚪ 中立")
                headline = f"[{title}]({url})" if url else title
                meta = " ｜ ".join(x for x in [source, date, sent] if x)
                news_lines.append(f"{headline}\n{meta}" if meta else headline)
            if news_lines:
                embed.add_field(name="📰 相關新聞", value="\n\n".join(news_lines), inline=False)

        # ── Optional: quantitative analysis section ──────────────────────
        # Triggered when query contains quant keywords
        query_text = context.get("query", "")
        _QUANT_KEYWORDS = re.compile(r'量化|衝量|動態預測|動量|信心|勝率|回測|surge|momentum|quant', re.IGNORECASE)
        if _QUANT_KEYWORDS.search(query_text):
            avg_vol_10 = float(ind.get("vol_10") or 0)
            avg_vol_5  = float(ind.get("vol_5")  or 0)
            vol_today  = volume_zhang  # already in 張
            avg_vol_ref = avg_vol_10 or avg_vol_5
            vol_ratio = (vol_today / avg_vol_ref * 100) if avg_vol_ref else 0

            surge_label = "量能正常"
            if vol_ratio >= 200: surge_label = "🔥 爆量（量比 ≥ 200%）"
            elif vol_ratio >= 150: surge_label = "⚡ 量能放大（量比 ≥ 150%）"
            elif vol_ratio < 50:   surge_label = "📉 縮量（量比 < 50%）"

            # Momentum score: count aligned indicators
            momentum_pts = 0
            momentum_total = 5
            if rsi14 > 50: momentum_pts += 1
            if macd_v > macd_sig_v: momentum_pts += 1
            if kdk > kdd: momentum_pts += 1
            if current_price > float(ind.get("ma_20") or current_price): momentum_pts += 1
            if vol_ratio >= 100: momentum_pts += 1
            momentum_score = int(momentum_pts / momentum_total * 100)

            # Signal confidence: how many indicators align with the signal
            bull_count = sum([
                rsi14 < 70, macd_v > macd_sig_v, kdk > kdd,
                current_price > float(ind.get("ma_20") or 0),
                boll_lower > 0 and current_price <= boll_lower * 1.02,
            ])
            if signal in ("buy", "strong_buy"):
                confidence = int(bull_count / 5 * 100)
            elif signal in ("sell", "strong_sell"):
                confidence = int((5 - bull_count) / 5 * 100)
            else:
                confidence = 50

            # Bollinger position
            boll_mid = float(ind.get("bollinger_middle") or 0)
            if boll_mid and boll_upper and boll_lower and boll_upper != boll_lower:
                boll_pos = (current_price - boll_lower) / (boll_upper - boll_lower)
                boll_label = f"{boll_pos:.0%} 位置"
                if boll_pos >= 0.9: boll_label += "（接近上軌，壓力）"
                elif boll_pos <= 0.1: boll_label += "（接近下軌，支撐）"
            else:
                boll_label = "N/A"

            embed.add_field(
                name="🔬 量化分析",
                value=(
                    f"動量分數：**{momentum_score}** / 100\n"
                    f"信心分數：**{confidence}%**\n"
                    f"衝量狀態：{surge_label}（量比 {vol_ratio:.0f}%）\n"
                    f"布林位置：{boll_label}"
                ),
                inline=False,
            )
            embed.add_field(
                name="📌 量化提示",
                value=(
                    "以上指標基於技術分析規則計算，尚未納入新聞情緒與基本面。\n"
                    "完整分析請使用：**`幫我做完整研究分析 {code}`**（觸發 ResearchLoop）"
                ).format(code=stock_code),
                inline=False,
            )

        # Row 6: 參考連結 (inline=False)
        embed.add_field(
            name="🔗 參考連結",
            value=(
                f"[TWSE](https://www.twse.com.tw/zh/stock/info?stockNo={stock_code}) | "
                f"[Yahoo](https://tw.finance.yahoo.com/quote/{stock_code}.TW) | "
                f"[鉅亨](https://www.cnyes.com/twstock/quote/{stock_code})"
            ),
            inline=False,
        )

        chip_label = f" · 法人資料 {chip_date}" if chip_date and is_real_chip else ""
        embed.set_footer(text=f"更新時間 {datetime.now().strftime('%H:%M')}{chip_label} · TWSE / Yahoo Finance")

        embeds = [embed]

        # ── K-line chart ─────────────────────────────────────────────────
        chart_bytes = None
        if ohlcv:
            try:
                chart_bytes = generate_candlestick_chart(stock_code, ohlcv)
                embeds[0].set_image(url="attachment://chart.png")
            except Exception as e:
                logger.warning(f"[StockTemplate] K-line chart failed: {e}")

        # ── View: refresh + period select ────────────────────────────────
        period_ref = {"period": period}

        async def on_refresh(interaction: discord.Interaction) -> None:
            new_resp = await StockTemplate().build({
                **context, "period": period_ref["period"]
            })
            await _edit_interaction(interaction, new_resp)

        async def on_period_change(interaction: discord.Interaction, new_period: str) -> None:
            period_ref["period"] = new_period
            new_resp = await StockTemplate().build({
                **context, "period": new_period
            })
            await _edit_interaction(interaction, new_resp)

        view = make_stock_view(
            stock_code,
            current_period=period,
            on_refresh=on_refresh,
            on_period_change=on_period_change,
        )

        # Reaction
        reaction = Emoji.STOCK_UP if signal == "buy" else (Emoji.STOCK_DOWN if signal == "sell" else Emoji.STOCK_HOLD)

        return DiscordResponse(
            embeds=embeds,
            chart_bytes=chart_bytes,
            chart_filename="chart.png",
            view=view,
            reactions=[reaction],
        )


# ─── Weather Template ─────────────────────────────────────────────────────────

class WeatherTemplate(DiscordTemplate):
    """
    Weather query template.

    Features:
    - Embed with forecast summary
    - Temperature line chart (if LLM returns chart data)
    - Weather emoji reactions
    """

    async def build(self, context: dict) -> DiscordResponse:
        llm_response = context.get("llm_response", "")
        query = context.get("query", "天氣查詢")

        embed_data, chart_bytes = await self._beautify(
            llm_response,
            title="天氣預報",
            data_context=f"天氣預報數據，用戶查詢：{query}",
        )
        embeds = _dicts_to_embeds(embed_data)
        if chart_bytes and embeds:
            embeds[0].set_image(url="attachment://chart.png")

        # Pick reaction based on keywords in response
        response_lower = llm_response.lower()
        if any(w in response_lower for w in ["颱風", "暴雨", "大雨", "storm"]):
            reaction = Emoji.STORM
        elif any(w in response_lower for w in ["雨", "rain"]):
            reaction = Emoji.RAIN
        elif any(w in response_lower for w in ["陰", "雲", "cloud"]):
            reaction = Emoji.CLOUDY
        else:
            reaction = Emoji.SUNNY

        return DiscordResponse(
            embeds=embeds,
            chart_bytes=chart_bytes,
            reactions=[reaction],
        )


# ─── Report Template ──────────────────────────────────────────────────────────

class ReportTemplate(DiscordTemplate):
    """
    Research / analysis report template.

    Features:
    - Embed with key findings
    - Bar/line chart if data has comparisons or trends
    - 📌 and 💡 reactions
    """

    async def build(self, context: dict) -> DiscordResponse:
        llm_response = context.get("llm_response", "")
        query = context.get("query", "分析報告")

        embed_data, chart_bytes = await self._beautify(
            llm_response,
            title="分析報告",
            data_context=f"研究分析報告，用戶查詢：{query}",
        )
        embeds = _dicts_to_embeds(embed_data)
        if chart_bytes and embeds:
            embeds[0].set_image(url="attachment://chart.png")

        return DiscordResponse(
            embeds=embeds,
            chart_bytes=chart_bytes,
            reactions=[Emoji.REPORT, Emoji.PIN],
        )


# ─── Event Template ───────────────────────────────────────────────────────────

class EventTemplate(DiscordTemplate):
    """
    Calendar / event template.

    Features:
    - Embed with event details
    - ✅ 參加 / ❌ 不參加 RSVP buttons
    - 📅 reaction
    """

    async def build(self, context: dict) -> DiscordResponse:
        llm_response = context.get("llm_response", "")
        query = context.get("query", "活動")

        embed_data, _ = await self._beautify(
            llm_response,
            title="活動 / 行程",
            data_context=f"行事曆活動資訊，用戶查詢：{query}",
        )
        embeds = _dicts_to_embeds(embed_data)

        async def on_accept(interaction: discord.Interaction) -> None:
            await interaction.response.send_message("✅ 已記錄您的出席！", ephemeral=True)

        async def on_decline(interaction: discord.Interaction) -> None:
            await interaction.response.send_message("❌ 已記錄您的缺席。", ephemeral=True)

        view = make_event_view(on_accept=on_accept, on_decline=on_decline)

        return DiscordResponse(
            embeds=embeds,
            view=view,
            reactions=[Emoji.CALENDAR],
        )


# ─── General Template ─────────────────────────────────────────────────────────

class GeneralTemplate(DiscordTemplate):
    """
    Fallback template for any query that doesn't match a specific type.

    Features:
    - Beautified embed
    - Chart if LLM provides chart data
    - No interactive components (simple response)
    """

    async def build(self, context: dict) -> DiscordResponse:
        llm_response = context.get("llm_response", "")
        query = context.get("query", "查詢")

        if not llm_response:
            embed = discord.Embed(
                title="⚠️ 無法取得回應",
                description="目前無法連接 AI 引擎，請稍後再試。\n如問題持續，請確認 gateway 服務是否運行中。",
                color=0xFF6B6B,
            )
            return DiscordResponse(embeds=[embed])

        embed_data, chart_bytes = await self._beautify(
            llm_response,
            title="查詢結果",
            data_context=f"用戶查詢：{query}",
        )
        embeds = _dicts_to_embeds(embed_data)
        if chart_bytes and embeds:
            embeds[0].set_image(url="attachment://chart.png")

        return DiscordResponse(
            embeds=embeds,
            chart_bytes=chart_bytes,
        )


# ─── Screen Template ──────────────────────────────────────────────────────────

class ScreenTemplate(DiscordTemplate):
    """
    Stock screener template — runs stock_screen() and shows top 5 results.

    Triggered by: "推薦標的", "選股", "強勢股", "哪幾檔值得買", etc.
    Shows: header embed + one compact embed per stock (real-time data, no LLM guessing).
    """

    _SIGNAL_EMOJI = {
        "strong_buy": "🔥", "buy": "✅", "hold": "🟡",
        "sell": "🔴", "strong_sell": "🚫",
    }

    async def build(self, context: dict) -> DiscordResponse:
        import asyncio
        from claw.tools.stock_tools import stock_screen

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # stock_screen is sync and blocking — run in thread pool
        try:
            results = await asyncio.to_thread(stock_screen)
        except Exception as e:
            logger.error(f"[ScreenTemplate] stock_screen failed: {e}")
            return DiscordResponse(text=f"選股失敗：{e}")

        top5 = results[:5]
        if not top5:
            embed = discord.Embed(
                title="🔍 選股結果",
                description="今日沒有符合條件的標的（RSI 30-70，買入訊號）。",
                color=0x87898C,
                timestamp=datetime.now(timezone.utc),
            )
            return DiscordResponse(embeds=[embed])

        # ── Header embed ──────────────────────────────────────────────────────
        header = discord.Embed(
            title=f"🔥 今日強勢標的 — {today}",
            description=(
                f"市場掃描完成，以下為符合條件的前 **{len(top5)}** 檔標的\n"
                "篩選條件：RSI 30-70 ｜ 買入訊號 ｜ 成交量 > 1,000萬"
            ),
            color=0x23A559,
            timestamp=datetime.now(timezone.utc),
        )
        for i, r in enumerate(top5, 1):
            sig_emoji = self._SIGNAL_EMOJI.get(getattr(r, "signal", ""), "⬜")
            chg = getattr(r, "change_pct", 0.0)
            arrow = "▲" if chg >= 0 else "▼"
            rsi = r.indicators.rsi_14 if r.indicators.rsi_14 else r.indicators.rsi
            header.add_field(
                name=f"{i}. {sig_emoji} {r.symbol} {r.name}",
                value=(
                    f"現價 **${r.current_price:,.2f}** {arrow}{abs(chg):.2f}%\n"
                    f"RSI {rsi:.1f} ｜ 信號 {getattr(r, 'signal', 'hold')}"
                ),
                inline=True,
            )
        # Pad to multiple of 3 for clean grid layout
        while len(top5) % 3 != 0:
            header.add_field(name="\u200b", value="\u200b", inline=True)

        embeds: list[discord.Embed] = [header]

        # ── Per-stock compact embeds ──────────────────────────────────────────
        for r in top5:
            ind = r.indicators
            sig = getattr(r, "signal", "hold")
            chg = getattr(r, "change_pct", 0.0)
            arrow = "▲" if chg >= 0 else "▼"
            vol_zhang = (getattr(r, "volume", 0) or 0) // 1000

            kd_trend = "金叉▲" if ind.kd_k > ind.kd_d else ("死叉▼" if ind.kd_k < ind.kd_d else "持平")
            rsi14 = ind.rsi_14 if ind.rsi_14 else ind.rsi

            embed = discord.Embed(
                title=f"{self._SIGNAL_EMOJI.get(sig, '⬜')} {r.symbol} {r.name}",
                color=_signal_to_color(sig),
                timestamp=datetime.now(timezone.utc),
            )
            # Row 1: 現價 | 漲跌 | 成交量
            embed.add_field(name="💰 現價", value=f"NT$ {r.current_price:,.2f}", inline=True)
            embed.add_field(name="📈 漲跌", value=f"{arrow} {abs(chg):.2f}%", inline=True)
            embed.add_field(name="📦 成交量", value=f"{vol_zhang:,}張", inline=True)
            # Row 2: RSI | KD | MACD
            macd_trend = "▲ 正面" if ind.macd > ind.macd_signal else "▼ 負面"
            macd_dec = 4 if r.current_price < 100 else 3
            embed.add_field(name="📊 RSI(14)", value=f"{rsi14:.1f}", inline=True)
            embed.add_field(name="📐 KD", value=f"K:{ind.kd_k:.1f} D:{ind.kd_d:.1f} {kd_trend}", inline=True)
            embed.add_field(name="📉 MACD", value=f"DIF:{_fmt(ind.macd, macd_dec)} {macd_trend}", inline=True)
            # Row 3: MA5/MA20 | 布林帶
            embed.add_field(name="📏 MA5/MA20", value=f"{_fmt(ind.ma_5)} / {_fmt(ind.ma_20)}", inline=True)
            embed.add_field(name="🎯 布林上/下", value=f"{_fmt(ind.bollinger_upper)} / {_fmt(ind.bollinger_lower)}", inline=True)
            embed.add_field(name="📋 PE", value=f"{float(r.fundamental.pe_ratio):.2f}x" if r.fundamental.pe_ratio else "N/A", inline=True)
            # Reference links
            embed.add_field(
                name="🔗 參考連結",
                value=(
                    f"[TWSE](https://www.twse.com.tw/zh/stock/info?stockNo={r.symbol}) | "
                    f"[Yahoo](https://tw.finance.yahoo.com/quote/{r.symbol}.TW) | "
                    f"[鉅亨](https://www.cnyes.com/twstock/quote/{r.symbol})"
                ),
                inline=False,
            )
            embeds.append(embed)

        return DiscordResponse(embeds=embeds, reactions=["🔥"])


# ─── Portfolio Template ───────────────────────────────────────────────────────

class PortfolioTemplate(DiscordTemplate):
    """
    Portfolio management template.

    Triggered by: "持倉", "我的股票", "成本", "損益", etc.

    Features:
    - Current holdings with real-time P&L (current price fetched live)
    - ➕ 新增/更新持倉 button → opens PortfolioAddModal
    - 🔄 Refresh button
    - 📌 reaction
    """

    async def build(self, context: dict) -> DiscordResponse:
        from claw.tools.portfolio_manager import PortfolioManager
        from claw.channels.discord_components import make_portfolio_view, Emoji

        pm = PortfolioManager()
        holdings = pm.get_holdings()

        # Fetch current prices in parallel
        prices: dict[str, float] = {}
        if holdings:
            try:
                import asyncio
                from claw.tools.stock_tools import stock_fetch_data

                async def _fetch_price(sym: str) -> tuple[str, float]:
                    try:
                        data = await stock_fetch_data(sym, period="1mo")
                        ohlcv = data.get("ohlcv", [])
                        price = float(ohlcv[-1]["close"]) if ohlcv else 0.0
                        return sym, price
                    except Exception:
                        return sym, 0.0

                results = await asyncio.gather(*[_fetch_price(h["symbol"]) for h in holdings])
                prices = dict(results)
            except Exception as e:
                logger.warning(f"[PortfolioTemplate] Price fetch failed: {e}")

        summary = pm.portfolio_summary(prices)

        # Build embed
        if not summary:
            embed = discord.Embed(
                title="📂 我的持倉",
                description="目前沒有任何持倉紀錄。\n點擊下方 **➕ 新增/更新持倉** 按鈕開始建立。",
                color=0x5865F2,
            )
            embeds = [embed]
        else:
            total_value = sum(r.get("market_value", 0) for r in summary)
            total_gain = sum(r.get("gain_amount", 0) for r in summary)
            gain_color = 0x00B94A if total_gain >= 0 else 0xE03131

            embed = discord.Embed(
                title="📂 我的持倉",
                description=(
                    f"總市值：**NT$ {total_value:,.0f}**　"
                    f"總損益：**{'▲' if total_gain >= 0 else '▼'} NT$ {abs(total_gain):,.0f}**"
                ),
                color=gain_color,
                timestamp=_parse_ts(None) or __import__("datetime").datetime.now(__import__("datetime").timezone.utc),
            )

            for row in summary:
                sym = row["symbol"]
                name = row.get("name", sym)
                shares = row.get("shares", 0)
                cost = row.get("cost_per_share", 0)
                current = row.get("current_price")
                gain_pct = row.get("gain_pct")
                gain_amt = row.get("gain_amount")

                if current is not None:
                    arrow = "▲" if (gain_pct or 0) >= 0 else "▼"
                    value_str = (
                        f"現價 **{current:,.2f}** | 成本 {cost:,.2f}\n"
                        f"{arrow} {abs(gain_pct or 0):.2f}% ({'+' if (gain_amt or 0)>=0 else ''}{gain_amt:,.0f} 元)\n"
                        f"持股 {shares:,} 股"
                    )
                else:
                    value_str = f"成本 {cost:,.2f} | 持股 {shares:,} 股\n*(現價取得失敗)*"

                embed.add_field(name=f"{sym} {name}", value=value_str, inline=False)

            embeds = [embed]

        # View
        async def on_refresh(interaction: discord.Interaction) -> None:
            new_resp = await PortfolioTemplate().build(context)
            await _edit_interaction(interaction, new_resp)

        view = make_portfolio_view(on_refresh=on_refresh)

        return DiscordResponse(
            embeds=embeds,
            view=view,
            reactions=[Emoji.PIN],
        )


# ─── LLM direct call helper ───────────────────────────────────────────────────

async def _call_llm_direct(
    router_url: str,
    model: str,
    prompt: str,
    system: str = "",
    max_tokens: int = 200,
    temperature: float = 0.7,
) -> str:
    """
    Direct call to LLM router (bypasses agent pipeline).
    Used by templates that need a quick LLM opinion without going through gateway.
    Returns empty string on any error.
    """
    import httpx
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{router_url.rstrip('/')}/v1/chat/completions",
                json={"model": model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens},
            )
        if resp.status_code != 200:
            return ""
        data = resp.json()
        content = data["choices"][0]["message"].get("content", "") or ""
        if isinstance(content, list):
            content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
        content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
        return content
    except Exception as e:
        logger.warning(f"[LLM direct] {e}")
        return ""


# ─── Shared signal labels / colors ───────────────────────────────────────────

_SIGNAL_LABEL = {
    "strong_buy": "🔥 強力買進", "buy": "✅ 買進", "hold": "🟡 觀察",
    "sell": "🔴 賣出", "strong_sell": "🚫 強力賣出",
}
_SIGNAL_COLOR = {
    "strong_buy": 0x23A559, "buy": 0x23A559, "hold": 0x5865F2,
    "sell": 0xDA373C, "strong_sell": 0xDA373C,
}


# ─── Single-stock embed builder (shared by StockTemplate & MorningReportTemplate) ─

async def _build_single_stock_embed(
    sym: str,
    tag: str,
    stock_data: dict,
    ohlcv: list[dict],
    chip: dict | None,
    news_list: list[dict],
    context: dict,
) -> tuple[discord.Embed, bytes | None]:
    """
    Build a full StockTemplate-style embed for one stock.
    Returns (embed, chart_bytes_or_None).
    chart filename = attachment://chart_{sym_safe}.png  — caller sets set_image().
    """
    from claw.tools.chart_tools import generate_candlestick_chart

    ind   = stock_data.get("indicators", {})
    fund  = stock_data.get("fundamental", {})
    signal = stock_data.get("signal", "hold")
    stock_name    = stock_data.get("name", sym)
    current_price = float(stock_data.get("current_price", 0))

    # Change % and volume from OHLCV
    change_pct  = 0.0
    volume_zhang = 0
    if len(ohlcv) >= 2:
        prev_close = ohlcv[-2]["close"]
        if prev_close:
            change_pct = (ohlcv[-1]["close"] - prev_close) / prev_close * 100
    if ohlcv:
        volume_zhang = ohlcv[-1]["volume"] // 1000

    # Sentiment-analyze news in-place
    if news_list:
        try:
            from claw.tools.stock_tools import sentiment_analyze
            sentiment_analyze(news_list)
        except Exception:
            pass

    rsi14     = float(ind.get("rsi_14", 0))
    kdk       = float(ind.get("kd_k", 0))
    kdd       = float(ind.get("kd_d", 0))
    macd_v    = float(ind.get("macd", 0))
    macd_sig_v = float(ind.get("macd_signal", 0))

    # AI opinion via Gemma
    _router_url   = context.get("_router_url", "")
    _intent_model = context.get("_intent_model", "")
    description   = ""
    if _router_url and _intent_model:
        news_headlines = "; ".join(
            n.get("title", "")[:40] for n in (news_list or [])[:3] if n.get("title")
        ) or "無"
        chip_summary = (
            f"外資 {chip.get('net_foreign', 0):+,}張 / 投信 {chip.get('net_trust', 0):+,}張"
            if chip and chip.get("source") not in ("mock", "", None)
            else "法人資料暫無"
        )
        opinion_prompt = (
            f"股票：{sym} {stock_name}  現價：{current_price:.2f}  "
            f"漲跌：{change_pct:+.2f}%  成交量：{volume_zhang:,}張\n"
            f"技術訊號：{signal}  RSI:{rsi14:.1f}  KD K/D:{kdk:.1f}/{kdd:.1f}  "
            f"MACD DIF/Signal:{macd_v:.4f}/{macd_sig_v:.4f}\n"
            f"法人籌碼：{chip_summary}\n"
            f"最新新聞：{news_headlines}\n\n"
            "請用繁體中文，60 字以內，給出：①買賣建議（買進/賣出/觀察）②主要理由 ③主要風險。"
        )
        description = await _call_llm_direct(
            _router_url, _intent_model, opinion_prompt,
            system="你是專業台股 AI 分析師，根據技術指標、籌碼和新聞給出簡潔買賣建議。",
            max_tokens=120, temperature=0.5,
        )

    if not description:
        _signal_text = {
            "strong_buy": "技術強勢，多指標共振偏多",
            "buy": "技術偏多，具買進潛力",
            "hold": "技術中性，建議觀察",
            "sell": "技術偏空，留意風險",
            "strong_sell": "技術弱勢，多指標轉空",
        }
        desc_parts = [_signal_text.get(signal, "技術中性")]
        if kdk > kdd:             desc_parts.append("KD 金叉")
        elif kdk < kdd:           desc_parts.append("KD 死叉")
        if macd_v > macd_sig_v:   desc_parts.append("MACD 偏多")
        elif macd_v < macd_sig_v: desc_parts.append("MACD 偏空")
        if rsi14 < 30:  desc_parts.append("RSI 超賣區")
        elif rsi14 > 70: desc_parts.append("RSI 超買區")
        description = "，".join(desc_parts) + "。"

    safe_sym = sym.replace(".", "_")
    chart_filename = f"chart_{safe_sym}.png"

    embed = discord.Embed(
        title=f"{tag} {_SIGNAL_LABEL.get(signal, '🟡 觀察')}  {sym} {stock_name}",
        description=description,
        color=_signal_to_color(signal),
        timestamp=datetime.now(timezone.utc),
    )

    # Row 1: 現價 | 漲跌 | 成交量
    arrow = "▲" if change_pct >= 0 else "▼"
    embed.add_field(name="💰 現價",   value=f"NT$ {current_price:,.2f}", inline=True)
    embed.add_field(name="📈 漲跌",   value=f"{arrow} {abs(change_pct):.2f}%", inline=True)
    embed.add_field(name="📦 成交量", value=f"{volume_zhang:,}張", inline=True)

    # Row 2: RSI | KD | MACD
    kd_trend   = "金叉▲" if kdk > kdd else ("死叉▼" if kdk < kdd else "持平")
    macd_trend = "▲ 正面" if macd_v > macd_sig_v else "▼ 負面"
    macd_dec   = 4 if current_price < 100 else 3
    embed.add_field(name="📊 RSI(14)", value=f"{rsi14:.1f}", inline=True)
    embed.add_field(name="📐 KD",      value=f"K:{kdk:.1f} D:{kdd:.1f} {kd_trend}", inline=True)
    embed.add_field(name="📉 MACD",    value=f"DIF:{_fmt(macd_v, macd_dec)} {macd_trend}", inline=True)

    # Row 3: 外資 | 投信 | 本益比
    net_f = chip.get("net_foreign", 0) if chip else 0
    net_t = chip.get("net_trust", 0) if chip else 0
    is_real_chip = chip and chip.get("source") not in ("mock", "")
    if not is_real_chip:
        f_val = t_val = "—"
    else:
        f_val = ("買超▲" if net_f > 0 else ("賣超▼" if net_f < 0 else "持平")) + f" {abs(net_f):,}張"
        t_val = ("買超▲" if net_t > 0 else ("賣超▼" if net_t < 0 else "持平")) + f" {abs(net_t):,}張"
    try:
        pe_val = f"{float(fund.get('pe_ratio')):,.2f}x" if fund.get("pe_ratio") else "N/A"
    except (TypeError, ValueError):
        pe_val = "N/A"
    embed.add_field(name="🏦 外資",   value=f_val, inline=True)
    embed.add_field(name="📊 投信",   value=t_val, inline=True)
    embed.add_field(name="📋 本益比", value=pe_val, inline=True)

    # News with sentiment
    if news_list:
        _sent_emoji = {"positive": "🟢 正面", "negative": "🔴 負面", "neutral": "⚪ 中立"}
        news_lines = []
        for n in news_list[:3]:
            if not n.get("title"):
                continue
            title_txt = n["title"][:32] + ("…" if len(n["title"]) > 32 else "")
            url    = n.get("url", "")
            source = n.get("source", "")
            date   = (n.get("publish_date") or "")[:10]
            sent   = _sent_emoji.get(n.get("sentiment", "neutral"), "⚪ 中立")
            headline = f"[{title_txt}]({url})" if url else title_txt
            meta = " ｜ ".join(x for x in [source, date, sent] if x)
            news_lines.append(f"{headline}\n{meta}" if meta else headline)
        if news_lines:
            embed.add_field(name="📰 相關新聞", value="\n\n".join(news_lines), inline=False)

    embed.add_field(
        name="🔗 參考連結",
        value=(
            f"[TWSE](https://www.twse.com.tw/zh/stock/info?stockNo={sym}) | "
            f"[Yahoo](https://tw.finance.yahoo.com/quote/{sym}.TW) | "
            f"[鉅亨](https://www.cnyes.com/twstock/quote/{sym})"
        ),
        inline=False,
    )
    embed.set_footer(text=f"更新時間 {datetime.now().strftime('%H:%M')} · TWSE / Yahoo Finance")

    # K-line chart
    chart_bytes: bytes | None = None
    if ohlcv:
        try:
            chart_bytes = generate_candlestick_chart(sym, ohlcv)
            embed.set_image(url=f"attachment://{chart_filename}")
        except Exception as e:
            logger.warning(f"[MorningReport] K-line chart failed for {sym}: {e}")

    return embed, chart_bytes


# ─── Morning Report Template ──────────────────────────────────────────────────


def _build_report_embeds(top5: list[dict], title: str, subtitle: str, prices: dict | None = None) -> list[discord.Embed]:
    """Build header + per-stock embeds from watchlist top5 records."""
    buy_count = sum(1 for r in top5 if r.get("signal") in ("buy", "strong_buy"))
    sell_count = sum(1 for r in top5 if r.get("signal") in ("sell", "strong_sell"))
    mood = "多方偏強 🟢" if buy_count >= 3 else ("空方偏強 🔴" if sell_count >= 3 else "市場觀望 🟡")

    header = discord.Embed(
        title=title,
        description=f"**市場情緒：{mood}**\n{subtitle}",
        color=0x23A559 if buy_count >= 3 else (0xDA373C if sell_count >= 3 else 0x5865F2),
        timestamp=datetime.now(timezone.utc),
    )
    embeds = [header]

    for r in top5:
        sym = r.get("symbol", "")
        name = r.get("name", sym)
        signal = r.get("signal", "hold")
        rsi = float(r.get("rsi", 0))
        summary = r.get("summary", "")
        price = (prices or {}).get(sym)

        e = discord.Embed(
            title=f"{_SIGNAL_LABEL.get(signal, '🟡 觀察')}  {sym} {name}",
            description=summary or f"RSI {rsi:.1f}，訊號：{signal}",
            color=_SIGNAL_COLOR.get(signal, 0x5865F2),
        )
        if price:
            e.add_field(name="現價", value=f"NT$ {price:,.2f}", inline=True)
        e.add_field(name="RSI(14)", value=f"{rsi:.1f}", inline=True)
        e.add_field(
            name="🔗",
            value=f"[Yahoo](https://tw.finance.yahoo.com/quote/{sym}.TW) ｜ [鉅亨](https://www.cnyes.com/twstock/quote/{sym})",
            inline=True,
        )
        embeds.append(e)

    if not top5:
        header.description = (header.description or "") + "\n今日沒有符合條件的標的，市場可能偏向觀望。"

    return embeds


# Fallback pool when stock_screen doesn't return enough non-holding picks
_MORNING_FALLBACK_POOL = [
    "0050", "0056", "006208", "00878", "00919", "00929",  # ETFs
    "2330", "2454", "2317", "2412", "3008",               # Tech blue chips
    "1301", "1303", "2002", "2882", "2881", "2308",        # Blue chips
]


class MorningReportTemplate(DiscordTemplate):
    """
    On-demand morning report.
    - Holdings: compact status in header only (not full cards)
    - New picks: exactly 5 stocks DISJOINT from holdings (互斥), full cards
    - Supplemented from fallback pool if stock_screen < 5 non-holding results
    """

    async def build(self, context: dict) -> DiscordResponse:
        import asyncio
        import json as _j
        from claw.tools.portfolio_manager import PortfolioManager
        from claw.tools.stock_tools import stock_screen, stock_analyze, stock_fetch, stock_chip, stock_news

        pm = PortfolioManager()
        today = datetime.now().strftime("%Y-%m-%d")

        holdings = pm.get_holdings()
        holding_syms = {h["symbol"] for h in holdings}

        # ── Helper: fetch full data for one stock ─────────────────────────────
        async def _fetch_full(sym: str, is_holding: bool) -> dict:
            try:
                stock_data_raw, ohlcv_raw, chip, news_list = await asyncio.gather(
                    stock_analyze(sym),
                    stock_fetch(sym, period="1mo"),
                    asyncio.to_thread(stock_chip, sym),
                    asyncio.to_thread(stock_news, sym, 3),
                )
                stock_data = _j.loads(stock_data_raw) if isinstance(stock_data_raw, str) else stock_data_raw
                ohlcv_raw2 = _j.loads(ohlcv_raw) if isinstance(ohlcv_raw, str) else ohlcv_raw
                ohlcv = [
                    {
                        "date":   item.get("Date", item.get("date", "")).split("T")[0],
                        "open":   float(item.get("Open",   item.get("open",   0))),
                        "high":   float(item.get("High",   item.get("high",   0))),
                        "low":    float(item.get("Low",    item.get("low",    0))),
                        "close":  float(item.get("Close",  item.get("close",  0))),
                        "volume": int(item.get("Volume",  item.get("volume",  0))),
                    }
                    for item in (ohlcv_raw2 if isinstance(ohlcv_raw2, list) else [])
                ]
                return {
                    "symbol": sym, "stock_data": stock_data,
                    "ohlcv": ohlcv, "chip": chip or {}, "news_list": news_list or [],
                    "_holding": is_holding,
                }
            except Exception as e:
                logger.warning(f"[MorningReport] _fetch_full({sym}) failed: {e}")
                return {
                    "symbol": sym,
                    "stock_data": {"name": sym, "signal": "hold", "indicators": {}, "fundamental": {}, "current_price": 0},
                    "ohlcv": [], "chip": {}, "news_list": [],
                    "_holding": is_holding,
                }

        # ── 1. Holdings analysis + stock_screen in parallel ───────────────────
        async def _screen() -> list:
            try:
                return await asyncio.to_thread(stock_screen) or []
            except Exception as e:
                logger.warning(f"[MorningReport] stock_screen failed: {e}")
                return []

        holding_tasks = [_fetch_full(h["symbol"], True) for h in holdings]

        async def _gather_holdings() -> list:
            if not holding_tasks:
                return []
            return list(await asyncio.gather(*holding_tasks))

        holding_results_raw, screen_raw = await asyncio.gather(
            _gather_holdings(),
            _screen(),
        )
        holding_results: list[dict] = list(holding_results_raw)

        # ── 2. Pick exactly 5 new picks DISJOINT from holdings (互斥) ────────
        seen: set[str] = set(holding_syms)
        new_syms: list[str] = []

        # First pass: from stock_screen (strong signals)
        for r in screen_raw:
            sym = r.get("symbol", "") if isinstance(r, dict) else getattr(r, "symbol", "")
            if sym and sym not in seen:
                new_syms.append(sym)
                seen.add(sym)
            if len(new_syms) >= 5:
                break

        # Second pass: supplement from fallback pool if still < 5
        if len(new_syms) < 5:
            for sym in _MORNING_FALLBACK_POOL:
                if sym not in seen:
                    new_syms.append(sym)
                    seen.add(sym)
                if len(new_syms) >= 5:
                    break

        logger.info(f"[MorningReport] new picks: {new_syms}")

        new_pick_results: list[dict] = list(
            await asyncio.gather(*[_fetch_full(s, False) for s in new_syms])
        ) if new_syms else []

        # Cache new picks for weekly report
        cache_records = [
            {
                "symbol": r["symbol"],
                "name":   r["stock_data"].get("name", r["symbol"]),
                "signal": r["stock_data"].get("signal", "hold"),
                "rsi":    round(float((r["stock_data"].get("indicators") or {}).get("rsi_14") or 50), 1),
            }
            for r in new_pick_results
        ]
        if cache_records:
            try:
                pm.save_watchlist_entry(today, cache_records)
            except Exception:
                pass

        # ── 3. Header embed: market mood + compact holdings status ────────────
        new_buy = sum(1 for r in new_pick_results if r["stock_data"].get("signal") in ("buy", "strong_buy"))
        new_sell = sum(1 for r in new_pick_results if r["stock_data"].get("signal") in ("sell", "strong_sell"))
        mood = "多方偏強 🟢" if new_buy > new_sell + 1 else ("空方偏強 🔴" if new_sell > new_buy + 1 else "市場觀望 🟡")

        # Compact new picks list for header
        pick_tags = " / ".join(
            f"{_SIGNAL_LABEL.get(r['stock_data'].get('signal','hold'), '🟡')} {r['symbol']}"
            for r in new_pick_results
        )

        header = discord.Embed(
            title=f"🌅 {today} 台股日報",
            description=(
                f"**市場情緒：{mood}**\n"
                f"今日推薦：{pick_tags or '—'}\n"
                f"篩選條件：RSI 30-70 ｜ 技術偏多訊號 ｜ 排除持倉"
            ),
            color=0x23A559 if new_buy > new_sell else (0xDA373C if new_sell > new_buy else 0x5865F2),
            timestamp=datetime.now(timezone.utc),
        )

        # Holdings compact status in header fields
        for r in holding_results:
            sym  = r["symbol"]
            name = r["stock_data"].get("name", sym)
            sig  = r["stock_data"].get("signal", "hold")
            ind  = r["stock_data"].get("indicators", {})
            rsi  = float(ind.get("rsi_14") or ind.get("rsi") or 0)
            price = float(r["stock_data"].get("current_price", 0))
            arrow  = "▲" if sig in ("buy", "strong_buy") else ("▼" if sig in ("sell", "strong_sell") else "—")
            header.add_field(
                name=f"📦 {sym} {name}",
                value=f"{_SIGNAL_LABEL.get(sig, '🟡 觀察')}\n現價 {price:,.2f} ｜ RSI {rsi:.1f}",
                inline=True,
            )

        if not new_pick_results:
            header.description = (header.description or "") + "\n\n❌ 無法取得推薦資料，請稍後再試。"
            return DiscordResponse(embeds=[header], reactions=["🌅"])

        # ── 4. Full cards for new picks (Discord limit: 10 total, 1 header + 9) ──
        async def _build_embed_task(r: dict) -> tuple[discord.Embed, bytes | None]:
            return await _build_single_stock_embed(
                sym=r["symbol"], tag="🆕",
                stock_data=r["stock_data"], ohlcv=r["ohlcv"],
                chip=r["chip"], news_list=r["news_list"],
                context=context,
            )

        embed_results_raw = await asyncio.gather(
            *[_build_embed_task(r) for r in new_pick_results[:9]],
            return_exceptions=True,
        )

        embeds: list[discord.Embed] = [header]
        chart_files: list[discord.File] = []
        for r, result in zip(new_pick_results[:9], embed_results_raw):
            if isinstance(result, BaseException):
                logger.warning(f"[MorningReport] embed failed for {r['symbol']}: {result}")
                embeds.append(discord.Embed(
                    title=f"⚠️ {r['symbol']} 資料載入失敗",
                    description="暫時無法取得此股票資料，請稍後重試。",
                    color=0x87898C,
                ))
                continue
            emb, chart_bytes = result
            embeds.append(emb)
            if chart_bytes:
                safe_sym = r["symbol"].replace(".", "_")
                chart_files.append(
                    discord.File(io.BytesIO(chart_bytes), filename=f"chart_{safe_sym}.png")
                )

        return DiscordResponse(embeds=embeds, extra_files=chart_files, reactions=["🌅"])


class WeeklyReportTemplate(DiscordTemplate):
    """
    On-demand weekly report — shows last 7 days of top5 picks from watchlist cache.
    """

    async def build(self, context: dict) -> DiscordResponse:
        from claw.tools.portfolio_manager import PortfolioManager

        pm = PortfolioManager()
        history = pm.get_watchlist_history(7)

        if not history:
            return DiscordResponse(embeds=[discord.Embed(
                title="📊 台股週報",
                description="尚無週報資料。週報排程為 **每週五 18:00** 自動推送。",
                color=0x87898C,
                timestamp=datetime.now(timezone.utc),
            )])

        # Summary embed
        date_range = f"{history[-1]['date']} ~ {history[0]['date']}" if len(history) > 1 else history[0]["date"]
        all_stocks: dict[str, dict] = {}
        for entry in history:
            for r in entry.get("top5", []):
                sym = r.get("symbol", "")
                if sym not in all_stocks:
                    all_stocks[sym] = {**r, "appearances": 0}
                all_stocks[sym]["appearances"] += 1

        # Sort by appearance count desc
        ranked = sorted(all_stocks.values(), key=lambda x: x["appearances"], reverse=True)

        header = discord.Embed(
            title=f"📊 台股週報 {date_range}",
            description=(
                f"本週共掃描 **{len(history)} 天**，彙整每日強勢標的出現頻率\n"
                f"出現次數越多代表持續強勢，值得重點關注"
            ),
            color=0xF0B232,
            timestamp=datetime.now(timezone.utc),
        )
        embeds = [header]

        for r in ranked[:5]:
            sym = r.get("symbol", "")
            name = r.get("name", sym)
            signal = r.get("signal", "hold")
            rsi = float(r.get("rsi", 0))
            appearances = r.get("appearances", 1)
            stars = "⭐" * min(appearances, 5)

            e = discord.Embed(
                title=f"{_SIGNAL_LABEL.get(signal, '🟡 觀察')}  {sym} {name}",
                description=f"{stars} 本週出現 **{appearances}/{len(history)} 天**",
                color=_SIGNAL_COLOR.get(signal, 0x5865F2),
            )
            e.add_field(name="RSI(14)", value=f"{rsi:.1f}", inline=True)
            e.add_field(name="訊號", value=_SIGNAL_LABEL.get(signal, "觀察"), inline=True)
            e.add_field(
                name="🔗",
                value=f"[Yahoo](https://tw.finance.yahoo.com/quote/{sym}.TW) ｜ [鉅亨](https://www.cnyes.com/twstock/quote/{sym})",
                inline=True,
            )
            embeds.append(e)

        # Per-day summary
        days_embed = discord.Embed(title="📅 本週每日強勢股", color=0xF0B232)
        for entry in history[:5]:
            date = entry.get("date", "")
            syms = " / ".join(r.get("symbol", "") for r in entry.get("top5", []))
            days_embed.add_field(name=date, value=syms or "無資料", inline=False)
        embeds.append(days_embed)

        return DiscordResponse(embeds=embeds, reactions=["📊"])


# ─── Template Registry ────────────────────────────────────────────────────────

from claw.channels.discord_formatter import ResponseType  # noqa: E402

_REGISTRY: dict[ResponseType, type[DiscordTemplate]] = {
    ResponseType.STOCK:          StockTemplate,
    ResponseType.SCREEN:         ScreenTemplate,
    ResponseType.WEATHER:        WeatherTemplate,
    ResponseType.REPORT:         ReportTemplate,
    ResponseType.EVENT:          EventTemplate,
    ResponseType.PORTFOLIO:      PortfolioTemplate,
    ResponseType.MORNING_REPORT: MorningReportTemplate,
    ResponseType.WEEKLY_REPORT:  WeeklyReportTemplate,
    ResponseType.GENERAL:        GeneralTemplate,
}


def get_template(response_type: ResponseType) -> DiscordTemplate:
    """Instantiate and return the correct template for the given ResponseType."""
    cls = _REGISTRY.get(response_type, GeneralTemplate)
    return cls()


# ─── Interaction edit helper ─────────────────────────────────────────────────

async def _edit_interaction(
    interaction: discord.Interaction,
    response: DiscordResponse,
) -> None:
    """Edit an interaction's original message with a new DiscordResponse."""
    try:
        kwargs: dict = {}

        if response.embeds:
            kwargs["embeds"] = response.embeds[:10]
        elif response.text:
            # Fallback: wrap plain text in a simple embed so edit always has content
            kwargs["embeds"] = [discord.Embed(description=response.text[:2000], color=0xAAAAAA)]

        if response.view:
            kwargs["view"] = response.view

        if response.chart_bytes:
            # files= for new uploads; attachments=[] would clear existing files
            fname = response.chart_filename or "chart.png"
            kwargs["files"] = [discord.File(io.BytesIO(response.chart_bytes), filename=fname)]
            kwargs["attachments"] = []   # clear old attachment slot so new one replaces it
        else:
            kwargs["attachments"] = []   # clear previous chart if not regenerated

        if kwargs:
            await interaction.edit_original_response(**kwargs)
    except Exception as e:
        logger.error(f"Failed to edit interaction message: {e}")
        try:
            await interaction.followup.send(f"更新失敗: {e}", ephemeral=True)
        except Exception:
            pass
