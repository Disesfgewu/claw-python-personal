"""Reusable Discord UI components: buttons, selects, pagination, reactions."""
from __future__ import annotations

import logging
from typing import Optional, Callable, Awaitable

import discord

logger = logging.getLogger(__name__)


# ─── Emoji constants ──────────────────────────────────────────────────────────

class Emoji:
    # Stock
    STOCK_UP    = "📈"
    STOCK_DOWN  = "📉"
    STOCK_HOLD  = "📊"
    REFRESH     = "🔄"

    # Weather
    SUNNY       = "☀️"
    CLOUDY      = "🌥️"
    RAIN        = "🌧️"
    STORM       = "⛈️"
    COLD        = "🥶"

    # General
    PIN         = "📌"
    IDEA        = "💡"
    CHECK       = "✅"
    CROSS       = "❌"
    CALENDAR    = "📅"
    REPORT      = "📋"
    WARN        = "⚠️"


# ─── Refresh Button ───────────────────────────────────────────────────────────

class RefreshButton(discord.ui.Button):
    """
    A 🔄 refresh button that re-runs a callback and edits the original message.

    Usage:
        async def on_refresh(interaction):
            new_response = await fetch_fresh_data(...)
            # The button handles editing the message

        view = discord.ui.View(timeout=300)
        view.add_item(RefreshButton(on_refresh))
    """

    def __init__(
        self,
        refresh_callback: Callable[[discord.Interaction], Awaitable[None]],
        label: str = "🔄 刷新",
        custom_id: str | None = None,
    ):
        import uuid
        super().__init__(
            label=label,
            style=discord.ButtonStyle.secondary,
            custom_id=custom_id or f"refresh_{uuid.uuid4().hex[:8]}",
        )
        self._refresh_callback = refresh_callback

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        try:
            await self._refresh_callback(interaction)
        except Exception as e:
            logger.error(f"RefreshButton callback error: {e}")
            await interaction.followup.send(f"刷新失敗: {e}", ephemeral=True)


# ─── Stock Time Range Select ──────────────────────────────────────────────────

class StockTimeRangeSelect(discord.ui.Select):
    """
    Dropdown for selecting stock chart time range.

    Triggers a callback with the selected period string.
    """

    PERIODS = [
        ("1 週", "1wk"),
        ("1 個月", "1mo"),
        ("3 個月", "3mo"),
        ("6 個月", "6mo"),
        ("1 年", "1y"),
    ]

    def __init__(
        self,
        on_select: Callable[[discord.Interaction, str], Awaitable[None]],
        current: str = "1mo",
    ):
        options = [
            discord.SelectOption(
                label=label,
                value=value,
                default=(value == current),
            )
            for label, value in self.PERIODS
        ]
        super().__init__(
            placeholder="選擇時間範圍",
            options=options,
            custom_id="stock_time_range",
        )
        self._on_select = on_select

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        selected = self.values[0] if self.values else "1mo"
        try:
            await self._on_select(interaction, selected)
        except Exception as e:
            logger.error(f"StockTimeRangeSelect callback error: {e}")
            await interaction.followup.send(f"切換失敗: {e}", ephemeral=True)


# ─── Confirm View ─────────────────────────────────────────────────────────────

class ConfirmView(discord.ui.View):
    """
    ✅ 確認 / ❌ 取消 View，用於需要用戶確認的操作。

    Usage:
        async def on_confirm(interaction):
            await do_action()

        view = ConfirmView(on_confirm)
        await channel.send("確認執行？", view=view)
    """

    def __init__(
        self,
        on_confirm: Callable[[discord.Interaction], Awaitable[None]],
        confirm_label: str = "✅ 確認",
        cancel_label: str = "❌ 取消",
        timeout: float = 60,
    ):
        super().__init__(timeout=timeout)
        self._on_confirm = on_confirm

        confirm_btn = discord.ui.Button(
            label=confirm_label, style=discord.ButtonStyle.success
        )
        cancel_btn = discord.ui.Button(
            label=cancel_label, style=discord.ButtonStyle.danger
        )

        async def confirm_cb(interaction: discord.Interaction) -> None:
            await interaction.response.defer()
            self.stop()
            await self._on_confirm(interaction)

        async def cancel_cb(interaction: discord.Interaction) -> None:
            await interaction.response.send_message("已取消", ephemeral=True)
            self.stop()

        confirm_btn.callback = confirm_cb
        cancel_btn.callback = cancel_cb
        self.add_item(confirm_btn)
        self.add_item(cancel_btn)


# ─── Pagination View ──────────────────────────────────────────────────────────

class PaginationView(discord.ui.View):
    """
    ◀ / ▶ 分頁 View，用於長列表（如篩選結果、新聞列表等）。

    Usage:
        pages = ["Page 1 content", "Page 2 content", ...]
        view = PaginationView(pages)
        await channel.send(pages[0], view=view)
    """

    def __init__(self, pages: list[str], timeout: float = 120):
        super().__init__(timeout=timeout)
        self.pages = pages
        self.current = 0
        self._update_buttons()

    def _update_buttons(self) -> None:
        self.clear_items()
        if self.current > 0:
            prev_btn = discord.ui.Button(label="◀ 上一頁", style=discord.ButtonStyle.secondary)
            prev_btn.callback = self._prev
            self.add_item(prev_btn)

        page_label = discord.ui.Button(
            label=f"{self.current + 1} / {len(self.pages)}",
            style=discord.ButtonStyle.primary,
            disabled=True,
        )
        self.add_item(page_label)

        if self.current < len(self.pages) - 1:
            next_btn = discord.ui.Button(label="下一頁 ▶", style=discord.ButtonStyle.secondary)
            next_btn.callback = self._next
            self.add_item(next_btn)

    async def _prev(self, interaction: discord.Interaction) -> None:
        self.current -= 1
        self._update_buttons()
        await interaction.response.edit_message(
            content=self.pages[self.current], view=self
        )

    async def _next(self, interaction: discord.Interaction) -> None:
        self.current += 1
        self._update_buttons()
        await interaction.response.edit_message(
            content=self.pages[self.current], view=self
        )


# ─── Stock Action View ────────────────────────────────────────────────────────

def make_stock_view(
    stock_code: str,
    current_period: str = "1mo",
    on_refresh: Optional[Callable] = None,
    on_period_change: Optional[Callable] = None,
) -> discord.ui.View:
    """
    Creates a stock action View with refresh button + time range select.

    Args:
        stock_code: e.g. "2330"
        current_period: current selected period
        on_refresh: async callback(interaction) for refresh
        on_period_change: async callback(interaction, period_str) for time range change

    Returns:
        discord.ui.View ready to attach to a message
    """
    view = discord.ui.View(timeout=300)

    if on_refresh:
        view.add_item(RefreshButton(on_refresh))

    if on_period_change:
        view.add_item(StockTimeRangeSelect(on_period_change, current=current_period))

    return view


# ─── Event RSVP View ─────────────────────────────────────────────────────────

def make_event_view(
    on_accept: Optional[Callable] = None,
    on_decline: Optional[Callable] = None,
) -> discord.ui.View:
    """
    Creates an event RSVP View with ✅ 參加 / ❌ 不參加 buttons.
    """
    view = discord.ui.View(timeout=86400)  # 24 hours

    accept_btn = discord.ui.Button(
        label="✅ 參加", style=discord.ButtonStyle.success, custom_id="event_accept"
    )
    decline_btn = discord.ui.Button(
        label="❌ 不參加", style=discord.ButtonStyle.danger, custom_id="event_decline"
    )

    if on_accept:
        accept_btn.callback = on_accept
    if on_decline:
        decline_btn.callback = on_decline

    view.add_item(accept_btn)
    view.add_item(decline_btn)
    return view


# ─── Portfolio Modal ──────────────────────────────────────────────────────────

class PortfolioAddModal(discord.ui.Modal, title="新增/更新持倉"):
    """
    Discord Modal for adding or updating a stock holding.

    Fields: symbol, shares, cost_per_share, purchase_date (optional), note (optional)
    """

    symbol = discord.ui.TextInput(
        label="股票代號",
        placeholder="例如：2330",
        max_length=6,
        min_length=4,
    )
    shares = discord.ui.TextInput(
        label="持有股數（張數 × 1000）",
        placeholder="例如：1000（= 1張）",
        max_length=10,
    )
    cost_per_share = discord.ui.TextInput(
        label="平均成本（元/股）",
        placeholder="例如：850.0",
        max_length=10,
    )
    purchase_date = discord.ui.TextInput(
        label="買入日期（選填，YYYY-MM-DD）",
        placeholder="例如：2025-01-15",
        required=False,
        max_length=10,
    )
    note = discord.ui.TextInput(
        label="備註（選填）",
        required=False,
        max_length=100,
        style=discord.TextStyle.short,
    )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        from claw.tools.portfolio_manager import PortfolioManager

        try:
            sym = self.symbol.value.strip()
            sh = int(str(self.shares.value).replace(",", "").strip())
            cost = float(str(self.cost_per_share.value).replace(",", "").strip())
            dt = self.purchase_date.value.strip() if self.purchase_date.value else ""
            nt = self.note.value.strip() if self.note.value else ""

            pm = PortfolioManager()
            holding = pm.add_holding(sym, name="", shares=sh, cost_per_share=cost, purchase_date=dt, note=nt)

            embed = discord.Embed(
                title="✅ 持倉已儲存",
                color=0x00B94A,
            )
            embed.add_field(name="股票代號", value=holding["symbol"], inline=True)
            embed.add_field(name="股數", value=f"{holding['shares']:,}", inline=True)
            embed.add_field(name="成本價", value=f"NT$ {holding['cost_per_share']:,.2f}", inline=True)
            if holding.get("purchase_date"):
                embed.add_field(name="買入日期", value=holding["purchase_date"], inline=True)
            if holding.get("note"):
                embed.add_field(name="備註", value=holding["note"], inline=False)

            await interaction.response.send_message(embed=embed, ephemeral=True)

        except (ValueError, TypeError) as e:
            await interaction.response.send_message(
                f"⚠️ 輸入格式有誤：{e}\n請確認股數和成本價為數字。",
                ephemeral=True,
            )

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        logger.error(f"[PortfolioAddModal] Error: {error}")
        await interaction.response.send_message("❌ 儲存持倉時發生錯誤，請稍後重試。", ephemeral=True)


# ─── Portfolio Action View ────────────────────────────────────────────────────

def make_portfolio_view(
    on_add: Optional[Callable] = None,
    on_refresh: Optional[Callable] = None,
) -> discord.ui.View:
    """
    Creates a portfolio action View with:
    - ➕ 新增持倉 button (opens PortfolioAddModal)
    - 🔄 刷新 button
    """
    view = discord.ui.View(timeout=300)

    add_btn = discord.ui.Button(
        label="➕ 新增/更新持倉",
        style=discord.ButtonStyle.primary,
        custom_id="portfolio_add",
    )
    if on_add:
        add_btn.callback = on_add
    else:
        async def _default_add(interaction: discord.Interaction) -> None:
            await interaction.response.send_modal(PortfolioAddModal())
        add_btn.callback = _default_add

    view.add_item(add_btn)

    if on_refresh:
        view.add_item(RefreshButton(on_refresh, label="🔄 刷新持倉"))

    return view
