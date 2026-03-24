"""Unit tests for stock backtesting framework."""
import pytest
from unittest.mock import patch
from claw.research.stock_strategy import StockBacktester, BacktestResult


@pytest.mark.asyncio
async def test_backtest_returns_valid_result():
    """Test backtest execution and result structure."""
    backtester = StockBacktester()

    with patch("claw.tools.stock_tools.stock_fetch_data_sync") as mock_fetch:
        mock_fetch.return_value = {
            "ohlcv": [
                {
                    "date": f"2026-03-{i:02d}",
                    "open": 598.0 + i,
                    "high": 603.0 + i,
                    "low": 595.0 + i,
                    "close": 600.0 + i,
                    "volume": 17500000,
                }
                for i in range(1, 31)
            ]
        }

        result = backtester.backtest("2330", "momentum", "2026-03-01", "2026-03-31")

        assert isinstance(result, BacktestResult)
        assert result.symbol == "2330"
        assert result.strategy == "momentum"
        assert 0 <= result.win_rate <= 1
        assert result.total_trades >= 0


@pytest.mark.asyncio
async def test_walk_forward_validation():
    """Test walk-forward validation across multiple strategies."""
    backtester = StockBacktester()

    with patch("claw.tools.stock_tools.stock_fetch_data_sync") as mock_fetch:
        mock_fetch.return_value = {
            "ohlcv": [
                {
                    "date": f"2026-{(i // 30) + 1:02d}-{(i % 30) + 1:02d}",
                    "open": 598.0 + (i % 10),
                    "high": 603.0 + (i % 10),
                    "low": 595.0 + (i % 10),
                    "close": 600.0 + (i % 10),
                    "volume": 17500000,
                }
                for i in range(0, 180)
            ]
        }

        result = backtester.walk_forward_validation(
            "2330",
            ["momentum", "reversal"],
            test_period_days=90,
        )

        assert result["symbol"] == "2330"
        assert "results" in result
        assert len(result["results"]) > 0


@pytest.mark.asyncio
async def test_rsi_calculation():
    """Test RSI indicator calculation."""
    backtester = StockBacktester()
    prices = [
        44,
        44.34,
        44.09,
        43.61,
        44.33,
        44.83,
        45.10,
        45.42,
        45.84,
        46.08,
        45.89,
        46.03,
        45.61,
        46.28,
        46.00,
        46.00,
    ]

    rsi = backtester._calculate_rsi(prices)

    assert 0 <= rsi <= 100
