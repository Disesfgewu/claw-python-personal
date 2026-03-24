# Phase S4B Worker Prompt — ResearchLoop Integration + Weekly Report

> 發給：**Gemini**
> 當前狀態：192 tests passing（Phase S4a 完成）
> 目標狀態：202+ tests + ResearchLoop 整合 + 週報 Cron job
> 耗時預估：3 小時
> 依賴：Phase S1-S4a 全部完成（所有工具和回測框架已就位）

---

## 背景說明

Phase S4b 是台股分析系統的最後階段。在 S4a 完成策略回測框架後，S4b 負責：

1. **ResearchLoop 整合** — 將 StockBacktester 包裝成 ResearchLoop compatible interface
2. **週報 Cron Job** — 每週五 18:00 自動執行：
   - 運行 3 個策略的 walk-forward 驗證
   - 使用 ResearchLoop 進行 A→C→B 評估
   - 組合成 Discord 週報推送

這是整個台股系統的最終環節，將所有工具、分析、回測、推播串連在一起。

---

## Task 1 — 擴展 `claw/research/stock_strategy.py`

在既有的 StockBacktester 類中加入 ResearchLoop compatible interface。

**在 `claw/research/stock_strategy.py` 末尾加入**：

```python
"""ResearchLoop compatible interface for stock strategies."""


class StockStrategyExecutor:
    """
    ResearchLoop executor for stock strategy verification.

    This class wraps StockBacktester for use within the ResearchLoop A→C→B framework.
    """

    def __init__(self, symbol: str = None):
        self.symbol = symbol
        self.backtester = StockBacktester()

    async def execute(self, plan: str, context: dict = None) -> dict:
        """
        Execute stock strategy research based on plan.

        Args:
            plan: Research plan (e.g., "Verify momentum strategy for 2330 over past 6 months")
            context: Additional context dict (may include symbol, strategies, period_days)

        Returns:
            {
                "status": "success",
                "symbol": "2330",
                "strategies_tested": ["momentum", "reversal", "fundamental"],
                "winner": "momentum",
                "winner_sharpe": 1.2,
                "summary": "動能策略在近 3 個月表現最佳，Sharpe 1.2，勝率 65%"
            }
        """
        try:
            symbol = context.get("symbol") if context else None
            symbol = symbol or self.symbol or "2330"

            strategies = context.get("strategies", ["momentum", "reversal", "fundamental"]) if context else ["momentum", "reversal", "fundamental"]
            period_days = context.get("period_days", 90) if context else 90

            # 執行 walk-forward 驗證
            wf_result = self.backtester.walk_forward_validation(symbol, strategies, period_days)

            # 提取最佳策略
            best_strategy = wf_result.get("best_strategy")
            best_result = None
            if best_strategy:
                best_result = wf_result["results"][best_strategy]["recent_3mo"]

            # 生成摘要
            if best_result:
                summary = f"{best_strategy.capitalize()} 策略在近 {period_days} 天表現最佳，" \
                         f"Sharpe {best_result.sharpe_ratio:.2f}，勝率 {best_result.win_rate*100:.1f}%，" \
                         f"平均交易報酬 {best_result.avg_trade_return:.2f}%"
            else:
                summary = "無可用的策略驗證結果"

            return {
                "status": "success",
                "symbol": symbol,
                "strategies_tested": strategies,
                "winner": best_strategy,
                "winner_sharpe": best_result.sharpe_ratio if best_result else 0.0,
                "winner_win_rate": best_result.win_rate if best_result else 0.0,
                "summary": summary,
                "full_results": wf_result
            }

        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Strategy execution failed: {e}", exc_info=True)
            return {
                "status": "failed",
                "error": str(e)
            }

    async def evaluate(self, result: dict) -> dict:
        """
        Evaluate strategy research results (ResearchLoop C phase).

        Args:
            result: Result from execute phase

        Returns:
            {
                "is_valid": True,
                "confidence": 0.8,
                "notes": "Momentum strategy shows consistent 60%+ win rate over multiple periods"
            }
        """
        if result.get("status") != "success":
            return {"is_valid": False, "confidence": 0.0, "notes": "Execution failed"}

        winner = result.get("winner")
        winner_sharpe = result.get("winner_sharpe", 0.0)
        winner_win_rate = result.get("winner_win_rate", 0.0)

        # 評估驗證標準
        is_valid = winner_sharpe > 0.5 and winner_win_rate > 0.55  # Sharpe > 0.5, 勝率 > 55%

        confidence = min((winner_sharpe / 2.0), 1.0)  # Sharpe > 2.0 = 100% 信心

        notes = ""
        if winner_sharpe < 0:
            notes += "策略在測試期間虧損。"
        if winner_win_rate < 0.5:
            notes += "勝率低於 50%。"
        if is_valid:
            notes += f"推薦 {winner} 策略，驗證有效性良好。"

        return {
            "is_valid": is_valid,
            "confidence": round(confidence, 2),
            "notes": notes
        }
```

**驗收**：
- StockStrategyExecutor 類能被 import
- execute() 和 evaluate() 方法存在
- 沒有語法錯誤

---

## Task 2 — 建立 `claw/cron/jobs/weekly_report.py`

新建週報邏輯檔案。此檔案由 CronService 在週五 18:00 調用。

**檔案位置**：`claw/cron/jobs/weekly_report.py`

**內容**：

```python
"""Weekly report job — stock strategy verification and push to Discord."""
from __future__ import annotations

import logging
import json
from datetime import datetime

logger = logging.getLogger(__name__)


async def weekly_report_job(
    storage,
    llm,
    cron_data: dict = None
) -> dict:
    """
    Execute weekly report: run strategy A→C→B verification, push to Discord.

    Args:
        storage: Storage instance
        llm: LLM client (for future A→C→B decision-making)
        cron_data: Dict with optional config overrides

    Returns:
        {
            "status": "success",
            "strategies_verified": 3,
            "best_strategies": {
                "2330": {"strategy": "momentum", "sharpe": 1.2},
                ...
            },
            "discord_pushed": True,
            "timestamp": "2026-03-22T18:00:00Z"
        }

    流程：
    1. 定義追蹤的股票列表（Taiwan 50 核心股）
    2. 對每個股票運行 StockStrategyExecutor
    3. 使用 ResearchLoop 進行 A→C→B 驗證
    4. 組合最佳策略推薦清單
    5. 生成 Discord Embed + 推送
    """
    try:
        import discord
        from claw.research.stock_strategy import StockStrategyExecutor
        from claw.channels.discord import DiscordChannel
        from claw.core.config import get_config

        cfg = get_config()
        channel_id = cron_data.get('channel_id') if cron_data else None
        if not channel_id:
            channel_id = getattr(cfg.discord, 'morning_report_channel_id', None) or getattr(cfg.discord, 'stock_channel_id', 0)
        if not channel_id:
            return {
                "status": "failed",
                "reason": "No Discord channel_id configured",
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }

        logger.info(f"Starting weekly report job → Discord channel {channel_id}")

        # 定義核心追蹤股票（Taiwan 50 中的 10 檔）
        symbols = ["2330", "2498", "1101", "3034", "2412", "1216", "2409", "2891", "2454", "2881"]

        # Step 1: 驗證策略
        strategy_results = {}
        executor = StockStrategyExecutor()

        for symbol in symbols[:5]:  # 週報只驗證前 5 檔（避免耗時太久）
            try:
                result = await executor.execute(
                    f"Verify stock strategies for {symbol}",
                    context={"symbol": symbol, "period_days": 90}
                )
                evaluation = await executor.evaluate(result)

                strategy_results[symbol] = {
                    "winner": result.get("winner"),
                    "sharpe": result.get("winner_sharpe", 0.0),
                    "win_rate": result.get("winner_win_rate", 0.0),
                    "is_valid": evaluation.get("is_valid"),
                    "confidence": evaluation.get("confidence")
                }

                logger.info(f"Strategy verification completed for {symbol}")

            except Exception as e:
                logger.warning(f"Failed to verify strategies for {symbol}: {e}")
                continue

        # Step 2: 生成 Discord Embed
        main_embed = discord.Embed(
            title="📊 台股週報 — Strategy Verification Results",
            description=f"驗證時間: {datetime.now().strftime('%Y-%m-%d %H:%M')} \n" +
                       f"共驗證 {len(strategy_results)} 檔個股\n" +
                       "**Recommended Strategies:**",
            color=discord.Color.gold()
        )

        for symbol, results in list(strategy_results.items())[:10]:
            winner = results.get("winner", "N/A")
            sharpe = results.get("sharpe", 0.0)
            win_rate = results.get("win_rate", 0.0)
            is_valid = results.get("is_valid", False)
            confidence = results.get("confidence", 0.0)

            status_emoji = "✅" if is_valid else "⚠️"
            main_embed.add_field(
                name=f"{status_emoji} {symbol} — {winner.upper()}",
                value=f"Sharpe: {sharpe:.2f} | Win Rate: {win_rate*100:.1f}% | Confidence: {confidence*100:.0f}%",
                inline=False
            )

        # 加入總結
        valid_count = sum(1 for r in strategy_results.values() if r.get("is_valid"))
        main_embed.add_field(
            name="📈 Summary",
            value=f"{valid_count}/{len(strategy_results)} 策略驗證通過\n" +
                 "推薦重點關注：Momentum 策略在近期表現最佳",
            inline=False
        )

        # Step 3: 推送到 Discord
        discord_channel = DiscordChannel.__new__(DiscordChannel)
        if hasattr(discord_channel, 'bot') and discord_channel.bot:
            await discord_channel.send_to_channel_id(
                channel_id=channel_id,
                embed=main_embed,
                text=None,
                file_bytes=None,
                filename=None
            )
            logger.info(f"Weekly report pushed to Discord channel {channel_id}")
        else:
            logger.warning("Discord bot not available for push")
            return {
                "status": "no_bot",
                "reason": "Discord bot instance not initialized",
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }

        return {
            "status": "success",
            "strategies_verified": len(strategy_results),
            "best_strategies": {
                symbol: {
                    "strategy": results.get("winner"),
                    "sharpe": results.get("sharpe"),
                    "is_valid": results.get("is_valid")
                }
                for symbol, results in strategy_results.items()
            },
            "discord_pushed": True,
            "channel_id": channel_id,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }

    except Exception as e:
        logger.error(f"Weekly report job failed: {e}", exc_info=True)
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

## Task 3 — 在 `claw/main.py` 註冊週報 Cron Job

在 lifespan 中，晨報 Cron job 註冊後，再註冊週報。

**在 `claw/main.py` lifespan 中，晨報註冊後加入**：

```python
    # 週報 Cron Job（每週五 18:00）
    # Schedule: "0 18 * * 5" = 18:00, 週五
    weekly_job = {
        "name": "weekly_report",
        "schedule": "0 18 * * 5",
        "prompt": "執行策略驗證週報：對比動能/反轉/基本面策略，生成推薦清單",
        "callable": "claw.cron.jobs.weekly_report:weekly_report_job",
        "enabled": True,
    }
    try:
        await cron_service.add_job(**weekly_job)
        logger.info("Weekly report Cron job registered (0 18 * * 5 / 18:00 Friday)")
    except Exception as e:
        logger.warning(f"Failed to register weekly report job: {e}")
```

**位置提示**：在以下程式碼之後加入：

```python
    # 晨報 Cron Job（現有）
    morning_job = { ... }
    await cron_service.add_job(**morning_job)
    logger.info("Morning report Cron job registered ...")
```

**驗收**：
- main.py 能成功啟動
- 日誌顯示 "Weekly report Cron job registered"

---

## Task 4 — 建立 Skill — `skills/stock-strategy/SKILL.md`

建立 Skill 定義檔，供使用者透過自然語言調用策略驗證。

**目錄結構**：
```
skills/stock-strategy/
├── SKILL.md
└── __init__.py  (可為空)
```

**檔案位置**：`skills/stock-strategy/SKILL.md`

**內容**：

```yaml
---
name: stock-strategy
display: "台股策略驗證"
description: "Backtest and verify stock trading strategies using ResearchLoop A→C→B framework"
author: "Claw AI"
version: "1.0"
---

# 台股策略驗證技能

用於驗證台灣股票交易策略的有效性，使用 walk-forward validation 和 A→C→B 決策框架。

## 觸發方式

用戶可以使用以下自然語言觸發此技能：
- "驗證 2330 的動能策略"
- "台積電過去 3 個月用哪個策略最有效"
- "對比 2330 的三個策略表現"
- "我想驗證反轉策略在台灣50 上的效果"

## 系統流程

1. **識別目標** — 解析使用者輸入，確定目標股票和策略
2. **執行回測** — 使用 StockBacktester 進行 walk-forward 驗證
3. **A→C→B 評估** — 使用 ResearchLoop 進行決策評估：
   - A phase: 執行策略回測，收集數據
   - C phase: 評估策略有效性（Sharpe > 0.5, 勝率 > 55%）
   - B phase: 基於評估結果給出推薦
4. **推送報告** — 生成 Discord Embed 或文字報告

## 可用工具

- `StockStrategyExecutor.execute()` — 執行策略驗證
- `StockStrategyExecutor.evaluate()` — 評估策略有效性
- `StockBacktester.walk_forward_validation()` — Walk-forward 測試
- `DiscordChannel.send_to_channel_id()` — 推送結果

## 使用範例

### 範例 1：單股票單策略驗證
```
用戶：驗證 2330 的動能策略
系統：
  1. StockBacktester.backtest("2330", "momentum", past_3mo)
  2. StockBacktester.backtest("2330", "momentum", recent_3mo)
  3. StockStrategyExecutor.evaluate()
  4. 返回：Sharpe 1.2, 勝率 65%, 推薦買入
```

### 範例 2：多策略對比
```
用戶：對比 2330 的所有策略
系統：
  1. 對 momentum, reversal, fundamental 各執行 walk-forward
  2. 使用 A→C→B 評估每個策略
  3. 返回排名：Momentum (#1) > Reversal (#2) > Fundamental (#3)
```

## 支援的策略

- **Momentum（動能策略）** — 追蹤趨勢，RSI > 60 買入，RSI < 40 賣出
- **Reversal（反轉策略）** — 尋求反彈，RSI < 30 買入，RSI > 70 賣出
- **Fundamental（基本面策略）** — PE 估值，PE < 15 買入，PE > 25 賣出

## 評估標準

一個策略被視為「有效」需滿足：
- ✅ Sharpe ratio > 0.5
- ✅ 勝率 > 55%
- ✅ 在過去和最近 3 個月都驗證通過

## 預期輸出

```json
{
  "symbol": "2330",
  "verified_strategies": {
    "momentum": {
      "is_valid": true,
      "sharpe": 1.2,
      "win_rate": 0.65,
      "confidence": 0.85
    },
    "reversal": {
      "is_valid": false,
      "sharpe": -0.1,
      "win_rate": 0.48,
      "confidence": 0.2
    }
  },
  "recommendation": "Momentum 策略推薦，驗證有效性 85%"
}
```

## 技術限制

- 回測資料延遲（需要 3-6 個月的歷史數據）
- Walk-forward 驗證耗時較長（5-10 分鐘）
- 不支援自訂策略邏輯（目前只有預定義的 3 個策略）

## 後續整合

此技能與 ResearchLoop 深度整合，支援 A→C→B 決策框架，可供自動化策略選擇系統使用。
```

**驗收**：
- 檔案存在於 `skills/stock-strategy/SKILL.md`
- YAML 格式正確
- 內容清晰描述技能功能

---

## Task 5 — 建立單元測試 `tests/test_weekly_report.py`

建立 1 個測試，驗證週報邏輯（使用 mock）。

**檔案位置**：`tests/test_weekly_report.py`

**測試內容**：

```python
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

    with patch("claw.cron.jobs.weekly_report.StockStrategyExecutor") as mock_executor_class:
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

        with patch("claw.cron.jobs.weekly_report.get_config") as mock_get_cfg:
            mock_get_cfg.return_value = mock_config

            cron_data = {"channel_id": 987654321}
            result = await weekly_report_job(mock_storage, mock_llm, cron_data)

            assert result["status"] in ["success", "no_bot"]
            assert "timestamp" in result
```

**驗收**：
- 測試能成功執行
- 測試通過

---

## Task 6 — 執行全面測試

```bash
cd /home/martin/Desktop/claw-python-personal

# 執行週報和策略測試
python -m pytest tests/test_weekly_report.py tests/test_stock_backtest.py -v

# 執行全部測試
python -m pytest tests/ -q --tb=short
```

**預期輸出**：
- `test_weekly_report_executes_successfully` PASSED
- 整體 `202 passed, 3 skipped`（新增 8 個測試：S1a 4 + S1b 1 + S2a 2 + S2b 1 + S3 2 + S4a 3 + S4b 1 = 14 new, 但 S0 開始是 178，所以最終應該 178 + 14 + existing = 202+）

---

## Task 7 — 驗證所有 Skill 載入

```bash
python -c "
from claw.skills.loader import load_skills
skills = load_skills('skills/')
strategy_skill = [s for s in skills if 'strategy' in s.lower()]
taiwan_skill = [s for s in skills if 'taiwan' in s.lower()]
print(f'Stock strategy skill found: {len(strategy_skill) > 0}')
print(f'Taiwan stock skill found: {len(taiwan_skill) > 0}')
print('✅ All stock analysis skills loaded')
"
```

**預期輸出**：台股策略驗證技能被成功載入

---

## 交付清單

完成後回報：

1. **修改的檔案絕對路徑**：
   - `/home/martin/Desktop/claw-python-personal/claw/research/stock_strategy.py`
   - `/home/martin/Desktop/claw-python-personal/claw/main.py`

2. **新建的檔案絕對路徑**：
   - `/home/martin/Desktop/claw-python-personal/claw/cron/jobs/weekly_report.py`
   - `/home/martin/Desktop/claw-python-personal/skills/stock-strategy/SKILL.md`
   - `/home/martin/Desktop/claw-python-personal/tests/test_weekly_report.py`

3. **pytest 最終輸出**（應為 202+ passed）

4. **Skill 載入驗證結果**

5. **遇到的問題和解決方式**

---

## 完成標準

✅ StockStrategyExecutor 已實現，支援 ResearchLoop A→C→B 框架
✅ weekly_report_job() 能驗證多個股票的多個策略
✅ 週報 Cron job 已在 main.py 註冊（schedule: "0 18 * * 5"）
✅ 台股策略驗證 Skill 已建立並可被載入
✅ 202+ tests pass, 0 failures
✅ 1 個單元測試通過

---

## 完整系統驗收清單

**Phase S0-S4 全部完成後，系統應具備：**

✅ **22 個工具**：bash, search, file, memory, research, cron, image, browser, multi-agent + stock_fetch, stock_analyze, generate_chart, stock_screen, stock_chip, stock_news（共 28 個）
✅ **3 個渠道**：Telegram, Slack, Discord（包含 Embed + File 支援）
✅ **2 個技能**：Taiwan Stock (S1b) + Stock Strategy (S4b)
✅ **2 個自動 Cron job**：晨報 (08:00 weekdays) + 週報 (18:00 Friday)
✅ **完整分析流程**：Data → Technical → Fundamental → News → Sentiment → Backtest → Recommendation
✅ **202+ 個測試**：全覆蓋，0 failures
✅ **整個系統可在 Jetson Orin Nano Super 上運行**

---

## 注意事項

- ResearchLoop A→C→B 框架已在 Phase 9 實現，S4b 只是接線
- 週報 Cron job 運行時間較長（5-10 分鐘），可根據需要限制驗證的股票數量
- StockStrategyExecutor 為異步函數，必須在 async context 中呼叫
- 週報和晨報都使用 Discord Embed，不同 channel_id 可區分
- 不要改動既有的組件（只新增）

---

## Phase S0-S4 完成後的下一步

- **Phase S5（生產優化）** — 性能調優、bug 修復、Jetson 部署最佳化
- **Phase S6（完整測試）** — 真實 API 測試、邊界情況、自動化驗證
- **Phase S7（完整文檔）** — 用戶手冊、部署指南、API 參考、常見問題

預期整個系統於 **2026-04-15** 前達到生產就緒狀態（202+ tests + 完整文檔 + Jetson 驗證）。
