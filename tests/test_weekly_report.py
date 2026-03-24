"""Unit tests for weekly report cron job."""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from claw.cron.jobs.weekly_report import weekly_report_job


@pytest.mark.asyncio
async def test_weekly_report_executes_successfully():
    """Test weekly report job executes and returns success status."""
    mock_storage = MagicMock()
    mock_llm = MagicMock()
    mock_config = MagicMock()
    mock_config.discord.stock_channel_id = 987654321
    mock_config.discord.morning_report_channel_id = None

    with patch("claw.research.stock_strategy.StockStrategyExecutor") as mock_executor_class:
        mock_executor = MagicMock()
        mock_executor_class.return_value = mock_executor

        # Mock execute and evaluate
        mock_executor.execute = AsyncMock(return_value={
            "status": "success",
            "symbol": "2330",
            "winner": "momentum",
            "winner_sharpe": 1.2,
            "winner_win_rate": 0.65
        })
        mock_executor.evaluate = AsyncMock(return_value={
            "is_valid": True,
            "confidence": 0.85
        })

        with patch("claw.core.config.get_config") as mock_get_cfg:
            mock_get_cfg.return_value = mock_config

            cron_data = {"channel_id": 987654321}
            result = await weekly_report_job(mock_storage, mock_llm, cron_data)

            assert result["status"] in ["success", "no_bot"]
            assert "timestamp" in result
