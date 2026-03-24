from __future__ import annotations

import logging
import asyncio
import io
import re
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

from claw.channels.discord_formatter import DiscordFormatter
from claw.channels.discord_templates import get_template

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


_INTENT_SYSTEM = """\
You are an intent classifier for a Taiwan stock-assistant Discord bot.
Given a user query, output ONLY a JSON object. No explanation, no markdown fences.

Schema: {"type": "<type>", "code": "<4-digit code or null>"}

Types:
- stock          → asking about a specific stock/company (e.g., "查0050", "台積電多少錢", "0056怎麼了")
- screen         → asking for stock recommendations/screener (e.g., "推薦幾檔", "今天強勢股", "選股")
- portfolio      → own holdings (e.g., "我的持倉", "我買了多少")
- morning_report → asking for today's daily stock market report (e.g., "日報", "晨報", "今天股市", "股價日報", "今天的報告")
- weather        → weather queries
- report         → in-depth analysis, market trends, research
- event          → calendar, schedule, meetings
- general        → everything else (chat, status, general questions)

Examples:
User: 查0050          → {"type":"stock","code":"0050"}
User: 台積電今天多少    → {"type":"stock","code":"2330"}
User: 推薦幾檔好股票    → {"type":"screen","code":null}
User: 日報             → {"type":"morning_report","code":null}
User: 今天的股價日報    → {"type":"morning_report","code":null}
User: 今天股市怎樣      → {"type":"morning_report","code":null}
User: 今天天氣          → {"type":"weather","code":null}
User: 你好             → {"type":"general","code":null}
"""


# ── Portfolio helpers ─────────────────────────────────────────────────────────

async def _fetch_portfolio_prices(holdings: list) -> list[float]:
    """Batch-fetch current prices via yfinance (one API call, non-blocking)."""
    import yfinance as yf
    symbols = [h["symbol"] for h in holdings]
    tickers = [f"{s}.TW" for s in symbols]
    try:
        loop = asyncio.get_event_loop()
        df = await loop.run_in_executor(
            None,
            lambda: yf.download(
                tickers if len(tickers) > 1 else tickers[0],
                period="2d", group_by="ticker", progress=False, auto_adjust=True,
            ),
        )
        prices = []
        for h, ticker in zip(holdings, tickers):
            try:
                col = df[ticker]["Close"] if len(tickers) > 1 else df["Close"]
                prices.append(float(col.dropna().iloc[-1]))
            except Exception:
                prices.append(float(h["cost_per_share"]))
        return prices
    except Exception as e:
        logger.warning(f"Batch price fetch failed: {e}")
        return [float(h["cost_per_share"]) for h in holdings]

def _build_portfolio_embed(holdings: list, prices: list) -> discord.Embed:
    total_cost = total_value = 0.0
    fields = []
    for h, price in zip(holdings, prices):
        shares = h.get("shares", 0)
        lots = shares / 1000
        cost = h["cost_per_share"]
        pnl = (price - cost) * shares
        pnl_pct = (price - cost) / cost * 100 if cost else 0
        arrow = "▲" if pnl >= 0 else "▼"
        total_cost += cost * shares
        total_value += price * shares
        fields.append((
            f"{h['symbol']} {h.get('name', '')}",
            f"現價 **{price:.2f}** ｜ 成本 {cost:.2f}\n"
            f"{arrow} {abs(pnl_pct):.1f}%（NT${'+' if pnl >= 0 else '-'}{abs(pnl):,.0f}）　"
            f"持股 {lots:.1f}張 / {shares}股",
        ))
    overall_pnl = total_value - total_cost
    overall_pct = overall_pnl / total_cost * 100 if total_cost else 0
    embed = discord.Embed(
        title="📂 我的持倉",
        description=(
            f"總市值：**NT$ {total_value:,.0f}**　"
            f"總損益：{'▲' if overall_pnl >= 0 else '▼'} NT$ {abs(overall_pnl):,.0f}"
            f"（{overall_pct:+.1f}%）"
        ),
        color=0x23A559 if overall_pnl >= 0 else 0xDA373C,
        timestamp=datetime.now(timezone.utc),
    )
    for name, value in fields:
        embed.add_field(name=name, value=value, inline=False)
    return embed


class _PortfolioView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=600)

    @discord.ui.button(label="🔄 刷新", style=discord.ButtonStyle.secondary)
    async def refresh(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Step 1: immediately respond (<3s) with loading state to satisfy Discord
        loading = discord.Embed(title="📂 我的持倉", description="⏳ 更新中...", color=0x87898C)
        await interaction.response.edit_message(embed=loading, view=self)
        # Step 2: fetch data (can take as long as needed)
        from claw.tools.portfolio_manager import PortfolioManager
        try:
            pm = PortfolioManager()
            holdings = pm.get_holdings()
            if not holdings:
                await interaction.message.edit(
                    embed=discord.Embed(title="📂 目前持倉", description="尚未設定任何持倉。", color=0x87898C),
                    view=None,
                )
                return
            prices = await _fetch_portfolio_prices(holdings)
            await interaction.message.edit(
                embed=_build_portfolio_embed(holdings, prices),
                view=_PortfolioView(),
            )
        except Exception as e:
            logger.error(f"[Portfolio refresh] {e}", exc_info=True)
            await interaction.message.edit(
                embed=discord.Embed(title="❌ 刷新失敗", description=str(e), color=0xDA373C),
                view=self,
            )


# ──────────────────────────────────────────────────────────────────────────────

class DiscordChannel:
    def __init__(
        self,
        token: str,
        base_url: str,
        router_url: str = "http://localhost:8000",
        intent_model: str = "gemma",
    ):
        """
        Args:
            token: Discord bot token
            base_url: Base URL of gateway (e.g., "http://localhost:18790")
            router_url: LLM router URL for direct (non-agent) calls
            intent_model: Fast model used for intent pre-classification
        """
        self.token = token
        self.base_url = base_url
        self._router_url = router_url.rstrip("/")
        self._intent_model = intent_model
        self.intents = discord.Intents.default()
        self.intents.message_content = True  # Read message content
        self.bot = commands.Bot(command_prefix="!", intents=self.intents)
        self._session_clients: dict[str, discord.abc.Messageable] = {}
        self._formatter = DiscordFormatter()

        # Register event handlers
        @self.bot.event
        async def on_ready():
            logger.info(f"Discord bot logged in as {self.bot.user}")
            try:
                await self.bot.tree.sync()
                logger.info("[Discord] Slash commands synced")
            except Exception as e:
                logger.warning(f"[Discord] Slash command sync failed: {e}")

        @self.bot.event
        async def on_message(message: discord.Message):
            # Ignore bot's own messages
            if message.author == self.bot.user:
                return
            await self._handle_message(message)

        # ── Portfolio slash commands ───────────────────────────────────────────

        @self.bot.tree.command(name="持倉", description="查看目前所有持倉與損益")
        async def cmd_portfolio(interaction: discord.Interaction) -> None:
            await interaction.response.defer()
            from claw.tools.portfolio_manager import PortfolioManager
            pm = PortfolioManager()
            holdings = pm.get_holdings()
            if not holdings:
                await interaction.followup.send(embed=discord.Embed(
                    title="📂 目前持倉",
                    description="尚未設定任何持倉。\n使用 `/加倉` 指令新增。",
                    color=0x87898C,
                ))
                return
            prices = await _fetch_portfolio_prices(holdings)
            await interaction.followup.send(
                embed=_build_portfolio_embed(holdings, prices),
                view=_PortfolioView(),
            )

        @self.bot.tree.command(name="加倉", description="新增或更新一筆持倉")
        async def cmd_add_position(interaction: discord.Interaction) -> None:
            class _AddModal(discord.ui.Modal, title="新增持倉"):
                code = discord.ui.TextInput(label="股票代碼", placeholder="例：0050", min_length=4, max_length=6)
                lots = discord.ui.TextInput(label="張數（1張=1000股）", placeholder="例：10", min_length=1, max_length=8)
                cost = discord.ui.TextInput(label="成本（元/股）", placeholder="例：57.5", min_length=1, max_length=10)
                note = discord.ui.TextInput(label="備註（可空白）", placeholder="例：長期持有", required=False, max_length=50)

                async def on_submit(self, inter: discord.Interaction) -> None:
                    from claw.tools.portfolio_manager import PortfolioManager
                    try:
                        pm = PortfolioManager()
                        sym = self.code.value.strip().upper()
                        shares = int(float(self.lots.value) * 1000)
                        cost_val = float(self.cost.value)
                        pm.add_holding(symbol=sym, shares=shares, cost_per_share=cost_val, note=self.note.value or "")
                        await inter.response.send_message(embed=discord.Embed(
                            title="✅ 持倉已新增",
                            description=(
                                f"**{sym}**  {float(self.lots.value):.1f}張 ｜ 成本 NT${cost_val:.2f}\n"
                                f"使用 `/持倉` 查看完整損益。"
                            ),
                            color=0x23A559,
                        ))
                    except Exception as exc:
                        await inter.response.send_message(f"❌ 錯誤：{exc}", ephemeral=True)

                async def on_error(self, inter: discord.Interaction, error: Exception) -> None:
                    await inter.response.send_message(f"❌ 輸入錯誤：{error}", ephemeral=True)

            await interaction.response.send_modal(_AddModal())

        @self.bot.tree.command(name="賣出", description="記錄賣出並更新持倉（支援部分賣出）")
        async def cmd_sell(interaction: discord.Interaction) -> None:
            class _SellModal(discord.ui.Modal, title="記錄賣出"):
                code = discord.ui.TextInput(label="股票代碼", placeholder="例：0050", min_length=4, max_length=6)
                sell_lots = discord.ui.TextInput(label="賣出張數（填 0 = 全部賣出）", placeholder="例：5", min_length=1, max_length=8)
                sell_price = discord.ui.TextInput(label="賣出價格（元/股）", placeholder="例：62.5", min_length=1, max_length=10)

                async def on_submit(self, inter: discord.Interaction) -> None:
                    from claw.tools.portfolio_manager import PortfolioManager
                    try:
                        pm = PortfolioManager()
                        sym = self.code.value.strip().upper()
                        price_sold = float(self.sell_price.value)
                        lots_sold = float(self.sell_lots.value)
                        holdings = pm.get_holdings()
                        h = next((x for x in holdings if x["symbol"] == sym), None)
                        if not h:
                            await inter.response.send_message(f"❌ 找不到 **{sym}** 的持倉。", ephemeral=True)
                            return
                        cost = h["cost_per_share"]
                        shares_held = h.get("shares", 0)
                        lots_held = shares_held / 1000
                        if lots_sold == 0 or lots_sold >= lots_held:
                            realized_pnl = (price_sold - cost) * shares_held
                            pm.remove_holding(sym)
                            desc = (
                                f"**{sym}** 全部賣出 {lots_held:.1f}張 @ NT${price_sold:.2f}\n"
                                f"實現損益：{'▲' if realized_pnl >= 0 else '▼'} NT${abs(realized_pnl):,.0f}"
                            )
                        else:
                            shares_sold = int(lots_sold * 1000)
                            realized_pnl = (price_sold - cost) * shares_sold
                            pm.update_holding(sym, shares=shares_held - shares_sold)
                            desc = (
                                f"**{sym}** 賣出 {lots_sold:.1f}張 @ NT${price_sold:.2f}"
                                f"，剩餘 {(shares_held - shares_sold) / 1000:.1f}張\n"
                                f"實現損益：{'▲' if realized_pnl >= 0 else '▼'} NT${abs(realized_pnl):,.0f}"
                            )
                        await inter.response.send_message(embed=discord.Embed(
                            title="✅ 賣出記錄完成",
                            description=desc,
                            color=0x23A559 if realized_pnl >= 0 else 0xDA373C,
                        ))
                    except Exception as exc:
                        await inter.response.send_message(f"❌ 錯誤：{exc}", ephemeral=True)

                async def on_error(self, inter: discord.Interaction, error: Exception) -> None:
                    await inter.response.send_message(f"❌ 輸入錯誤：{error}", ephemeral=True)

            await interaction.response.send_modal(_SellModal())

        @self.bot.tree.command(name="刪倉", description="直接刪除一筆持倉（無損益記錄）")
        async def cmd_remove_position(interaction: discord.Interaction, code: str) -> None:
            from claw.tools.portfolio_manager import PortfolioManager
            pm = PortfolioManager()
            ok = pm.remove_holding(code.upper())
            msg = (f"**{code.upper()}** 已從持倉清單移除。" if ok
                   else f"❌ 找不到持倉 **{code.upper()}**，請確認代碼是否正確。")
            await interaction.response.send_message(embed=discord.Embed(
                title="🗑 持倉已刪除" if ok else "❌ 找不到持倉",
                description=msg,
                color=0xDA373C,
            ))

    async def start(self) -> None:
        """Start the Discord bot and Discord-specific push schedulers."""
        logger.info("Starting Discord channel")
        asyncio.create_task(self.bot.start(self.token))
        await self.bot.wait_until_ready()
        self._start_discord_scheduler()
        logger.info("Discord channel started successfully")

    def _start_discord_scheduler(self) -> None:
        """APScheduler for jobs that need to push to Discord (inject self)."""
        try:
            from apscheduler.schedulers.asyncio import AsyncIOScheduler
            from claw.cron.jobs.morning_report import morning_report_job
            from claw.cron.jobs.weekly_report import weekly_report_job
            from claw.cron.jobs.portfolio_alert import portfolio_alert_job
            from claw.cron.jobs.volume_alert import volume_alert_job

            sched = AsyncIOScheduler(timezone="Asia/Taipei")

            # 08:00 weekdays — morning stock report
            sched.add_job(
                morning_report_job, "cron", day_of_week="mon-fri", hour=8, minute=0,
                kwargs={"discord_channel": self},
                id="discord:morning_report", replace_existing=True,
            )
            # 18:00 Friday — weekly strategy report
            sched.add_job(
                weekly_report_job, "cron", day_of_week="fri", hour=18, minute=0,
                kwargs={"discord_channel": self},
                id="discord:weekly_report", replace_existing=True,
            )
            # 09:30 weekdays — portfolio alert (after market open)
            sched.add_job(
                portfolio_alert_job, "cron", day_of_week="mon-fri", hour=9, minute=30,
                kwargs={"storage": None, "llm": None, "cron_data": None, "discord_channel": self},
                id="discord:portfolio_alert", replace_existing=True,
            )
            # 17:30 weekdays — after-market volume surge alert
            sched.add_job(
                volume_alert_job, "cron", day_of_week="mon-fri", hour=17, minute=30,
                kwargs={"discord_channel": self},
                id="discord:volume_alert", replace_existing=True,
            )

            sched.start()
            self._discord_scheduler = sched
            logger.info("Discord push scheduler started: morning(08:00) weekly(Fri 18:00) portfolio(09:30) volume(17:30)")
        except Exception as e:
            logger.error(f"Discord scheduler setup failed: {e}")

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

        # Get user message (strip bot mention, fall back to clean_content)
        user_message = message.content or ""
        if self.bot.user:
            mention = self.bot.user.mention
            if mention:
                user_message = user_message.replace(mention, "").strip()
        if not user_message:
            user_message = (message.clean_content or "").strip()
        if not user_message:
            await message.reply(
                "訊息內容為空。請確認已開啟 Discord Bot 的 "
                "Message Content Intent，並在訊息中輸入文字。"
            )
            return

        try:
            async with message.channel.typing():
                from claw.channels.discord_formatter import ResponseType

                # 1. Gemma intent classification (fast, cheap, bypasses agent pipeline)
                pre_type, pre_ctx = await self._classify_intent(user_message)
                _DATA_ONLY = {
                    ResponseType.STOCK,
                    ResponseType.SCREEN,
                    ResponseType.PORTFOLIO,
                    ResponseType.MORNING_REPORT,
                    ResponseType.WEEKLY_REPORT,
                }

                # Inject router info so templates can make their own Gemma calls (AI opinion etc.)
                _llm_ctx = {"_router_url": self._router_url, "_intent_model": self._intent_model}

                if pre_type in _DATA_ONLY:
                    # Data-driven: skip main LLM entirely
                    llm_response = ""
                    response_type = pre_type
                    context = {**pre_ctx, **_llm_ctx, "llm_response": ""}
                else:
                    # 2. Call main LLM for text generation (weather / event / report / general)
                    llm_response = await self._query_llm(session_id, user_message)
                    if llm_response:
                        # Let main LLM response refine the classification
                        response_type, context = self._formatter.classify(user_message, llm_response)
                        context.update(_llm_ctx)
                    else:
                        # Main LLM failed → use Gemma's classification with empty response
                        response_type = pre_type
                        context = {**pre_ctx, **_llm_ctx, "llm_response": ""}

                logger.info(f"[Discord] ResponseType={response_type.value} for: {user_message[:50]}")

                # 3. Build DiscordResponse via template
                template = get_template(response_type)
                discord_response = await template.build(context)

            # 4. Dispatch
            sent_msg = await self._dispatch(message.channel, discord_response)

            # 5. Add reactions
            if sent_msg and discord_response.reactions:
                for emoji in discord_response.reactions:
                    try:
                        await sent_msg.add_reaction(emoji)
                    except Exception as e:
                        logger.warning(f"[Discord] Reaction {emoji} failed: {e}")

        except Exception as e:
            logger.error(f"Discord message processing error: {e}")
            await message.reply(f"Error: {type(e).__name__}: {e}")

    async def _classify_intent(
        self, query: str
    ) -> tuple["ResponseType", dict]:  # type: ignore[name-defined]
        """
        Round-trip 1: call a lightweight model (Gemma) directly on the LLM router
        to classify query intent into a ResponseType + optional stock_code.
        Falls back to regex classifier on any error.
        """
        import json as _json
        import httpx
        from claw.channels.discord_formatter import ResponseType

        # Fast keyword pre-filter — bypass Gemma for high-confidence cases
        _q = query.lower()
        if any(kw in _q for kw in ("日報", "晨報", "早報", "早安報", "股價日報", "morning report")):
            logger.info(f"[Discord] keyword pre-filter → morning_report")
            return ResponseType.MORNING_REPORT, {"query": query, "llm_response": ""}
        if any(kw in _q for kw in ("週報", "周報", "本週報告", "weekly report")):
            logger.info(f"[Discord] keyword pre-filter → weekly_report")
            return ResponseType.WEEKLY_REPORT, {"query": query, "llm_response": ""}
        if any(kw in _q for kw in ("持倉", "我的股票", "我的投資", "我買了")):
            return ResponseType.PORTFOLIO, {"query": query, "llm_response": ""}

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    f"{self._router_url}/v1/chat/completions",
                    json={
                        "model": self._intent_model,
                        "messages": [
                            {"role": "system", "content": _INTENT_SYSTEM},
                            {"role": "user", "content": query},
                        ],
                        "temperature": 0.1,
                        "max_tokens": 64,
                    },
                )
            if resp.status_code != 200:
                raise ValueError(f"HTTP {resp.status_code}")

            raw = self._extract_response_text(resp.json())
            # Strip <think> and markdown fences before JSON parse
            raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
            raw = re.sub(r"^```(?:json)?\s*", "", raw).rstrip("`").strip()

            data = _json.loads(raw)
            rtype_str = data.get("type", "general")
            code: str | None = data.get("code") or None

            try:
                rtype = ResponseType(rtype_str)
            except ValueError:
                rtype = ResponseType.GENERAL

            # Build partial context (llm_response filled later if needed)
            context: dict = {"query": query, "llm_response": ""}
            if rtype == ResponseType.STOCK:
                if not code:
                    # Gemma said "stock" but found no code → treat as general
                    logger.info(f"[Discord] Gemma: stock intent but no code — downgrade to general")
                    return ResponseType.GENERAL, context
                context["stock_code"] = code

            logger.info(f"[Discord] Gemma intent: {rtype.value}  code={code}  query={query[:40]!r}")
            return rtype, context

        except Exception as e:
            logger.warning(f"[Discord] Gemma intent classify failed ({e}) — regex fallback")
            return self._formatter.classify(query, "")

    async def _query_llm(self, session_id: str, user_message: str) -> str:
        """Call the gateway and return the assistant's text response."""
        import httpx

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/v1/chat/completions",
                json={
                    "session_id": session_id,
                    "messages": [{"role": "user", "content": user_message}],
                    "stream": False,
                },
                timeout=300,
            )

        if resp.status_code != 200:
            logger.error(f"[Discord] Gateway {resp.status_code}")
            return ""

        try:
            text = self._extract_response_text(resp.json())
            stripped = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()
            if not stripped and text.strip():
                logger.warning("[Discord] LLM returned only <think> blocks — no output text")
            return stripped
        except Exception as e:
            logger.error(f"[Discord] Parse gateway response failed: {e}")
            return ""

    async def _dispatch(
        self,
        channel: discord.abc.Messageable,
        response,
    ) -> discord.Message | None:
        """Send a DiscordResponse to a channel, return the sent Message."""
        try:
            kwargs: dict = {}

            if response.embeds:
                kwargs["embeds"] = response.embeds[:10]

            if response.view:
                kwargs["view"] = response.view

            files = []
            if response.chart_bytes:
                files.append(
                    discord.File(
                        io.BytesIO(response.chart_bytes),
                        filename=response.chart_filename,
                    )
                )
            files.extend(response.extra_files)
            if files:
                kwargs["files"] = files

            if not kwargs:
                text = (response.text or "").strip()
                if not text:
                    return None  # nothing to send
                # Wrap in embed so markdown renders properly (avoid raw ### / --- in chat)
                embed = discord.Embed(description=text[:4096], color=0x5865F2)
                return await channel.send(embed=embed)

            return await channel.send(**kwargs)

        except Exception as e:
            logger.error(f"[Discord] Dispatch failed: {e}")
            try:
                return await channel.send((response.text or f"Error: {e}")[:2000])
            except Exception:
                return None

    @staticmethod
    def _extract_response_text(result: dict) -> str:
        """Extract assistant text from OpenAI-compatible responses."""
        try:
            choices = result.get("choices", [])
            if not choices:
                return ""
            msg = choices[0].get("message", {})
            content = msg.get("content", "")
            if content is None:
                content = ""
            if isinstance(content, list):
                # Support content blocks: [{"type": "text", "text": "..."}]
                parts = []
                for part in content:
                    if isinstance(part, dict):
                        text = part.get("text")
                        if isinstance(text, str):
                            parts.append(text)
                    elif isinstance(part, str):
                        parts.append(part)
                return "".join(parts).strip()
            if isinstance(content, str):
                return content.strip()
            return str(content).strip()
        except Exception:
            return ""

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
        embed: discord.Embed | None = None,
        text: str = "",
        file_bytes: bytes = b"",
        filename: str = ""
    ) -> None:
        """
        Proactive push to a specific channel ID (for Cron jobs).
        Used by scheduled tasks to push morning/evening reports.
        """
        try:
            from typing import cast
            channel = await self.bot.fetch_channel(channel_id)
            msg_channel = cast(discord.abc.Messageable, channel)
            if embed and file_bytes:
                file = discord.File(
                    io.BytesIO(file_bytes),
                    filename=filename
                )
                await msg_channel.send(embed=embed, file=file)
            elif embed:
                await msg_channel.send(embed=embed)
            elif file_bytes:
                file = discord.File(
                    io.BytesIO(file_bytes),
                    filename=filename
                )
                await msg_channel.send(content=text or "", file=file)
            elif text:
                await msg_channel.send(text)
        except Exception as e:
            logger.error(f"Failed to send to channel {channel_id}: {e}")

    async def _beautify_and_send(
        self,
        channel: discord.abc.Messageable,
        user_query: str,
        response_text: str
    ) -> None:
        """
        自動美化任何 LLM 回應為 Discord Embed 並發送，附帶圖表（若有）。

        支持：股票、天氣、新聞、研究報告、任何查詢結果
        """
        try:
            from claw.tools.beautify import beautify_to_discord_embed

            context = f"用戶查詢: {user_query}\nLLM 回應結果"

            # 美化回應，返回 (embed_dict, chart_bytes)
            embed_data, chart_bytes = await beautify_to_discord_embed(
                response_text,
                title="查詢結果",
                data_context=context
            )

            embeds_list = embed_data.get("embeds", [])
            discord_embeds = []

            for embed_dict in embeds_list:
                # 解析 timestamp 字串為 datetime 對象
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

                for field in embed_dict.get("fields", []):
                    embed.add_field(
                        name=field.get("name"),
                        value=field.get("value"),
                        inline=field.get("inline", False),
                    )

                # 若有圖表，設定 image URL 指向附件
                if chart_bytes:
                    embed.set_image(url="attachment://chart.png")

                discord_embeds.append(embed)

            if not discord_embeds:
                await channel.send(response_text[:2000])
                return

            # 發送第一批（含圖表附件）
            first_batch = discord_embeds[:10]
            if chart_bytes:
                file = discord.File(io.BytesIO(chart_bytes), filename="chart.png")
                await channel.send(embeds=first_batch, file=file)
            else:
                await channel.send(embeds=first_batch)

            # 剩餘 embeds 分次發送
            for i in range(10, len(discord_embeds), 10):
                await channel.send(embeds=discord_embeds[i:i+10])

            logger.info(f"[Discord] Sent {len(discord_embeds)} embeds + {'chart' if chart_bytes else 'no chart'}")

        except Exception as e:
            logger.error(f"[Discord] Beautify failed, falling back to text: {e}")
            chunks = [response_text[i:i+2000] for i in range(0, len(response_text), 2000)]
            for chunk in chunks:
                try:
                    await channel.send(chunk)
                except Exception as send_err:
                    logger.error(f"Failed to send fallback text: {send_err}")
