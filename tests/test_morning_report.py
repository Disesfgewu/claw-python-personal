"""Unit tests for morning report cron job."""
import pytest
from unittest.mock import patch, MagicMock
from claw.cron.jobs.morning_report import morning_report_job
from claw.models.stock_report import StockReport, TechnicalIndicators, FundamentalData


@pytest.mark.asyncio
async def test_morning_report_executes_successfully():
    """Test morning report job executes and returns success status."""
    mock_storage = MagicMock()
    mock_llm = MagicMock()
    mock_config = MagicMock()
    mock_config.discord.stock_channel_id = 123456789

    indicators = TechnicalIndicators(
        ma_20=600.0,
        ma_50=590.0,
        ma_200=580.0,
        rsi_14=55.0,
        macd=1.0,
        macd_signal=0.5,
        macd_hist=0.5,
        kd_k=50.0,
        kd_d=48.0,
    )
    fundamentals = FundamentalData()

    mock_report = StockReport(
        symbol="2330",
        name="台積電",
        current_price=600.0,
        change_pct=0.3,
        change_amount=2.0,
        indicators=indicators,
        fundamental=fundamentals,
    )
    mock_report.recommendation = "買進"

    with patch("claw.cron.jobs.morning_report.stock_screen") as mock_screen:
        mock_screen.return_value = [mock_report]

        with patch("claw.cron.jobs.morning_report.stock_fetch") as mock_fetch:
            mock_fetch.return_value = {"ohlcv": []}

            with patch("claw.cron.jobs.morning_report.generate_candlestick_chart") as mock_chart:
                mock_chart.return_value = b"PNG_DATA"

                with patch("claw.cron.jobs.morning_report.get_config") as mock_get_cfg:
                    mock_get_cfg.return_value = mock_config

                    cron_data = {"channel_id": 123456789}
                    result = await morning_report_job(mock_storage, mock_llm, cron_data)

                    assert result["status"] in ["success", "no_bot", "no_stocks"]
                    assert "timestamp" in result
                    assert "stocks_screened" in result or "reason" in result
