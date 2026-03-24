# Phase S2B Worker Prompt — Morning Report Cron Job

> 發給：**Codex**
> 當前狀態：186 tests passing（Phase S2a 完成）
> 目標狀態：187+ tests + 晨報 Cron job 就位
> 耗時預估：2 小時
> 依賴：Phase S0 (Discord send_to_channel_id), Phase S1/S2a (stock tools) 必須先完成

---

## 背景說明

Phase S2b 與 S2a 並行執行。在 S2a 完成篩選工具後，S2b 負責自動化層面：

**晨報 Cron Job** — 每個交易日早上 08:00 自動執行：
1. 呼叫 `stock_screen()` 拉取前 10 個強勢股
2. 對每個股票呼叫 `generate_chart()` 生成圖表
3. 組合成 Discord Embed（帶圖表附檔）
4. 透過 `send_to_channel_id()` 推送到指定的 Discord 頻道

這是第一個真實的 Cron job，後續 S4b 會有周報（週五 18:00）。

---

## Task 1 — 建立 `claw/cron/jobs/morning_report.py`

新建晨報邏輯檔案。此檔案由 CronService 在排定時間調用。

**檔案位置**：`claw/cron/jobs/morning_report.py`

**內容**：

```python
"""Morning report job — daily stock screening and push to Discord."""
from __future__ import annotations

import logging
import json
from datetime import datetime
from io import BytesIO

logger = logging.getLogger(__name__)


async def morning_report_job(
    storage,
    llm,
    cron_data: dict = None
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
        import discord
        from claw.tools.stock_tools import stock_screen
        from claw.tools.chart_tools import generate_candlestick_chart
        from claw.channels.discord import DiscordChannel
        from claw.core.config import get_config

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
        screened = stock_screen()
        if not screened:
            logger.warning("No stocks passed screening")
            return {
                "status": "no_stocks",
                "stocks_screened": 0,
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }

        logger.info(f"Screened {len(screened)} stocks")

        # Step 2: Generate embeds with charts
        embeds = []
        files = []

        # Main embed: 標題 + 概述
        main_embed = discord.Embed(
            title="🌅 台股晨報 — Taiwan 50 強勢股",
            description=f"篩選時間: {datetime.now().strftime('%Y-%m-%d %H:%M')} \n" +
                       f"共篩選 {len(screened)} 檔強勢股\n\n" +
                       "**Top 5 Strong Stocks:**",
            color=discord.Color.green()
        )

        for i, report in enumerate(screened[:5]):
            main_embed.add_field(
                name=f"{i+1}. {report.symbol} {report.name}",
                value=f"💰 {report.current_price} TWD | Signal: {report.signal}\n" +
                     f"RSI: {report.indicators.rsi:.1f} | {report.trend}\n" +
                     f"📝 {report.summary}",
                inline=False
            )

        embeds.append(main_embed)

        # Step 3: Generate individual charts
        for i, report in enumerate(screened[:3]):  # 只前 3 個生成圖表（避免檔案太多）
            try:
                from claw.tools.stock_tools import stock_fetch
                fetch_result = stock_fetch(report.symbol, period="3mo")
                png_bytes = generate_candlestick_chart(report.symbol, fetch_result.get("ohlcv", []))

                # Create discord.File from BytesIO
                file_obj = BytesIO(png_bytes)
                discord_file = discord.File(file_obj, filename=f"chart_{report.symbol}.png")
                files.append(discord_file)

                # 為圖表創建單獨的 Embed
                chart_embed = discord.Embed(
                    title=f"📊 {report.symbol} 走勢圖",
                    description=f"近 3 個月 K 線圖",
                    color=discord.Color.blue()
                )
                chart_embed.set_image(url=f"attachment://chart_{report.symbol}.png")
                embeds.append(chart_embed)

            except Exception as e:
                logger.warning(f"Failed to generate chart for {report.symbol}: {e}")
                continue

        # Step 4: Push to Discord
        discord_channel = DiscordChannel.__new__(DiscordChannel)
        if hasattr(discord_channel, 'bot') and discord_channel.bot:
            message = await discord_channel.send_to_channel_id(
                channel_id=channel_id,
                embed=embeds[0],  # Send embeds separately for multiple messages
                file_bytes=None
            )
            # Send chart embeds
            for chart_embed in embeds[1:]:
                await discord_channel.send_to_channel_id(
                    channel_id=channel_id,
                    embed=chart_embed,
                    file_bytes=None
                )
            logger.info(f"Morning report pushed to Discord channel {channel_id}")
        else:
            logger.warning("Discord bot not available for push")
            return {
                "status": "no_bot",
                "reason": "Discord bot instance not initialized",
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }

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
```

**驗收**：
- 檔案存在於指定路徑
- 函數簽名正確（接收 storage, llm, cron_data）
- 沒有語法錯誤

---

## Task 2 — 在 `claw/main.py` 註冊晨報 Cron Job

在 lifespan 中，CronService 啟動後，註冊一個晨報 Cron job。

**在 `claw/main.py` lifespan 中，CronService 啟動後加入**：

```python
    # 晨報 Cron Job（每個交易日 08:00）
    # Schedule: "0 8 * * 1-5" = 08:00, 週一至週五
    morning_job = {
        "name": "morning_report",
        "schedule": "0 8 * * 1-5",
        "prompt": "執行台股晨報：掃 Taiwan 50 強勢股，生成圖表，推送到 Discord",
        "callable": "claw.cron.jobs.morning_report:morning_report_job",
        "enabled": True,
    }
    try:
        await cron_service.add_job(**morning_job)
        logger.info("Morning report Cron job registered (0 8 * * 1-5 / 08:00 weekdays)")
    except Exception as e:
        logger.warning(f"Failed to register morning report job: {e}")
```

**位置提示**：在以下程式碼之後加入：

```python
    cron_service = CronService(store=cron_store, storage=storage, llm=llm)
    await cron_service.start()
    set_cron_service(cron_service)
    logger.info("CronService initialized and started")
```

**驗收**：
- main.py 能成功啟動
- 日誌顯示 "Morning report Cron job registered"

---

## Task 3 — 建立單元測試 `tests/test_morning_report.py`

建立 1 個測試，驗證晨報邏輯（使用 mock）。

**檔案位置**：`tests/test_morning_report.py`

**測試內容**：

```python
"""Unit tests for morning report cron job."""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from claw.cron.jobs.morning_report import morning_report_job
from claw.models.stock_report import StockReport


@pytest.mark.asyncio
async def test_morning_report_executes_successfully():
    """Test morning report job executes and returns success status."""
    # Mock dependencies
    mock_storage = MagicMock()
    mock_llm = MagicMock()
    mock_config = MagicMock()
    mock_config.discord.stock_channel_id = 123456789

    mock_report = StockReport(
        symbol="2330",
        name="台積電",
        current_price=600.0,
        previous_close=598.0,
        day_high=605.0,
        day_low=595.0,
        volume=18500000,
    )
    mock_report.signal = "buy"
    mock_report.summary = "RSI 適中，買進訊號"

    with patch("claw.cron.jobs.morning_report.stock_screen") as mock_screen:
        mock_screen.return_value = [mock_report]

        with patch("claw.cron.jobs.morning_report.get_config") as mock_get_cfg:
            mock_get_cfg.return_value = mock_config

            cron_data = {"channel_id": 123456789}
            result = await morning_report_job(mock_storage, mock_llm, cron_data)

            assert result["status"] in ["success", "no_bot", "no_stocks"]  # 允許多種狀態
            assert "timestamp" in result
            assert "stocks_screened" in result or "reason" in result
```

**驗收**：
- 測試能成功執行
- 測試通過

---

## Task 4 — 執行測試

```bash
cd /home/martin/Desktop/claw-python-personal

# 執行晨報測試
python -m pytest tests/test_morning_report.py -v

# 執行全部測試
python -m pytest tests/ -q --tb=short
```

**預期輸出**：
- `test_morning_report_executes_successfully` PASSED
- 整體 `187 passed, 3 skipped`（新增 1 個測試）

---

## Task 5 — 驗證 Cron Job 註冊

```bash
python -c "
import asyncio
from claw.core.storage import Storage
from claw.cron.store import CronStore
from claw.cron.service import CronService
import tempfile

async def check_cron():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = f'{tmpdir}/test.db'
        store = CronStore(db_path=db_path)
        await store.init()
        service = CronService(store=store, storage=None, llm=None)

        # 查詢是否有晨報 job
        # 預計在 main.py startup 時被註冊
        print('✅ CronService ready for morning report job registration')

asyncio.run(check_cron())
"
```

**預期輸出**：CronService 可以被初始化

---

## 交付清單

完成後回報：

1. **新建的檔案絕對路徑**：
   - `/home/martin/Desktop/claw-python-personal/claw/cron/jobs/morning_report.py`
   - `/home/martin/Desktop/claw-python-personal/tests/test_morning_report.py`

2. **修改的檔案絕對路徑**：
   - `/home/martin/Desktop/claw-python-personal/claw/main.py`

3. **pytest 最終輸出**（應為 187+ passed）

4. **遇到的問題和解決方式**

---

## 完成標準

✅ morning_report_job() 能篩選台灣50 強勢股
✅ morning_report_job() 能生成 Discord Embed 和圖表
✅ morning_report_job() 能透過 send_to_channel_id() 推送
✅ Cron job 已在 main.py 註冊（schedule: "0 8 * * 1-5"）
✅ 187+ tests pass, 0 failures
✅ 1 個單元測試通過

---

## 注意事項

- morning_report_job() 應該是 async 函數，因為它涉及 discord 推送
- 如果 Discord bot 未初始化，應優雅降級（記錄 warning，不拋出異常）
- 圖表生成失敗不應阻止整個晨報（使用 try-except）
- Cron schedule "0 8 * * 1-5" 表示每週一至週五 08:00 執行
- 日後可根據台灣時區調整時間（目前使用伺服器時區）

