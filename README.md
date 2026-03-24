# claw-python — OpenClaw Python Reimplementation + Taiwan Stock Analysis

> **當前狀態：Phase S7 完成 — 201 tests pass（6 skipped）| 完整文檔套件已交付**
> **硬體：** Jetson Orin Nano Super（8GB unified memory, JetPack 6）
> **最後更新：** 2026-03-23

---

## 項目概述

**claw-python** 是 OpenClaw 的完整 Python 復刻，添加 NemoClaw 企業安全層和台股分析系統。

### 核心特徵

✅ **28 個多功能工具** — 從基礎 bash 到高級股票分析
✅ **3 個通訊渠道** — Telegram、Slack、Discord（帶 Embed + File 支援）
✅ **2 個自動 Cron Job** — 晨報（08:00 weekdays）+ 週報（18:00 Friday）
✅ **完整台股分析系統** — 技術面 → 基本面 → 新聞情緒 → 策略回測
✅ **ResearchLoop A→C→B 框架** — 智能決策驗證
✅ **生產級別優化** — 記憶體快取、Jetson 優化、monitoring
✅ **企業安全層** — EgressPolicy 白名單、Docker 沙盒、seccomp

---

## 快速開始

### 需求

- Python 3.8+
- Docker（用於工具隔離）
- Jetson Orin Nano Super（或相容硬體）
- LLM Router（外部服務）

### 安裝

```bash
git clone https://github.com/yourusername/claw-python.git
cd claw-python

# 安裝依賴
pip install -e .

# 啟動伺服器
python -m claw.main
```

詳見 [DEPLOYMENT_GUIDE.md](docs/DEPLOYMENT_GUIDE.md)。

---

## 系統架構

```
┌─────────────────────────────────────────────────────────┐
│                   Telegram / Slack / Discord           │
└────────────────────────┬────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────┐
│              FastAPI Gateway + WebSocket                 │
│  POST /v1/chat | WS /ws | /admin/metrics                │
└────────────────────────┬────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────┐
│              AgentLoop (Tool Dispatch)                   │
│  Memory Recall | Tool Call | Context Compaction         │
└───────┬──────────────┬──────────────┬────────────────────┘
        │              │              │
        ▼              ▼              ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│  28 工具      │ │ ResearchLoop │ │  CronService  │
│ (bash/search  │ │ (A→C→B eval) │ │ (晨報/週報)  │
│  /stock/etc)  │ │              │ │              │
└──────────────┘ └──────────────┘ └──────────────┘
        │              │              │
        └──────────────┼──────────────┘
                       ▼
        ┌──────────────────────────┐
        │  LLM Router (HTTP API)   │
        │ /v1/chat/completions     │
        │ /v1/embeddings           │
        │ /v1/images/generations   │
        │ /mcp/messages (DDGS)     │
        └──────────────────────────┘
```

### 核心組件

| 組件 | 功能 | 位置 |
|---|---|---|
| **Gateway** | FastAPI HTTP/WS 端點 | `claw/core/gateway.py` |
| **AgentLoop** | 工具調度和上下文管理 | `claw/agent/loop.py` |
| **Memory** | 向量搜尋 + FTS5 (RRF 混合) | `claw/memory/` |
| **ResearchLoop** | A→C→B 自主研究框架 | `claw/research/loop.py` |
| **CronService** | 排程工作執行 | `claw/cron/service.py` |
| **EgressPolicy** | 安全白名單 | `claw/tools/policy.py` |
| **Stock Tools** | 28 個工具 (含 6 個股票工具) | `claw/tools/` |
| **Channels** | Telegram/Slack/Discord | `claw/channels/` |

---

## 功能清單

### 工具 (28 個)

#### 基礎工具
- `bash` — 執行 bash 命令（Docker 沙盒隔離）
- `search_web` — DDGS 搜尋（LLM-Router MCP）
- `web_fetch` — HTTP GET/POST 資料

#### 檔案工具
- `file_read`, `file_write`, `file_list`, `file_delete` — 工作區檔案管理

#### 記憶體工具
- `memory_save` — 向量 + FTS5 儲存
- `memory_search` — 語意搜尋

#### 研究工具
- `research_start`, `research_status`, `experiment_record` — 自主研究流程

#### 時間工具
- `cron_add`, `cron_list`, `cron_delete` — 排程管理

#### 生成工具
- `image_gen` — 圖片生成（Router /v1/images）

#### 瀏覽器工具
- `browser_navigate`, `browser_extract`, `browser_close` — Playwright 自動化

#### 多代理工具
- `sessions_send`, `sessions_spawn`, `sessions_list` — 會話管理

#### 股票工具（新增）
- `stock_fetch` — 拉取 OHLCV 資料
- `stock_analyze` — 技術指標計算
- `generate_chart` — K 線圖生成
- `stock_screen` — 篩選台灣50
- `stock_chip` — 籌碼分析
- `stock_news` — 新聞追蹤

### 通訊渠道 (3 個)

| 渠道 | 特徵 | 用途 |
|---|---|---|
| **Telegram** | 輪詢模式 | 個人用戶 |
| **Slack** | Socket Mode | 團隊協作 |
| **Discord** | Embed + File | 結構化報告 |

### Cron Job (2 個)

| 工作 | 排程 | 功能 |
|---|---|---|
| **晨報** | 08:00 weekdays | 篩選台灣50 + 推播 Discord |
| **週報** | 18:00 Friday | 策略驗證 A→C→B + 推播 Discord |

### Skills (2 個)

- **Taiwan Stock** — 股票查詢、分析、圖表生成
- **Stock Strategy** — 策略驗證、walk-forward 回測

---

## 文檔

- [部署指南](docs/DEPLOYMENT_GUIDE.md) — Jetson 部署和配置
- [API 參考](docs/API_REFERENCE.md) — 28 工具完整文檔
- [常見問題](docs/FAQ.md) — 17 常見問題和答案
- [架構設計](docs/ARCHITECTURE.md) — 系統設計和技術棧
- [文檔索引](docs/INDEX.md) — 完整文檔導航

---

## 系統要求和性能指標

| 指標 | 規格 |
|---|---|
| **測試** | 201 passed, 6 skipped, 0 failures |
| **記憶體** | ~500MB 基線 + 任務緩存（< 2GB） |
| **CPU** | Jetson 4 核（受限於 Docker 設定） |
| **磁盤** | ~500MB（不含模型） |
| **延遲** | 平均 125ms (p95 450ms) |
| **吞吐** | ~12 req/s (受 LLM Router 限制) |

---

## 路線圖

| Phase | 內容 | 狀態 |
|---|---|---|
| 1-14 | 核心系統 | ✅ |
| S0 | Discord Embed | ✅ |
| S1 | Stock Tools | ✅ |
| S2 | 晨報 Cron | ✅ |
| S3 | 新聞情緒 | ✅ |
| S4 | 策略回測 + 週報 | ✅ |
| S5 | 生產優化 | ✅ |
| S6 | 完整測試 | ✅ |
| **S7** | **文檔** | **✅ 完成** |
| S8+ | 後續擴展 | 規劃中 |

見 [ROADMAP.md](ROADMAP.md) 了解完整計劃。

---

## 授權和貢獻

MIT License. 貢獻歡迎！見 [CONTRIBUTING.md](CONTRIBUTING.md)。

---

## 聯絡方式

- Issues: https://github.com/yourusername/claw-python/issues
- Discussions: https://github.com/yourusername/claw-python/discussions

---

更多詳細文檔見 [`docs/`](docs/) 目錄。
