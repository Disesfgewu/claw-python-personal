# 台股分析系統 — 完整分工計畫 (Phase S0-S4)

---

## 分工總表

| Phase | 任務 | 主要模組 | 分配 | 耗時 | 依賴 | 交付物 |
|---|---|---|---|---|---|---|
| **S0** | Discord Embed 擴充 + egress 白名單 | `discord.py`, `egress_policy.yaml` | **Codex** | 1-2h | 無 | 171 tests (+4) |
| **S1a** | stock_tools.py + 核心邏輯 | `stock_tools.py`, `stock_report.py` | **Codex** | 3h | S0 | 175 tests (+4) |
| **S1b** | chart_tools.py + Skill | `chart_tools.py`, `SKILL.md` | **Gemini** | 2h | S0 | 176 tests (+1) |
| **S2a** | stock_screen + stock_chip | 擴充 `stock_tools.py` | **Gemini** | 2h | S1 | 178 tests (+2) |
| **S2b** | 晨報 Cron job | `craw/cron/jobs/morning_report.py` | **Codex** | 2h | S1, S2a | 179 tests (+1) |
| **S3** | 新聞 + 情緒分析 | 擴充 `stock_tools.py` + LLM 調用 | **Gemini** | 2-3h | S2 | 181 tests (+2) |
| **S4a** | StockBacktester 框架 | `claw/research/stock_strategy.py` | **Codex** | 3h | S1 | 184 tests (+3) |
| **S4b** | ResearchLoop 整合 + 週報 | 擴充 `stock_strategy.py` + Cron | **Gemini** | 3h | S4a, S3 | 185 tests (+1) |

**總時程**：序列 9-10 天（若並行可縮至 5-6 天）

---

## 詳細分工

### Phase S0 — Codex (1-2 小時)

**任務**：
1. 擴充 `claw/channels/discord.py` 支援 Embed + File + `send_to_channel_id()`
2. 更新 `config/default.yaml` 加台股設定欄位
3. 更新 `config/egress_policy.yaml` 加台股資料源白名單
4. 新增 4 個單元測試

**Prompt 檔**：`PHASE_STOCK_S0_PROMPT_FOR_CODEX.md` ✅ (已寫)

**交付標準**：
- ✅ Discord Embed 可推送
- ✅ egress 規則正確載入
- ✅ 171 tests pass (167 → 171)

**驗收**：
```bash
python -m pytest tests/test_discord*.py -v
python -m pytest tests/ -q  # 應為 171 passed
```

---

### Phase S1a — Codex (3 小時)

**任務**：
實作 `claw/tools/stock_tools.py` 的核心邏輯
1. `stock_fetch(symbol, period)` — TWSE/Yahoo Finance 資料拉取
2. `stock_analyze(symbol, period)` — 技術 + 基本面分析
3. `_calculate_indicators()` 等輔助函數
4. 新增 2 個單元測試

需要裝新依賴：`yfinance`, `ta`, `mplfinance`

**交付標準**：
- ✅ `stock_fetch("2330", "3mo")` 回傳 OHLCV JSON
- ✅ `stock_analyze("2330")` 回傳完整報告（含 chart_base64）
- ✅ 175 tests pass (171 → 175)

**驗收**：
```bash
python -c "
import asyncio
from claw.tools.stock_tools import stock_analyze

result = asyncio.run(stock_analyze('2330'))
print('Analysis result length:', len(result))
assert '2330' in result
assert 'recommendation' in result
print('✅ stock_analyze works')
"
```

---

### Phase S1b — Gemini (2 小時)

**任務**：
實作 `claw/tools/chart_tools.py` + Skill
1. `generate_candlestick_chart()` — mplfinance 圖表生成
2. `generate_chart()` tool wrapper
3. 新增 `skills/taiwan-stock/SKILL.md`
4. 新增 1 個單元測試 (chart 生成測試)

**交付標準**：
- ✅ `generate_candlestick_chart()` 回傳有效的 PNG bytes
- ✅ SKILL.md 已建立
- ✅ 176 tests pass (175 → 176)

**驗收**：
```bash
python -m pytest tests/test_chart_tools.py -v
# 驗證 PNG 生成
python -c "
import asyncio
from claw.tools.chart_tools import generate_candlestick_chart
import pandas as pd

df = pd.DataFrame({
    'Open': [100]*10, 'High': [102]*10, 'Low': [98]*10, 'Close': [101]*10
}, index=pd.date_range('2026-01-01', periods=10))

png = asyncio.run(generate_candlestick_chart('2330', df, None))
assert len(png) > 1000  # 有效的 PNG 至少 1KB
print('✅ Chart generation works')
"
```

---

### Phase S2a — Gemini (2 小時)

**任務**：
擴充 `claw/tools/stock_tools.py` 新增選股 + 籌碼工具
1. `stock_screen(pool, criteria)` — 台灣50 篩選
2. `stock_chip(symbol)` — 法人、融資資料（用 TWSE API）
3. 新增 2 個單元測試

**交付標準**：
- ✅ `stock_screen("tw50")` 回傳符合條件的股票列表
- ✅ `stock_chip("2330")` 回傳法人資料
- ✅ 178 tests pass (176 → 178)

---

### Phase S2b — Codex (2 小時)

**任務**：
實作晨報 Cron job
1. 建立 `claw/cron/jobs/morning_report.py`
2. 在 `claw/main.py` lifespan 註冊 08:00 晨報 job
3. 晨報邏輯：掃台灣50 → 篩出強勢股 → 分析前5個 → 推 Discord Embed
4. 新增 1 個整合測試

**Cron 設定**：
```python
# 在 main.py lifespan 加入
await cron_service.register_job(
    schedule="0 8 * * 1-5",  # 08:00 週一至五
    prompt="執行台股晨報：掃台灣50強勢股並分析"
)
```

**交付標準**：
- ✅ 08:00 自動推晨報到 Discord
- ✅ Embed 格式正確
- ✅ 179 tests pass

**驗收**：
```bash
# 手動觸發晨報
python -c "
from claw.cron.jobs.morning_report import morning_report
import asyncio
result = asyncio.run(morning_report('agent:main'))
print(result)  # 應看到「已推送 X 支股票」之類的訊息
"
```

---

### Phase S3 — Gemini (2-3 小時)

**任務**：
新增新聞 + 情緒分析
1. 擴充 `stock_tools.py` 新增 `stock_news(symbol)` 工具
2. 用 `search_web` (DDGS) 搜尋新聞
3. 用 LLM-Router chat 做情緒分類
4. 在 `stock_analyze()` 中整合新聞欄位
5. 新增 2 個單元測試

**交付標準**：
- ✅ `stock_news("2330")` 回傳最近新聞 + 情緒
- ✅ `stock_analyze()` 現在包含 `sentiment_score` 欄位
- ✅ 建議會根據情緒調整
- ✅ 181 tests pass (179 → 181)

---

### Phase S4a — Codex (3 小時)

**任務**：
實作股票策略回測框架
1. 建立 `claw/research/stock_strategy.py`
2. 實作 `StockBacktester` class（walk-forward 驗證）
3. 支援多策略回測：「動能」、「反轉」、「基本面」
4. 計算 Sharpe、勝率、最大回撤
5. 新增 3 個單元測試

**數據源**：
用 Phase S1 的 `stock_fetch()` 拿歷史資料

**支援的時間段** (根據需求)：
- 過去時段回測：2025-03-01 ~ 2025-05-01（3 個月）
- 最近時段驗證：2026-02-01 ~ 2026-04-01（3 個月）
- Walk-forward：自動計算子期間

**交付標準**：
- ✅ `backtest("2330", "動能", start_date, end_date)` 回傳 BacktestResult
- ✅ 支援多策略對比
- ✅ 184 tests pass (181 → 184)

```python
# 回測結果格式
BacktestResult = {
    "strategy": "動能",
    "symbol": "2330",
    "period": "2025-03-01 ~ 2025-05-01",
    "total_return": 0.425,  # 42.5%
    "sharpe_ratio": 1.42,
    "win_rate": 0.68,  # 68%
    "max_drawdown": -0.123,  # -12.3%
    "trades": 15,
    "winning_trades": 10,
}
```

---

### Phase S4b — Gemini (3 小時)

**任務**：
ResearchLoop 整合 + 週報
1. 擴充 `stock_strategy.py` 新增 `ResearchLoop` compatible interface
2. 建立 SKILL.md for stock strategy research
3. 實作週報 Cron job (18:00 週五)
4. 週報推送 3 策略對比 + 推薦
5. 新增 1 個整合測試

**ResearchLoop 流程**：
```
Plan: 定義策略（「動能策略：20日新高 + RSI<30」）
  ↓
Execute: 用 StockBacktester 在 2025 Q1 回測
  ↓
Evaluate: 比較 2025 Q1 vs 2026 Q1 performance，看是否穩定
  ↓
Iterate: 調整參數，重複 A→C→B 5 次
  ↓
Output: 推週報 Embed 到 Discord
```

**交付標準**：
- ✅ `research_start("驗證動能策略")` 自動跑 A→C→B 驗證
- ✅ 18:00 自動推週報
- ✅ Embed 包含 3 策略對比表
- ✅ 185 tests pass (184 → 185)

**驗收**：
```bash
# 手動觸發週報
python -c "
from claw.cron.jobs.weekly_report import weekly_report
import asyncio
result = asyncio.run(weekly_report('agent:main'))
print(result)  # 應看到「已推送週報」
"
```

---

## 並行策略

**快速路徑（5-6 天）：**

```
Day 1: S0 (Codex) —完全獨立
Day 2: S1a (Codex) | S1b (Gemini) —並行
Day 3: S2a (Gemini) | S2b (Codex) —並行
Day 4: S3 (Gemini) —等 S2 完成
Day 5: S4a (Codex) —等 S1 完成
Day 6: S4b (Gemini) —等 S4a + S3 完成
```

**最早各 Phase 可開始時間**：
- S0: Day 1 開始
- S1a: S0 完成後立即開始
- S1b: S0 完成後立即開始（與 S1a 並行）
- S2a: S1 完成後開始
- S2b: S1 完成後開始（與 S2a 並行）
- S3: S2 完成後開始
- S4a: S1 完成後開始（可與 S2/S3 並行）
- S4b: S4a + S3 都完成後開始

---

## Prompt 檔案清單

| Phase | Prompt 檔名 | 發給 | 狀態 |
|---|---|---|---|
| S0 | `PHASE_STOCK_S0_PROMPT_FOR_CODEX.md` | Codex | ✅ 已寫 |
| S1a | `PHASE_STOCK_S1A_PROMPT_FOR_CODEX.md` | Codex | ⏳ 待寫 |
| S1b | `PHASE_STOCK_S1B_PROMPT_FOR_GEMINI.md` | Gemini | ⏳ 待寫 |
| S2a | `PHASE_STOCK_S2A_PROMPT_FOR_GEMINI.md` | Gemini | ⏳ 待寫 |
| S2b | `PHASE_STOCK_S2B_PROMPT_FOR_CODEX.md` | Codex | ⏳ 待寫 |
| S3 | `PHASE_STOCK_S3_PROMPT_FOR_GEMINI.md` | Gemini | ⏳ 待寫 |
| S4a | `PHASE_STOCK_S4A_PROMPT_FOR_CODEX.md` | Codex | ⏳ 待寫 |
| S4b | `PHASE_STOCK_S4B_PROMPT_FOR_GEMINI.md` | Gemini | ⏳ 待寫 |

---

## 質量把控

每個 Phase 交付時：

1. ✅ pytest 通過（新增測試數符合預期）
2. ✅ 伺服器啟動無錯誤
3. ✅ 實際功能驗證（手動測試或整合測試）
4. ✅ Code review（檢查是否符合項目風格）
5. ✅ Commit（每個 Phase 一個 commit）

---

## 時程表

| 日期 | 任務 | 狀態 |
|---|---|---|
| **Day 1** | S0 | ⏳ 待 Codex |
| **Day 2** | S1a + S1b (並行) | ⏳ 待 Codex/Gemini |
| **Day 3** | S2a + S2b (並行) | ⏳ 待 Gemini/Codex |
| **Day 4** | S3 | ⏳ 待 Gemini |
| **Day 5** | S4a | ⏳ 待 Codex |
| **Day 6** | S4b | ⏳ 待 Gemini |
| **Day 7+** | 測試 + 修 bug | ⏳ 持續 |

---

## 最終成果

完成 Phase S0-S4 後：

✅ **功能面**：
- 實時個股分析（Telegram/Discord）
- 自動晨報（08:00 台灣50）
- 自動新聞追蹤（包含情緒分析）
- 自動策略驗證（週五 18:00 週報）

✅ **測試面**：
- 185+ tests pass (from 167)
- 0 failures
- 完整的單元測試覆蓋

✅ **部署面**：
- 生產級別 Cron 任務
- Discord 推播完整（Embed + 圖表）
- egress 安全白名單

---

## 下一步

確認無誤後，馬上開始 **Phase S0**。Codex 準備好了嗎？
