# Phase S4A Worker Prompt — Strategy Backtesting Framework

> 發給：**Codex**
> 當前狀態：189 tests passing（Phase S3 完成）
> 目標狀態：192+ tests + StockBacktester 框架就位
> 耗時預估：3 小時
> 依賴：Phase S1a (stock_tools) 必須先完成

---

## 背景說明

Phase S4a 實現策略驗證層。前面的 Phase S1-S3 完成了股票分析工具，但缺乏歷史數據驗證。

S4a 的任務是建立 **StockBacktester** 框架：
1. 對指定股票運行 3 個歷史策略（動能、反轉、基本面）
2. 計算回測指標（勝率、Sharpe ratio、最大回撤）
3. 支援 Walk-forward 驗證（過去 3 個月 vs 最近 3 個月）

後續 S4b 會將此框架與 ResearchLoop 整合，生成週報。

---

## Task 1 — 建立 `claw/research/stock_strategy.py`

新建策略回測框架檔案。

**檔案位置**：`claw/research/stock_strategy.py`

**內容**：

```python
"""Stock strategy backtesting framework."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class BacktestResult:
    """Backtest result metrics."""
    symbol: str
    strategy: str  # "momentum", "reversal", "fundamental"
    start_date: str
    end_date: str
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float  # 勝率 (0-1)
    total_return: float  # 總報酬 (%)
    sharpe_ratio: float  # Sharpe ratio
    max_drawdown: float  # 最大回撤 (%)
    avg_trade_return: float  # 平均交易報酬 (%)


class StockBacktester:
    """
    Backtester for stock trading strategies.

    支援三個策略：
    1. Momentum（動能策略）— RSI > 60 買入，RSI < 40 賣出
    2. Reversal（反轉策略）— RSI < 30 買入，RSI > 70 賣出
    3. Fundamental（基本面策略）— PE < 15 時買入，PE > 25 時賣出
    """

    def __init__(self):
        self.results = []

    def backtest(
        self,
        symbol: str,
        strategy_name: str,
        start_date: str,  # YYYY-MM-DD
        end_date: str,    # YYYY-MM-DD
        initial_capital: float = 100000.0
    ) -> BacktestResult:
        """
        Run backtest for a strategy on historical data.

        Args:
            symbol: Stock code (e.g., "2330")
            strategy_name: "momentum", "reversal", or "fundamental"
            start_date: Backtest start date
            end_date: Backtest end date
            initial_capital: Initial capital for trading

        Returns:
            BacktestResult with metrics
        """
        from claw.tools.stock_tools import stock_fetch, stock_analyze

        try:
            # 計算回測期間
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            end_dt = datetime.strptime(end_date, "%Y-%m-%d")
            period_days = (end_dt - start_dt).days

            # 拉取歷史資料
            fetch_result = stock_fetch(symbol, period="1y")
            ohlcv = fetch_result.get("ohlcv", [])

            # 篩選回測期間內的資料
            ohlcv_filtered = [
                o for o in ohlcv
                if start_date <= o.get("date", "") <= end_date
            ]

            if not ohlcv_filtered:
                logger.warning(f"No data for {symbol} in period {start_date} to {end_date}")
                return BacktestResult(
                    symbol=symbol,
                    strategy=strategy_name,
                    start_date=start_date,
                    end_date=end_date,
                    total_trades=0,
                    winning_trades=0,
                    losing_trades=0,
                    win_rate=0.0,
                    total_return=0.0,
                    sharpe_ratio=0.0,
                    max_drawdown=0.0,
                    avg_trade_return=0.0
                )

            # 執行策略
            trades = []
            position = None  # None = 空手, float = 持股價格

            for i, candle in enumerate(ohlcv_filtered):
                # 簡化實作：在每個 candle 上執行策略邏輯
                close = candle.get("close", 0)

                if strategy_name == "momentum":
                    # 計算 RSI（簡化版：只用最近 14 個 candle）
                    recent = ohlcv_filtered[max(0, i-14):i+1]
                    rsi = self._calculate_rsi([c.get("close", 0) for c in recent])

                    if rsi > 60 and position is None:
                        # 買入信號
                        position = close
                        trades.append({"type": "buy", "price": close, "date": candle.get("date")})
                    elif rsi < 40 and position is not None:
                        # 賣出信號
                        trades.append({"type": "sell", "price": close, "date": candle.get("date"), "entry": position})
                        position = None

                elif strategy_name == "reversal":
                    recent = ohlcv_filtered[max(0, i-14):i+1]
                    rsi = self._calculate_rsi([c.get("close", 0) for c in recent])

                    if rsi < 30 and position is None:
                        position = close
                        trades.append({"type": "buy", "price": close, "date": candle.get("date")})
                    elif rsi > 70 and position is not None:
                        trades.append({"type": "sell", "price": close, "date": candle.get("date"), "entry": position})
                        position = None

                elif strategy_name == "fundamental":
                    # 簡化實作：使用固定 PE 閾值
                    if close < 600 and position is None:  # 假設 PE < 15 對應價格 < 600
                        position = close
                        trades.append({"type": "buy", "price": close, "date": candle.get("date")})
                    elif close > 700 and position is not None:  # PE > 25 對應價格 > 700
                        trades.append({"type": "sell", "price": close, "date": candle.get("date"), "entry": position})
                        position = None

            # 計算指標
            winning_trades = 0
            losing_trades = 0
            trade_returns = []

            # 配對買賣單
            i = 0
            while i < len(trades):
                if trades[i]["type"] == "buy" and i + 1 < len(trades) and trades[i + 1]["type"] == "sell":
                    entry = trades[i]["price"]
                    exit_price = trades[i + 1]["price"]
                    ret = (exit_price - entry) / entry * 100
                    trade_returns.append(ret)

                    if ret > 0:
                        winning_trades += 1
                    else:
                        losing_trades += 1
                    i += 2
                else:
                    i += 1

            total_trades = winning_trades + losing_trades
            win_rate = winning_trades / total_trades if total_trades > 0 else 0.0
            avg_trade_return = sum(trade_returns) / len(trade_returns) if trade_returns else 0.0
            total_return = sum(trade_returns)  # 簡化：總報酬
            sharpe_ratio = self._calculate_sharpe(trade_returns)
            max_drawdown = self._calculate_max_drawdown([ohlcv_filtered[0]["close"]] + [t.get("price", 0) for t in trades])

            result = BacktestResult(
                symbol=symbol,
                strategy=strategy_name,
                start_date=start_date,
                end_date=end_date,
                total_trades=total_trades,
                winning_trades=winning_trades,
                losing_trades=losing_trades,
                win_rate=win_rate,
                total_return=total_return,
                sharpe_ratio=sharpe_ratio,
                max_drawdown=max_drawdown,
                avg_trade_return=avg_trade_return
            )

            self.results.append(result)
            return result

        except Exception as e:
            logger.error(f"Backtest failed for {symbol} ({strategy_name}): {e}")
            raise

    def walk_forward_validation(
        self,
        symbol: str,
        strategies: list[str],
        test_period_days: int = 90
    ) -> dict:
        """
        Perform walk-forward validation: backtest on past 3 months vs recent 3 months.

        Args:
            symbol: Stock code
            strategies: List of strategy names (e.g., ["momentum", "reversal", "fundamental"])
            test_period_days: Days for each walk-forward period (default 90 = 3 months)

        Returns:
            {
                "symbol": "2330",
                "results": {
                    "momentum": {
                        "past_3mo": BacktestResult(...),
                        "recent_3mo": BacktestResult(...)
                    },
                    ...
                },
                "best_strategy": "momentum"  # 在最近 3 個月表現最佳的策略
            }
        """
        today = datetime.now()
        recent_end = today.strftime("%Y-%m-%d")
        recent_start = (today - timedelta(days=test_period_days)).strftime("%Y-%m-%d")
        past_end = (today - timedelta(days=test_period_days)).strftime("%Y-%m-%d")
        past_start = (today - timedelta(days=test_period_days * 2)).strftime("%Y-%m-%d")

        results = {}
        best_strategy = None
        best_sharpe = -float('inf')

        for strategy in strategies:
            try:
                past_result = self.backtest(symbol, strategy, past_start, past_end)
                recent_result = self.backtest(symbol, strategy, recent_start, recent_end)

                results[strategy] = {
                    "past_3mo": past_result,
                    "recent_3mo": recent_result
                }

                # 選擇最近 3 個月 Sharpe ratio 最高的策略
                if recent_result.sharpe_ratio > best_sharpe:
                    best_sharpe = recent_result.sharpe_ratio
                    best_strategy = strategy

            except Exception as e:
                logger.warning(f"Walk-forward validation failed for {strategy}: {e}")
                continue

        return {
            "symbol": symbol,
            "past_period": f"{past_start} to {past_end}",
            "recent_period": f"{recent_start} to {recent_end}",
            "results": results,
            "best_strategy": best_strategy
        }

    def _calculate_rsi(self, prices: list, period: int = 14) -> float:
        """Calculate RSI indicator (0-100)."""
        if len(prices) < period:
            return 50.0  # 資料不足，返回中立值

        gains = []
        losses = []

        for i in range(1, len(prices)):
            diff = prices[i] - prices[i-1]
            if diff > 0:
                gains.append(diff)
                losses.append(0)
            else:
                gains.append(0)
                losses.append(abs(diff))

        avg_gain = sum(gains[-period:]) / period
        avg_loss = sum(losses[-period:]) / period

        if avg_loss == 0:
            return 100.0

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return rsi

    def _calculate_sharpe(self, returns: list, risk_free_rate: float = 0.02) -> float:
        """Calculate Sharpe ratio."""
        if not returns or len(returns) < 2:
            return 0.0

        mean_return = sum(returns) / len(returns)
        variance = sum((r - mean_return) ** 2 for r in returns) / (len(returns) - 1)
        std_dev = variance ** 0.5

        if std_dev == 0:
            return 0.0

        return (mean_return - risk_free_rate) / std_dev

    def _calculate_max_drawdown(self, prices: list) -> float:
        """Calculate maximum drawdown (%)."""
        if len(prices) < 2:
            return 0.0

        max_price = prices[0]
        max_dd = 0.0

        for price in prices[1:]:
            if price > max_price:
                max_price = price
            dd = (max_price - price) / max_price * 100
            if dd > max_dd:
                max_dd = dd

        return max_dd
```

**驗收**：
- 檔案存在於指定路徑
- StockBacktester 類能被 import
- 沒有語法錯誤

---

## Task 2 — 建立單元測試 `tests/test_stock_backtest.py`

建立 3 個測試，驗證回測框架。

**檔案位置**：`tests/test_stock_backtest.py`

**測試內容**：

```python
"""Unit tests for stock backtesting framework."""
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime
from claw.research.stock_strategy import StockBacktester, BacktestResult


@pytest.mark.asyncio
async def test_backtest_returns_valid_result():
    """Test backtest execution and result structure."""
    backtester = StockBacktester()

    with patch("claw.research.stock_strategy.stock_fetch") as mock_fetch:
        mock_fetch.return_value = {
            "ohlcv": [
                {"date": f"2026-03-{i:02d}", "open": 598.0 + i, "high": 603.0 + i,
                 "low": 595.0 + i, "close": 600.0 + i, "volume": 17500000}
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

    with patch("claw.research.stock_strategy.stock_fetch") as mock_fetch:
        mock_fetch.return_value = {
            "ohlcv": [
                {"date": f"2026-{(i//30)+1:02d}-{(i%30)+1:02d}", "open": 598.0 + (i % 10),
                 "high": 603.0 + (i % 10), "low": 595.0 + (i % 10),
                 "close": 600.0 + (i % 10), "volume": 17500000}
                for i in range(0, 180)
            ]
        }

        result = backtester.walk_forward_validation(
            "2330",
            ["momentum", "reversal"],
            test_period_days=90
        )

        assert result["symbol"] == "2330"
        assert "results" in result
        assert len(result["results"]) > 0


@pytest.mark.asyncio
async def test_rsi_calculation():
    """Test RSI indicator calculation."""
    backtester = StockBacktester()
    prices = [44, 44.34, 44.09, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84, 46.08, 45.89, 46.03, 45.61, 46.28, 46.00, 46.00]

    rsi = backtester._calculate_rsi(prices)

    assert 0 <= rsi <= 100
```

**驗收**：
- 三個測試能成功執行
- 測試通過

---

## Task 3 — 執行測試

```bash
cd /home/martin/Desktop/claw-python-personal

# 執行回測測試
python -m pytest tests/test_stock_backtest.py -v

# 執行全部測試
python -m pytest tests/ -q --tb=short
```

**預期輸出**：
- `test_backtest_returns_valid_result` PASSED
- `test_walk_forward_validation` PASSED
- `test_rsi_calculation` PASSED
- 整體 `192 passed, 3 skipped`（新增 3 個測試）

---

## Task 4 — 驗證回測框架

```bash
python -c "
from claw.research.stock_strategy import StockBacktester, BacktestResult
backtester = StockBacktester()
print('✅ StockBacktester framework initialized successfully')
"
```

**預期輸出**：框架初始化成功

---

## 交付清單

完成後回報：

1. **新建的檔案絕對路徑**：
   - `/home/martin/Desktop/claw-python-personal/claw/research/stock_strategy.py`
   - `/home/martin/Desktop/claw-python-personal/tests/test_stock_backtest.py`

2. **pytest 最終輸出**（應為 192+ passed）

3. **遇到的問題和解決方式**

---

## 完成標準

✅ StockBacktester 類已實現
✅ backtest() 方法支援 3 個策略（momentum, reversal, fundamental）
✅ walk_forward_validation() 支援過去 3 個月 vs 最近 3 個月驗證
✅ BacktestResult 包含所有必要的指標（win_rate, sharpe_ratio, max_drawdown 等）
✅ 192+ tests pass, 0 failures
✅ 3 個單元測試通過

---

## 注意事項

- 回測邏輯目前為簡化版本（RSI 計算、交易信號），後續可優化
- Walk-forward 驗證使用硬編碼日期，實際應使用相對日期
- Sharpe ratio 和 max drawdown 計算可根據實際需要調整
- 策略參數（如 RSI 閾值）目前為常數，未來應該可配置
- 不要改動既有的 tools（只新增）

