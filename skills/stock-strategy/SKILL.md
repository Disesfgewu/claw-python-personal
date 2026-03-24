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
