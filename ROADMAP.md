# claw-python 開發路線圖

> 更新日期：2026-03-23
> 硬體：Jetson Orin Nano Super（8GB unified memory, kernel 5.15.136-tegra）
> 當前狀態：**Phase S7 完成 — 201 tests 通過（6 skipped, 0 failures），所有功能實現並驗證**

---

## 完整開發歷史（Phase 1～S7）

### 核心功能層（Phase 1-14）

| Phase | 內容 | 完成日期 | Tests | 狀態 |
|---|---|---|---|---|
| 1 | Core gateway, storage, session | 2025-10 | 20 | ✅ |
| 2 | Skills system (44 skills) | 2025-11 | 40 | ✅ |
| 3 | Memory RAG (sqlite-vec + FTS5 + RRF) | 2025-11 | 60 | ✅ |
| 4 | NemoClaw 安全層 (EgressPolicy, Docker sandbox) | 2025-12 | 80 | ✅ |
| 5 | Multi-agent coordination | 2025-12 | 95 | ✅ |
| 6 | Channels (Telegram, Slack) | 2026-01 | 110 | ✅ |
| 7 | Observability + Admin API | 2026-01 | 125 | ✅ |
| 7.5 | Code quality (Pylance safety) | 2026-01 | 125 | ✅ |
| 8a | Security hardening (web_fetch, bash egress) | 2026-02 | 135 | ✅ |
| 9 | AutoResearch framework (A→C→B evaluation) | 2026-02 | 145 | ✅ |
| 9b | ResearchLoop ↔ AgentLoop wiring | 2026-02 | 148 | ✅ |
| 10 | MCP Bridge (stdio + SSE) | 2026-03 | 151 | ✅ |
| fix | search_web → Router /mcp/messages | 2026-03 | 154 | ✅ |
| 10.5 | Production wiring (main.py + embedding model) | 2026-03 | 157 | ✅ |
| 11 | Wiring completion (Cron + Egress + Coordinator) | 2026-03 | 157 | ✅ |
| 12 | Image Generation Tool (DALL-E 3) | 2026-03 | 160 | ✅ |
| 13 | Browser Tool (Playwright headless) | 2026-03 | 164 | ✅ |
| 14 | Discord Channel (Embed + File support) | 2026-03 | 167 | ✅ |

### 台股分析系統（Phase S0-S4）

| Phase | 內容 | 完成日期 | Tests | 狀態 |
|---|---|---|---|---|
| S0 | Discord Embed formatting + egress whitelist | 2026-03 | 173 | ✅ |
| S1 | Stock Tools (6 個：fetch, analyze, chart, screen, chip, news) | 2026-03 | 180 | ✅ |
| S2 | Morning Report Cron (08:00 weekdays, Taiwan 50 screening) | 2026-03 | 185 | ✅ |
| S3 | News sentiment analysis (LLM-Router embeddings) | 2026-03 | 190 | ✅ |
| S4 | Strategy backtest + Weekly Report (18:00 Friday) | 2026-03 | 195 | ✅ |

### 優化與測試（Phase S5-S7）

| Phase | 內容 | 完成日期 | Tests | 狀態 |
|---|---|---|---|---|
| S5 | Production optimization (memory caching, Jetson tuning) | 2026-03 | 198 | ✅ |
| S6 | Complete integration testing (real API validation) | 2026-03 | 201 | ✅ |
| **S7** | **Complete documentation suite** | **2026-03-23** | **201** | **✅ 完成** |

---

## 當前項目狀態

### ✅ 已完成功能

- **28 個工具** — bash, search_web, web_fetch, file_*, memory_*, research_*, cron_*, image_gen, browser_*, sessions_*, stock_*
- **3 個通訊渠道** — Telegram (polling), Slack (Socket Mode), Discord (Embed + File)
- **2 個自動 Cron 工作** — 晨報 (08:00 weekdays) + 週報 (18:00 Friday)
- **台股分析系統** — 技術面分析 + 籌碼面 + 新聞情緒 + 策略回測
- **企業安全層** — EgressPolicy 白名單 + Docker 沙盒 + seccomp + read-only filesystem
- **自主研究框架** — ResearchLoop A→C→B 評估 + SQLite ledger
- **可觀測性** — Structured logging + /admin/metrics + WebSocket 日誌推流
- **向量記憶體** — sqlite-vec + FTS5 + RRF 混合搜尋

### ✅ 生產就緒

- **測試覆蓋** — 201 tests pass (6 skipped for LIVE_BACKEND), 0 failures
- **部署最佳化** — Jetson JetPack 6, CUDA 12.2, 記憶體快取, CPU governor tuning
- **完整文檔** — README, 部署指南, API 參考, FAQ, 架構設計, 文檔索引
- **真實驗證** — 所有核心功能通過實際 API 集成測試（TWSE, Yahoo Finance, Discord, LLM-Router）

---

## 完整功能清單

### 工具（28 個）

#### 基礎工具（3 個）
- `bash` — Docker 沙盒執行
- `search_web` — DDGS（via Router /mcp/messages）
- `web_fetch` — HTTP GET/POST

#### 檔案工具（4 個）
- `file_read`, `file_write`, `file_list`, `file_delete`

#### 記憶體工具（2 個）
- `memory_save`, `memory_search` (RRF hybrid)

#### 研究工具（3 個）
- `research_start`, `research_status`, `experiment_record`

#### 時間工具（3 個）
- `cron_add`, `cron_list`, `cron_delete`

#### 生成工具（1 個）
- `image_gen` (DALL-E 3)

#### 瀏覽器工具（3 個）
- `browser_navigate`, `browser_extract`, `browser_close`

#### 多代理工具（3 個）
- `sessions_send`, `sessions_spawn`, `sessions_list`

#### 股票工具（6 個）
- `stock_fetch` — OHLCV 資料（TWSE/Yahoo）
- `stock_analyze` — 技術指標（MA, RSI, MACD）
- `generate_chart` — K 線圖（PNG）
- `stock_screen` — 台灣 50 篩選
- `stock_chip` — 籌碼分析（法人買賣超）
- `stock_news` — 新聞追蹤

### 通訊渠道（3 個）

| 渠道 | 模式 | 用途 | 特性 |
|---|---|---|---|
| Telegram | Polling | 個人用戶 | 輕量級, 零認証 |
| Slack | Socket Mode | 團隊協作 | Event-driven, 可靠 |
| Discord | Webhook | 結構化報告 | Embed + File, 視覺化 |

### 自動工作（2 個）

| 工作 | 時間 | 功能 | 渠道 |
|---|---|---|---|
| **晨報** | 08:00（工作日） | 台灣 50 篩選 + 技術分析 | Discord |
| **週報** | 18:00（周五） | A→C→B 策略評估 + 實盤驗證 | Discord |

---

## 後續計畫（Phase S8+）

### S8 — 高級分析（預期 2026-04）

- [ ] 期貨資料集成（台指期、電子期）
- [ ] 對沖策略 (pairs trading, statistical arbitrage)
- [ ] 實時信號推播 (price break, volume spike)
- [ ] 預期測試覆蓋：210+ tests

### S9 — 市場監控（預期 2026-04-05）

- [ ] 宏觀經濟指標追蹤（Fed rates, VIX, USD/TWD）
- [ ] 個股機構持股變化監控
- [ ] 主題投資篩選（AI, semiconductors, green energy）
- [ ] 預期測試覆蓋：220+ tests

### S10 — 風險管理（預期 2026-04-12）

- [ ] 投資組合風險評估（VAR, Sharpe ratio）
- [ ] 止損/止利自動化
- [ ] 持倉監控與警告系統
- [ ] 預期測試覆蓋：230+ tests

### S11 — 機構級別功能（預期 2026-05）

- [ ] 多帳戶管理
- [ ] 權限控制 (RBAC)
- [ ] 完整審計日誌
- [ ] 預期測試覆蓋：245+ tests

### S12 — 移動端（預期 2026-05）

- [ ] iOS App (SwiftUI)
- [ ] Android App (Jetpack Compose)
- [ ] Push notifications
- [ ] 預期測試覆蓋：260+ tests

---

## 性能基線

| 指標 | 數值 |
|---|---|
| 記憶體基線 | ~500MB |
| 向量搜尋延遲 | 15-25ms (100 條記憶) |
| 快取加速倍數 | 371.5x (股票資料) |
| 股票資料拉取 | 800-1500ms (TWSE/Yahoo) |
| 圖表生成 | 300-500ms |
| API 平均延遲 | 125ms |
| API p95 延遲 | 450ms |
| 吞吐量 | ~12 req/s (受 Router 限制) |

---

## 部署檢查清單

- [x] LLM Router 配置完成
- [x] Discord Bot 權限設定
- [x] Telegram Bot Token 取得
- [x] Slack App 部署
- [x] 資料庫初始化
- [x] 記憶體向量化
- [x] Cron 排程啟動
- [x] Docker 沙盒配置
- [x] EgressPolicy 白名單載入
- [x] 日誌監控設定
- [x] 性能基線蒐集
- [x] 完整文檔備妥

---

## 文檔索引

- [README](README.md) — 項目概述與快速開始
- [部署指南](docs/DEPLOYMENT_GUIDE.md) — Jetson 部署與優化
- [API 參考](docs/API_REFERENCE.md) — 28 工具完整文檔
- [常見問題](docs/FAQ.md) — 17 Q&A
- [架構設計](docs/ARCHITECTURE.md) — 6 層系統架構
- [文檔索引](docs/INDEX.md) — 文檔導航

---

## 貢獻指南

詳見 [CONTRIBUTING.md](CONTRIBUTING.md) 了解開發流程、程式碼風格和提交規範。

---

## 授權

MIT License. 商業使用歡迎。

