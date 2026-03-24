from __future__ import annotations

import pytest
import pandas as pd
import json
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_stock_fetch_success():
    """stock_fetch returns OHLCV JSON."""
    from claw.tools.stock_tools import stock_fetch

    # Mock the Yahoo Finance fetch
    mock_df = pd.DataFrame({
        'Date': pd.date_range('2026-01-01', periods=10),
        'Open': [100] * 10,
        'High': [102] * 10,
        'Low': [98] * 10,
        'Close': [101] * 10,
        'Volume': [1000000] * 10,
    })

    with patch('claw.tools.stock_tools._fetch_from_twse_crawler', return_value=None):
        with patch('claw.tools.stock_tools._fetch_from_yahoo', return_value=mock_df):
            result = await stock_fetch("2330", period="3mo")

    assert "Error" not in result
    data = json.loads(result)
    assert len(data) == 10
    assert 'Close' in data[0]


@pytest.mark.asyncio
async def test_stock_analyze_success():
    """stock_analyze returns StockReport JSON with all fields."""
    from claw.tools.stock_tools import stock_analyze
    from claw.models.stock_report import FundamentalData

    # Mock the fetch and fundamental data
    mock_df = pd.DataFrame({
        'Date': pd.date_range('2026-01-01', periods=50),
        'Open': [100 + i*0.5 for i in range(50)],
        'High': [102 + i*0.5 for i in range(50)],
        'Low': [98 + i*0.5 for i in range(50)],
        'Close': [101 + i*0.5 for i in range(50)],
        'Volume': [1000000] * 50,
    })

    with patch('claw.tools.stock_tools.stock_fetch') as mock_fetch:
        with patch('claw.tools.stock_tools._fetch_fundamental') as mock_fund:
            with patch('claw.tools.stock_tools._generate_chart') as mock_chart:
                mock_fetch.return_value = mock_df.to_json(orient='records')
                mock_fund.return_value = FundamentalData(
                    pe_ratio=15.0,
                    pb_ratio=2.0,
                    roe=20.0,
                    dividend_yield=4.0,
                    debt_ratio=0.3
                )
                mock_chart.return_value = None

                result = await stock_analyze("2330")

    assert "Error" not in result
    report = json.loads(result)
    assert report['symbol'] == '2330'
    assert 'current_price' in report
    assert 'recommendation' in report
    assert 'chart_base64' in report


@pytest.mark.asyncio
async def test_stock_fetch_data_wrapper():
    """stock_fetch_data returns structured dict."""
    from claw.tools.stock_tools import stock_fetch_data

    mock_df = pd.DataFrame({
        'Date': pd.date_range('2026-01-01', periods=5),
        'Open': [100] * 5,
        'High': [102] * 5,
        'Low': [98] * 5,
        'Close': [101] * 5,
        'Volume': [1000000] * 5,
    })

    with patch('claw.tools.stock_tools._fetch_from_twse_crawler', return_value=None):
        with patch('claw.tools.stock_tools._fetch_from_yahoo', return_value=mock_df):
            result = await stock_fetch_data('2330', period='3mo')

    assert result['symbol'] == '2330'
    assert 'ohlcv' in result
    assert result['current'] > 0


@pytest.mark.asyncio
async def test_stock_analyze_report_wrapper():
    """stock_analyze_report returns StockReport with trend/signal/summary."""
    from claw.tools.stock_tools import stock_analyze_report
    from claw.models.stock_report import StockReport

    mock_ohlcv = [
        {"date": "2026-03-20", "open": 598.0, "high": 603.0, "low": 595.0, "close": 601.0, "volume": 17500000},
        {"date": "2026-03-21", "open": 601.0, "high": 605.0, "low": 599.0, "close": 603.0, "volume": 18000000},
        {"date": "2026-03-22", "open": 603.0, "high": 605.0, "low": 595.0, "close": 600.0, "volume": 18500000},
    ]

    report = stock_analyze_report('2330', mock_ohlcv)

    assert isinstance(report, StockReport)
    assert report.trend in ['uptrend', 'downtrend', 'sideways']
    assert report.signal in ['strong_buy', 'buy', 'hold', 'sell', 'strong_sell']
    assert report.summary
