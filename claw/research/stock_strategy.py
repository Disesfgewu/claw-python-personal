"""Stock strategy backtesting framework."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

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
        """
        from claw.tools.stock_tools import stock_fetch_data_sync

        try:
            # 計算回測期間
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            end_dt = datetime.strptime(end_date, "%Y-%m-%d")
            period_days = (end_dt - start_dt).days

            # 拉取歷史資料
            fetch_result = stock_fetch_data_sync(symbol, period="1y")
            ohlcv = fetch_result.get("ohlcv", []) if isinstance(fetch_result, dict) else []

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
                close = candle.get("close", 0)

                if strategy_name == "momentum":
                    recent = ohlcv_filtered[max(0, i-14):i+1]
                    rsi = self._calculate_rsi([c.get("close", 0) for c in recent])

                    if rsi > 60 and position is None:
                        position = close
                        trades.append({"type": "buy", "price": close, "date": candle.get("date")})
                    elif rsi < 40 and position is not None:
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


class StockStrategyExecutor:
    """Execute and evaluate stock strategies for research workflows."""

    def __init__(self):
        self.backtester = StockBacktester()

    async def execute(self, prompt: str, context: dict | None = None) -> dict:
        """Run strategy verification and return summary metrics."""
        ctx = context or {}
        symbol = ctx.get("symbol")
        period_days = ctx.get("period_days", 90)
        if not symbol:
            return {
                "status": "failed",
                "reason": "symbol missing",
            }

        try:
            results = self.backtester.walk_forward_validation(
                symbol,
                ["momentum", "reversal", "fundamental"],
                test_period_days=period_days,
            )
            best_strategy = results.get("best_strategy") or "momentum"
            recent_result = results.get("results", {}).get(best_strategy, {}).get("recent_3mo")

            return {
                "status": "success",
                "symbol": symbol,
                "winner": best_strategy,
                "winner_sharpe": getattr(recent_result, "sharpe_ratio", 0.0),
                "winner_win_rate": getattr(recent_result, "win_rate", 0.0),
            }
        except Exception as e:
            logger.warning("Strategy execution failed for %s: %s", symbol, e)
            return {
                "status": "failed",
                "symbol": symbol,
                "reason": str(e),
            }

    async def evaluate(self, result: dict) -> dict:
        """Evaluate strategy results and return validation signal."""
        if result.get("status") != "success":
            return {"is_valid": False, "confidence": 0.0}

        sharpe = float(result.get("winner_sharpe", 0.0) or 0.0)
        win_rate = float(result.get("winner_win_rate", 0.0) or 0.0)
        confidence = max(0.0, min(1.0, (sharpe / 2.0) + (win_rate / 2.0)))
        is_valid = sharpe > 0 and win_rate >= 0.5
        return {
            "is_valid": is_valid,
            "confidence": confidence,
        }
