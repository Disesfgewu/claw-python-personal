"""Unit tests for stock screening and chip analysis."""
import pytest
from unittest.mock import patch, MagicMock
from claw.tools.stock_tools import stock_screen, stock_chip
from claw.models.stock_report import StockReport, TechnicalIndicators


@pytest.mark.asyncio
async def test_stock_screen_filters_correctly():
    """Test stock_screen filters based on criteria."""
    # Mock stock_analyze to return controlled reports
    with patch("claw.tools.stock_tools.stock_analyze_report") as mock_analyze:
        # Create mock reports with different signals
        mock_reports = []
        for i, signal in enumerate(['strong_buy', 'buy', 'hold', 'sell']):
            report = MagicMock()
            report.symbol = f"200{i}"
            report.name = f"Company {i}"
            report.current_price = 100.0 + i
            report.volume = 15000000
            report.signal = signal
            report.indicators.rsi = 50.0 + i * 5
            mock_reports.append(report)

        mock_analyze.side_effect = mock_reports

        with patch("claw.tools.stock_tools.stock_fetch_data_sync") as mock_fetch:
            mock_fetch.return_value = {"ohlcv": []}
            results = stock_screen({'signal': ['buy', 'strong_buy']})
            assert len(results) <= 15
            for r in results:
                assert r.signal in ['buy', 'strong_buy']


@pytest.mark.asyncio
async def test_stock_chip_returns_valid_dict():
    """Test stock_chip returns valid chip data."""
    result = stock_chip("2330")

    assert isinstance(result, dict)
    assert result["symbol"] == "2330"
    assert "chip_signal" in result
    assert result["chip_signal"] in ["positive", "neutral", "negative"]
    assert "net_foreign" in result
