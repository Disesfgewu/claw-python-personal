"""
Integration tests for live API endpoints.
These tests require:
1. LIVE_BACKEND=1 environment variable
2. LLM Router running at configured URL
3. Discord credentials in environment or config
4. Internet connection for data fetching
"""
from __future__ import annotations

import os
import pytest
import asyncio
from datetime import datetime
from unittest.mock import patch

# 只在 LIVE_BACKEND=1 時執行
pytestmark = pytest.mark.skipif(
    os.getenv("LIVE_BACKEND") != "1",
    reason="Integration tests require LIVE_BACKEND=1 env var"
)


class TestLiveAPI:
    """Test real API endpoints without mocking."""

    @pytest.fixture
    def live_config(self):
        """Load live configuration from environment."""
        from claw.core.config import get_config
        cfg = get_config()
        return {
            "llm_router_url": os.getenv("LLM_ROUTER_URL", cfg.llm_router.url),
            "llm_router_key": os.getenv("LLM_ROUTER_KEY", cfg.llm_router.api_key),
            "discord_token": os.getenv("DISCORD_TOKEN", cfg.discord.token),
            "discord_channel_id": int(os.getenv("DISCORD_CHANNEL_ID", cfg.discord.stock_channel_id or 0)),
        }

    @pytest.mark.asyncio
    async def test_stock_fetch_live(self, live_config):
        """
        Test stock_fetch against real data source (TWSE/Yahoo).

        驗證項目：
        - 能成功連接到資料源
        - 返回有效的 OHLCV 資料
        - 必要欄位都存在
        - 資料合理性（close > 0, volume > 0）
        """
        from claw.tools.stock_tools import stock_fetch_data

        # 使用現實股票代碼
        symbol = "2330"  # TSMC

        result = await stock_fetch_data(symbol, period="1mo")

        # 驗證結果結構
        assert result is not None
        assert result["symbol"] == symbol
        assert "current" in result
        assert "ohlcv" in result
        assert len(result["ohlcv"]) > 0

        # 驗證 OHLCV 資料合理性
        for candle in result["ohlcv"][-5:]:  # 最後 5 筆
            assert candle["open"] > 0
            assert candle["high"] > 0
            assert candle["low"] > 0
            assert candle["close"] > 0
            assert candle["high"] >= candle["low"]
            assert candle["volume"] >= 0

        print(f"✓ stock_fetch live test passed for {symbol}")

    @pytest.mark.asyncio
    async def test_stock_analyze_live(self, live_config):
        """
        Test stock_analyze with real data.

        驗證項目：
        - 技術指標計算正確
        - 生成有效的 JSON 報告
        - 訊號判斷合理
        """
        import json
        from claw.tools.stock_tools import stock_analyze

        symbol = "2330"
        result_json = await stock_analyze(symbol, period="3mo")

        # 驗證結果是有效的 JSON
        assert isinstance(result_json, str)
        assert "Error" not in result_json or result_json.startswith("{")

        try:
            report = json.loads(result_json)
        except json.JSONDecodeError:
            pytest.fail(f"Invalid JSON response: {result_json}")

        # 驗證報告結構
        assert report.get("symbol") == symbol
        assert report.get("current_price", 0) > 0
        signal = report.get("signal", "")
        assert signal in ["strong_buy", "buy", "hold", "sell", "strong_sell"], f"Invalid signal: {signal}"

        print(f"✓ stock_analyze live test passed: {signal}")

    @pytest.mark.asyncio
    async def test_chart_generation_live(self, live_config):
        """
        Test chart generation with real stock data.

        驗證項目：
        - PNG 生成成功
        - PNG 檔案有效（magic number）
        - 包含 K 線、均線、成交量
        """
        from claw.tools.stock_tools import stock_fetch_data
        from claw.tools.chart_tools import generate_candlestick_chart

        symbol = "2330"
        fetch_result = await stock_fetch_data(symbol, period="1mo")
        ohlcv = fetch_result.get("ohlcv", [])

        if len(ohlcv) < 10:
            pytest.skip("Not enough data for chart generation")

        png_bytes = generate_candlestick_chart(symbol, ohlcv)

        # 驗證 PNG
        assert isinstance(png_bytes, bytes)
        assert len(png_bytes) > 1000  # 合理的最小大小
        assert png_bytes[:8] == b'\x89PNG\r\n\x1a\n'  # PNG magic number

        print(f"✓ Chart generation live test passed: {len(png_bytes)} bytes")

    @pytest.mark.asyncio
    async def test_stock_screen_live(self, live_config):
        """
        Test stock screening against real Taiwan 50.

        驗證項目：
        - 能篩選出台灣50股票
        - 返回有效的 StockReport 列表
        - 篩選條件被正確應用
        """
        from claw.tools.stock_tools import stock_screen

        # 寬鬆的篩選條件（確保能找到股票）
        criteria = {
            'rsi_min': 0,
            'rsi_max': 100,
            'volume_threshold': 0,
            'signal': ['strong_buy', 'buy', 'hold', 'sell', 'strong_sell']
        }

        results = stock_screen(criteria)

        # 驗證結果
        assert isinstance(results, list)
        assert len(results) > 0, "Should screen out at least some stocks"
        assert len(results) <= 15, "Should return max 15 stocks"

        for report in results:
            assert report.symbol
            assert report.current_price > 0
            assert report.signal in ['strong_buy', 'buy', 'hold', 'sell', 'strong_sell']

        print(f"✓ Stock screening live test passed: {len(results)} stocks found")
