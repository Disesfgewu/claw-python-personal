# Phase S0-S4：台股分析系統完整規劃

> 發給：**Codex** (S0, S1a, S2b, S4a) + **Gemini** (S1b, S2a, S3, S4b)
> 當前狀態：174 tests passing（Phase 15 完成）
> 目標狀態：202+ tests + 台股分析系統全功能就位
> 耗時預估：11-13 天（可並行）

---

## 項目概述

這個 mega-phase 完整實現台股分析系統，從基礎工具層、到自動推播、再到策略驗證。

**最終成果**：
- ✅ 實時個股分析（Telegram/Discord）
- ✅ 自動晨報（08:00 台灣50 強勢股）
- ✅ 新聞追蹤 + 情緒分析
- ✅ 策略回測驗證（2025 Q1 vs 2026 Q1）
- ✅ 週報推送（18:00 週五）

---

## 分工計畫（並行執行）

### **Day 1: Phase S0（1-2 小時）— Codex**

**任務**：Discord Embed 擴充 + egress 白名單

**新建文件**：
- `claw/channels/discord.py` — 新增 4 個方法（send_embed, send_file, send_embed_with_file, send_to_channel_id）
- `tests/test_discord_embed.py` — 4 個新測試

**修改文件**：
- `config/default.yaml` — 新增 discord 頻道設定
- `config/egress_policy.yaml` — 新增 TWSE/Yahoo Finance 白名單
- `claw/core/config.py` — DiscordConfig 新增欄位

**目標**：174 → 178 tests

**Prompt 檔**：`docs/PHASE_S0_DISCORD.md`（待寫）

---

### **Day 2-3: Phase S1 並行（2-3 天）**

#### **S1a — Codex（3 小時）**
Stock Tools 核心邏輯

**新建文件**：
- `claw/models/stock_report.py` — 資料結構（TechnicalIndicators, FundamentalData, StockReport）
- `claw/tools/stock_tools.py` — 核心工具（stock_fetch, stock_analyze）
- `tests/test_stock_tools.py` — 2+ 個新測試

**修改文件**：
- `claw/tools/__init__.py`, `claw/main.py` — 新增 import
- `pyproject.toml` — 新增依賴（yfinance, ta, mplfinance）

**目標**：178 → 182 tests

**Prompt 檔**：`docs/PHASE_S1A_STOCK_TOOLS.md`（待寫）

---

#### **S1b — Gemini（2 小時）— 與 S1a 並行**
Chart Tools + Skill

**新建文件**：
- `claw/tools/chart_tools.py` — K 線圖生成（generate_candlestick_chart）
- `skills/taiwan-stock/SKILL.md` — 台股分析 Skill 定義
- `tests/test_chart_tools.py` — 1 個新測試

**修改文件**：
- `claw/tools/__init__.py`, `claw/main.py` — 新增 import

**目標**：182 → 184 tests

**Prompt 檔**：`docs/PHASE_S1B_CHART.md`（待寫）

---

### **Day 4: Phase S2 並行（2 天）**

#### **S2a — Gemini（2 小時）**
股票篩選 + 籌碼分析

**新增函數**：
- `stock_tools.py` 新增 `stock_screen()` — 台灣50 篩選
- `stock_tools.py` 新增 `stock_chip()` — 法人買賣超

**新建檔案**：
- `tests/test_stock_screen.py` — 2 個新測試

**目標**：184 → 186 tests

**Prompt 檔**：`docs/PHASE_S2A_SCREEN.md`（待寫）

---

#### **S2b — Codex（2 小時）— 與 S2a 並行**
晨報 Cron Job

**新建檔案**：
- `claw/cron/jobs/morning_report.py` — 晨報邏輯
- `tests/test_morning_report.py` — 1 個新測試

**修改檔案**：
- `claw/main.py` — 在 lifespan 中註冊 08:00 晨報 job

**目標**：186 → 187 tests

**Prompt 檔**：`docs/PHASE_S2B_CRON.md`（待寫）

---

### **Day 5: Phase S3（2-3 天）— Gemini**

新聞 + 情緒分析

**新增函數**：
- `stock_tools.py` 新增 `stock_news()` — DDGS 搜尋新聞
- 使用 LLM-Router chat 做情緒分類
- 在 `stock_analyze()` 中整合新聞欄位

**新建檔案**：
- `tests/test_stock_news.py` — 2 個新測試

**目標**：187 → 189 tests

**Prompt 檔**：`docs/PHASE_S3_NEWS.md`（待寫）

---

### **Day 6-7: Phase S4 並行（3 天）**

#### **S4a — Codex（3 小時）**
策略回測框架

**新建檔案**：
- `claw/research/stock_strategy.py` — StockBacktester 框架
- `tests/test_stock_backtest.py` — 3 個新測試

**功能**：
- `backtest(symbol, strategy_name, start_date, end_date)` — 回測 3 個月
- 計算 Sharpe、勝率、最大回撤
- Walk-forward 驗證支援（過去 3 月 vs 最近 3 月）

**目標**：189 → 192 tests

**Prompt 檔**：`docs/PHASE_S4A_BACKTEST.md`（待寫）

---

#### **S4b — Gemini（3 小時）— 與 S4a 並行**
ResearchLoop 整合 + 週報

**修改檔案**：
- `stock_strategy.py` 新增 ResearchLoop compatible interface
- `claw/main.py` — 在 lifespan 中註冊 18:00 週報 job

**新建檔案**：
- `claw/cron/jobs/weekly_report.py` — 週報邏輯
- `skills/stock-strategy/SKILL.md` — 策略驗證 Skill
- `tests/test_weekly_report.py` — 1 個新測試

**功能**：
- 使用 ResearchLoop 的 A→C→B 框架驗證策略
- 推送策略對比週報到 Discord

**目標**：192 → 202 tests

**Prompt 檔**：`docs/PHASE_S4B_RESEARCH.md`（待寫）

---

## 技術規範

### 資料源優先級
1. **TWSE 官方 API**（query.sse.com.tw）
2. **爬蟲備用**（ga642381/Taiwan-Stock-Crawler）
3. **Yahoo Finance**（fallback）

### 時間段設定
- **晨報**：每天 08:00（週一-五）
- **週報**：每週五 18:00
- **回測時段**：過去 3 月（e.g., 2025-03-01 ~ 2025-05-01）+ 最近 3 月（e.g., 2026-02-01 ~ 2026-04-01）

### egress 白名單
已在 Phase S0 中新增：
- query.sse.com.tw
- mds.twse.com.tw
- query1.finance.yahoo.com
- finance.yahoo.com

### Cron Job 設定
```python
# 晨報
schedule: "0 8 * * 1-5"
prompt: "執行台股晨報：掃台灣50強勢股"

# 週報
schedule: "0 18 * * 5"
prompt: "執行策略驗證週報：對比動能/反轉/基本面策略"
```

---

## 預期最終狀態

**測試**：202+ passed, 3 skipped, 0 failures

**功能**：
- ✅ 22 + 3 = 25 個工具（新增 stock_*, chart_*, stock_screen, stock_chip, stock_news）
- ✅ 2 個新 Skill（taiwan-stock, stock-strategy）
- ✅ 2 個新 Cron job（晨報、週報）
- ✅ 完整的台股分析系統

**檔案數**：
- 新增 25+ 個檔案
- 修改 5+ 個既有檔案
- 總計 ~2000 行新代碼

---

## 執行順序和依賴

```
Phase S0 (Codex) — 1-2h
  ↓
Phase S1a (Codex) + S1b (Gemini) — 並行 2-3h
  ↓
Phase S2a (Gemini) + S2b (Codex) — 並行 2h
  ↓
Phase S3 (Gemini) — 2-3h
  ↓
Phase S4a (Codex) + S4b (Gemini) — 並行 3h
  ↓
完成（202+ tests）
```

---

## 下一步

PM 現在開始寫所有 8 個 Prompt 檔案（S0-S4），然後並行派給 Codex 和 Gemini。

