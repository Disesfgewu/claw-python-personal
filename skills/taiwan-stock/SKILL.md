---
name: taiwan-stock
display: "台股分析"
description: "Real-time analysis of Taiwan stocks (TWSE symbols)"
author: "Claw AI"
version: "1.0"
---

# 台股分析技能

用於分析台灣股市個股，提供技術面、基本面、圖表三合一服務。

## 觸發方式

用戶可以使用以下自然語言觸發此技能：
- "分析台積電"
- "查詢 2330 股價"
- "給我台灣50強勢股的圖表"
- "分析鴻海（2498）的技術面"

## 系統流程

1. **識別股票代碼** — 從使用者輸入提取股票代碼（例如 2330、2498）或公司名稱
2. **拉取資料** — 調用 `stock_fetch` 工具
3. **技術分析** — 調用 `stock_analyze` 工具
4. **生成圖表** — 調用 `generate_chart` 工具
5. **整合報告** — 組合上述結果成 Discord Embed 或純文字回應

## 可用工具

- `stock_fetch_tool` — 拉取 OHLCV 資料
- `stock_analyze_tool` — 計算技術指標
- `generate_chart_tool` — 生成 K 線圖

## 使用範例

### 範例 1：基本股價查詢
```
用戶：分析台積電
系統：調用 stock_fetch("2330") → stock_analyze("2330") → 返回技術分析報告
```

### 範例 2：帶圖表的完整分析
```
用戶：我想看台積電的 3 個月走勢圖
系統：
  1. stock_fetch("2330", "3mo")
  2. stock_analyze("2330", ohlcv)
  3. generate_chart_tool("2330", "3mo")
  4. 組合成 Discord Embed（圖表作為附檔）
```

## 支援的股票代碼範圍

- **台灣上市公司**：任何在 TWSE 上市的股票（例如 2330, 2498, 1101, 3034 等）
- **資料源優先級**：TWSE → Yahoo Finance

## 預期輸出

```json
{
  "symbol": "2330",
  "name": "台積電",
  "current_price": 600.0,
  "change_percent": 1.5,
  "technical_summary": "RSI 過高，賣壓增加",
  "chart_url": "<base64 PNG>"
}
```

## 技術限制

- 只支援中文台灣股票代碼（4 碼數字）
- 數據延遲可能 15-30 分鐘（取決於資料源）
- 圖表預設顯示最近 3 個月走勢

## 後續整合點

- **Phase S2a**：篩選功能（stock_screen） → 找出台灣50強勢股
- **Phase S3**：新聞追蹤 (stock_news) → 加入新聞事件標記
- **Phase S4**：策略回測 (backtest) → 驗證分析的準確度
