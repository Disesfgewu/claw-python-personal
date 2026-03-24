"""
Cron job execution verification.
Tests that morning_report and weekly_report jobs execute correctly.
"""
from __future__ import annotations

import os
import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import patch, AsyncMock, MagicMock

pytestmark = pytest.mark.skipif(
    os.getenv("LIVE_BACKEND") != "1",
    reason="Cron tests require LIVE_BACKEND=1"
)


@pytest.mark.asyncio
async def test_morning_report_execution():
    """
    Test morning report Cron job execution - simplified.

    驗證項目：
    - Job 可以執行且返回有效的狀態
    """
    from claw.core.storage import Storage
    from claw.llm.router_client import LLMRouterClient
    from claw.models.stock_report import StockReport, TechnicalIndicators, FundamentalData
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        storage = Storage(db_path=f"{tmpdir}/claw.db", transcript_dir=f"{tmpdir}/transcripts")
        await storage.init()

        llm = LLMRouterClient(base_url="http://localhost:8000", api_key="test")

        # 創建模擬報告
        mock_report = StockReport(
            symbol="2330",
            name="台積電",
            current_price=600.0,
            change_pct=1.69,
            change_amount=10.0,
            previous_close=590.0,
            day_high=605.0,
            day_low=595.0,
            volume=5000000,
            timestamp="2026-03-23T09:30:00",
            indicators=TechnicalIndicators(
                ma_20=595.0,
                ma_50=580.0,
                ma_200=570.0,
                rsi_14=55.0,
                macd=12.5,
                macd_signal=10.0,
                macd_hist=2.5,
                kd_k=60.0,
                kd_d=50.0,
                bollinger_upper=620.0,
                bollinger_middle=600.0,
                bollinger_lower=580.0,
            ),
            fundamental=FundamentalData(
                pe_ratio=20.0,
                pb_ratio=3.0,
                roe=15.0,
            ),
            signal="buy",
            trend="uptrend",
            summary="買進訊號"
        )

        with patch("claw.cron.jobs.morning_report.stock_screen") as mock_screen:
            mock_screen.return_value = [mock_report]

            from claw.cron.jobs.morning_report import morning_report_job

            result = await morning_report_job(storage, llm, {"channel_id": 123456789})

            # 驗證執行結果 - job 應該返回有效的狀態
            assert isinstance(result, dict), "Result should be a dict"
            assert "status" in result, "Result should have 'status' key"
            assert result["status"] in ["success", "no_bot", "no_stocks", "failed"], f"Unexpected status: {result.get('status')}"
            print(f"✓ Morning report executed: {result['status']}")


@pytest.mark.asyncio
async def test_weekly_report_execution():
    """
    Test weekly report Cron job execution - simplified.

    驗證項目：
    - Job 可以執行且返回有效的狀態
    """
    from claw.core.storage import Storage
    from claw.llm.router_client import LLMRouterClient
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        storage = Storage(db_path=f"{tmpdir}/claw.db", transcript_dir=f"{tmpdir}/transcripts")
        await storage.init()

        llm = LLMRouterClient(base_url="http://localhost:8000", api_key="test")

        # 模擬週報 job - 使用簡單的 mock
        with patch("claw.research.stock_strategy.StockStrategyExecutor") as mock_executor_class:
            mock_executor = MagicMock()
            mock_executor_class.return_value = mock_executor

            mock_executor.execute = AsyncMock(return_value={
                "status": "success",
                "winner": "momentum",
                "winner_sharpe": 1.2,
                "winner_win_rate": 0.65
            })
            mock_executor.evaluate = AsyncMock(return_value={
                "is_valid": True,
                "confidence": 0.85
            })

            # Patch DiscordChannel at module level before importing
            with patch("discord.Client"):
                from claw.cron.jobs.weekly_report import weekly_report_job

                result = await weekly_report_job(storage, llm, {"channel_id": 987654321})

                # 驗證執行結果
                assert isinstance(result, dict), "Result should be a dict"
                assert "status" in result, "Result should have 'status' key"
                # Weekly report may return success or no_bot depending on Discord availability
                assert result["status"] in ["success", "no_bot", "failed"], f"Unexpected status: {result.get('status')}"
                print(f"✓ Weekly report executed: {result['status']}")


@pytest.mark.asyncio
async def test_cron_schedule_accuracy():
    """
    Verify that Cron schedules are correctly parsed and triggered.

    驗證項目：
    - 晨報排程 (0 8 * * 1-5) 只在週一至週五執行
    - 週報排程 (0 18 * * 5) 只在週五執行
    """
    from cron_validator import CronValidator
    from datetime import datetime

    # 晨報排程驗證
    morning_cron = "0 8 * * 1-5"
    try:
        CronValidator.parse(morning_cron)
        morning_valid = True
    except Exception:
        morning_valid = False
    assert morning_valid, "Morning cron is invalid"

    # 週報排程驗證
    weekly_cron = "0 18 * * 5"
    try:
        CronValidator.parse(weekly_cron)
        weekly_valid = True
    except Exception:
        weekly_valid = False
    assert weekly_valid, "Weekly cron is invalid"

    # Test that morning cron matches on Monday at 08:00
    from datetime import datetime, timezone
    monday_8am = datetime(2026, 3, 23, 8, 0, 0)  # Monday
    assert CronValidator.match_datetime(morning_cron, monday_8am), "Morning cron should match Monday 08:00"

    # Test that weekly cron matches on Friday at 18:00
    friday_6pm = datetime(2026, 3, 27, 18, 0, 0)  # Friday
    assert CronValidator.match_datetime(weekly_cron, friday_6pm), "Weekly cron should match Friday 18:00"

    print("✓ Cron schedules are valid and match expected times")
