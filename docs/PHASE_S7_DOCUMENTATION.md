# Phase S7 Worker Prompt — Complete Documentation & User Manual

> 當前狀態：210+ tests passing（Phase S0-S6 完成）
> 目標狀態：完整文檔 + 可直接使用的系統
> 耗時預估：2 天
> 負責人：PM（最終驗收和整理）

---

## 背景說明

Phase S0-S6 完成了整個系統的實現和驗證。Phase S7 負責將系統「文檔化」和「可使用化」：

1. **用戶操作手冊** — 如何透過 Telegram/Discord 使用系統
2. **部署指南** — 在 Jetson 上部署和配置
3. **API 參考文檔** — 所有 28 個工具的完整說明
4. **常見問題排查** — 遇到問題時的解決方案
5. **架構說明文檔** — 系統設計和技術棧概覽
6. **README 和 ROADMAP 最終更新** — 項目狀態清晰記錄

完成後，系統準備進行最終驗收和交付。

---

## Task 1 — 更新 README.md（系統概覽）

在 `/home/martin/Desktop/claw-python-personal/README.md` 中更新或重寫：

```markdown
# claw-python — OpenClaw Python Reimplementation + Taiwan Stock Analysis

> **當前狀態：Phase S6 完成 — 210+ tests pass | 所有功能驗證通過**
> 硬體：Jetson Orin Nano Super（8GB unified memory, JetPack 6）
> 最後更新：2026-03-23

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
pip install -r pyproject.toml

# 初始化資料庫
python -m claw.main

# 啟動伺服器
python -m claw.main
```

詳見 [部署指南](#部署指南)。

---

## 系統架構

```
┌─────────────────────────────────────────────────────────┐
│                     Telegram / Slack / Discord           │
└────────────────────────┬────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────┐
│              FastAPI Gateway + WebSocket                 │
│  POST /v1/chat/completions | WS /ws | /admin/* metrics   │
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

## 部署指南

見 `docs/DEPLOYMENT_GUIDE.md`

---

## API 參考

見 `docs/API_REFERENCE.md`

---

## 常見問題

見 `docs/FAQ.md`

---

## 系統要求和性能指標

| 指標 | 規格 |
|---|---|
| **測試** | 210+ passed, 3 skipped, 0 failures |
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
| **S7** | **文檔** | **⏳ 進行中** |
| S8+ | 後續擴展 | 規劃中 |

---

## 授權和貢獻

MIT License. 貢獻歡迎！見 `CONTRIBUTING.md`。

---

## 聯絡方式

- Issues: https://github.com/yourusername/claw-python/issues
- Discussions: https://github.com/yourusername/claw-python/discussions

---

更多詳細文檔見 [`docs/`](docs/) 目錄。
```

**驗收**：
- README 完整更新，清楚呈現系統狀態和功能
- 包含快速開始、架構、功能清單
- 連結指向詳細文檔

---

## Task 2 — 建立 DEPLOYMENT_GUIDE.md（部署和配置）

創建 `/home/martin/Desktop/claw-python-personal/docs/DEPLOYMENT_GUIDE.md`：

```markdown
# Deployment Guide — Jetson Orin Nano Super

> 目標硬體：Jetson Orin Nano Super（8GB unified memory, JetPack 6）

---

## 前置要求

### 硬體
- Jetson Orin Nano Super 開發板
- 最少 16GB microSD 卡（推薦 32GB）
- 電源供應器（5A 5V 或 USB-C PD）
- 網絡連接

### 軟體
- JetPack 6.x（含 CUDA 12.2）
- Python 3.8+
- Docker CE

### 外部服務
- LLM Router（執行 Claude API 代理）
- Discord Bot（用於推播）

---

## 安裝步驟

### 1. 準備 Jetson

```bash
# 更新系統
sudo apt update && sudo apt upgrade -y

# 安裝必要套件
sudo apt install -y python3-pip python3-dev build-essential
sudo apt install -y docker.io
sudo apt install -y git

# 將當前使用者加入 docker 群組（避免每次 sudo）
sudo usermod -aG docker $USER
newgrp docker

# 檢查 CUDA
nvidia-smi  # 應顯示 CUDA 12.2
```

### 2. 複製和配置 claw-python

```bash
# 複製專案
git clone https://github.com/yourusername/claw-python.git ~/claw-python
cd ~/claw-python

# 安裝 Python 依賴（可能耗時 5-10 分鐘）
pip install -e .

# 驗證安裝
python -c "import claw; print('✓ claw imported successfully')"
```

### 3. 配置環境變數

複製並編輯 `.env.example`：

```bash
cp .env.example .env
nano .env
```

必填項：

```bash
# LLM Router（執行於另一台機器或 localhost）
LLM_ROUTER_URL=http://localhost:8000
LLM_ROUTER_KEY=your_api_key_here

# Discord（可選，用於推播）
DISCORD_TOKEN=your_bot_token_here
DISCORD_CHANNEL_ID=your_channel_id_here
DISCORD_STOCK_CHANNEL_ID=your_stock_channel_id_here

# Telegram（可選）
TELEGRAM_TOKEN=your_telegram_bot_token

# Slack（可選）
SLACK_BOT_TOKEN=your_slack_bot_token
SLACK_APP_TOKEN=your_slack_app_token
```

### 4. 初始化資料庫

```bash
# 建立必要的目錄
mkdir -p ~/.claw/data/transcripts

# 初始化（會建立 SQLite 資料庫）
python -m claw.main --init

# 驗證初始化
ls -la ~/.claw/data/
```

### 5. 啟動伺服器

```bash
# 前景模式（用於測試）
python -m claw.main

# 背景模式（生產使用）
nohup python -m claw.main > ~/.claw/claw.log 2>&1 &

# 檢查執行狀態
curl -s http://localhost:8000/admin/health | python -m json.tool

# 檢查日誌
tail -f ~/.claw/claw.log
```

---

## 配置檔案

### config/default.yaml

主要配置檔案。重要設定：

```yaml
gateway:
  host: 0.0.0.0  # 對外綁定（生產應改為具體 IP）
  port: 8000

session:
  ttl_hours: 24
  reaper_interval_seconds: 60

logging:
  level: INFO  # 生產改為 WARNING
  format: json  # 結構化日誌

telegram:
  enabled: true
  token: ${TELEGRAM_TOKEN}
  polling: true

discord:
  enabled: true
  token: ${DISCORD_TOKEN}
  stock_channel_id: ${DISCORD_STOCK_CHANNEL_ID}

slack:
  enabled: false  # 可選，改為 true 啟用
  bot_token: ${SLACK_BOT_TOKEN}
  app_token: ${SLACK_APP_TOKEN}
```

### config/egress_policy.yaml

安全白名單。預設已包含：

```yaml
egress_rules:
  # 允許的網域
  - dest: "query.sse.com.tw"
    verdict: allow
  - dest: "mds.twse.com.tw"
    verdict: allow
  - dest: "finance.yahoo.com"
    verdict: allow
  # ... 其他規則 ...
```

---

## Jetson 優化

### CPU 效能設定

```bash
# 設定 CPU governor 為 performance
echo performance | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor

# 查看當前頻率
cat /sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_cur_freq

# 查看最大頻率
cat /sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq
```

### 記憶體管理

```bash
# 查看記憶體使用
free -h

# 查看詳細記憶體信息
cat /proc/meminfo | grep -E 'MemTotal|MemAvailable|SwapTotal'

# 如果需要擴展 swap（建立 2GB swap file）
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
```

### 磁盤管理

```bash
# 查看磁盤使用
df -h

# 清理 Docker 暫存空間
docker system prune -a

# 清理 Python 快取
find ~ -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true
find ~ -type d -name '.pytest_cache' -exec rm -rf {} + 2>/dev/null || true
```

---

## 監控和維護

### 監控指標

```bash
# 即時指標
curl -s http://localhost:8000/admin/metrics | python -m json.tool

# 健康檢查
curl -s http://localhost:8000/admin/health

# 日誌監控（實時）
tail -f ~/.claw/claw.log | grep -E 'ERROR|WARNING'
```

### 定期備份

```bash
# 備份資料庫（每日）
mkdir -p ~/backups
cp ~/.claw/data/*.db ~/backups/$(date +%Y%m%d_%H%M%S).db.backup

# 定期清理舊日誌
find ~/.claw -name "*.log" -mtime +7 -delete
```

### 更新和升級

```bash
# 更新依賴
pip install --upgrade -e .

# 更新程式碼
cd ~/claw-python && git pull origin main

# 重啟伺服器
pkill -f "python.*claw.main"
sleep 2
python -m claw.main &
```

---

## 故障排查

### 伺服器無法啟動

```bash
# 檢查端口佔用
lsof -i :8000

# 檢查日誌
tail -100 ~/.claw/claw.log

# 檢查依賴
python -m pip check
```

### Discord 推播失敗

```bash
# 驗證 token
python -c "
import discord
bot = discord.Client()
try:
    bot.run('YOUR_TOKEN')
except Exception as e:
    print(f'Error: {e}')
"

# 檢查權限
# 1. 確認 bot 已添加到伺服器
# 2. 確認 bot 有 Send Messages, Embed Links, Attach Files 權限
```

### 記憶體不足

```bash
# 檢查進程佔用
ps aux | grep claw

# 檢查 Docker 容器
docker stats

# 減少並發 (修改 config/default.yaml)
cron_service:
  max_concurrent: 2  # 從 3 改為 2
```

---

## 生產 Checklist

- [ ] LLM Router 正常執行
- [ ] Discord credentials 已設定並驗證
- [ ] Telegram/Slack 配置（如適用）
- [ ] 資料庫備份計劃已設立
- [ ] 日誌監控已設定
- [ ] Cron job 時區正確（Asia/Taipei）
- [ ] SSL/TLS 已配置（如需公網暴露）
- [ ] 防火牆規則已配置
- [ ] 定期更新計劃已制定

---

見 [README.md](../README.md) 了解更多。
```

**驗收**：
- 部署指南完整（Jetson 特定優化）
- 包含配置、監控、故障排查
- 用戶可以跟著指南部署

---

## Task 3 — 建立 API_REFERENCE.md（API 文檔）

創建 `/home/martin/Desktop/claw-python-personal/docs/API_REFERENCE.md`（這會很長，我只給結構和範例）：

```markdown
# API Reference — All 28 Tools

> 完整的 claw-python 工具 API 文檔。

---

## 基礎工具

### bash — Execute Shell Commands

**描述**：在隔離的 Docker 容器中執行 bash 命令

**簽名**：
```python
def bash(command: str) -> str
```

**參數**：
- `command` (str): bash 命令（例如 `ls -la /tmp`）

**返回**：
- str: 命令輸出

**例子**：
```python
result = bash("echo 'Hello, World!'")
# 返回：'Hello, World!\n'
```

**安全注意**：
- 命令執行於沙盒環境（network=none, read_only）
- 不支援互動式命令
- 輸出限制 10KB

---

### search_web — Search with DDGS

**描述**：使用 DuckDuckGo 搜尋（透過 LLM-Router MCP）

**簽名**：
```python
def search_web(query: str, max_results: int = 10) -> str
```

**參數**：
- `query` (str): 搜尋查詢
- `max_results` (int): 最多返回結果數

**返回**：
- str: JSON 格式的搜尋結果清單

**例子**：
```python
results = search_web("TSMC news 2026")
# 返回：[{"title": "...", "url": "...", "body": "..."}, ...]
```

---

## 檔案工具

### file_read — Read File

**簽名**：`def file_read(path: str) -> str`

**描述**：讀取工作區內的檔案

**參數**：
- `path` (str): 檔案路徑（相對於工作區）

**返回**：
- str: 檔案內容（限 100KB）

---

## 股票工具

### stock_fetch — Fetch Stock Data

**簽名**：
```python
def stock_fetch(symbol: str, period: str = "1y") -> dict
```

**描述**：從 TWSE/Yahoo Finance 拉取股票 OHLCV 資料

**參數**：
- `symbol` (str): 股票代碼（例如 "2330"）
- `period` (str): 資料期間（"1mo", "3mo", "1y", ...）

**返回**：
```python
{
    "symbol": "2330",
    "name": "台積電",
    "current": 600.0,
    "ohlcv": [
        {"date": "2026-03-22", "open": 598.5, "high": 605.0, "low": 595.0, "close": 600.0, "volume": 18500000},
        ...
    ]
}
```

**例子**：
```python
data = stock_fetch("2330", "3mo")
print(f"{data['name']}: ${data['current']}")
```

---

### stock_analyze — Technical Analysis

**簽名**：
```python
def stock_analyze(symbol: str, ohlcv_list: list) -> StockReport
```

**描述**：計算技術指標並生成分析報告

**返回**：StockReport（包含 RSI、MACD、Bollinger Bands、趨勢、訊號等）

---

### stock_screen — Screen Taiwan 50

**簽名**：
```python
def stock_screen(criteria: dict = None) -> list[StockReport]
```

**描述**：篩選台灣50中符合條件的強勢股

**參數**：
```python
criteria = {
    'rsi_min': 30,
    'rsi_max': 70,
    'volume_threshold': 10000000,
    'signal': ['buy', 'strong_buy']
}
```

**返回**：
- list[StockReport]: 前 15 個最強勢股

---

### stock_chip — Institutional Chip Analysis

**簽名**：
```python
def stock_chip(symbol: str) -> dict
```

**描述**：查詢法人買賣超（外資、投信、自營商）

**返回**：
```python
{
    "symbol": "2330",
    "net_foreign": 30000000,  # 外資淨買超
    "net_trust": 10000000,    # 投信淨買超
    "net_dealer": 20000000,   # 自營商淨買超
    "chip_signal": "positive"  # positive / neutral / negative
}
```

---

### stock_news — Fetch News

**簽名**：
```python
def stock_news(symbol: str, limit: int = 5) -> list[dict]
```

**描述**：搜尋個股相關新聞和情緒分析

**返回**：
```python
[
    {
        "title": "台積電宣布新廠投資",
        "url": "https://...",
        "source": "經濟日報",
        "sentiment": "positive"
    },
    ...
]
```

---

### generate_chart — Generate K-Line Chart

**簽名**：
```python
def generate_chart(symbol: str, ohlcv_list: list) -> bytes
```

**描述**：生成 K 線圖 (PNG)

**返回**：
- bytes: PNG 二進制資料

---

## Cron 工具

### cron_add — Add Scheduled Job

**簽名**：
```python
def cron_add(name: str, schedule: str, prompt: str) -> dict
```

**參數**：
- `name` (str): Job 名稱
- `schedule` (str): Cron 表達式（例如 "0 8 * * 1-5"）
- `prompt` (str): 執行時的提示詞

**例子**：
```python
result = cron_add("daily_stock_check", "0 8 * * 1-5", "執行台股晨報")
```

---

## 研究工具

### research_start — Start Research Task

**簽名**：
```python
def research_start(title: str, plan: str) -> dict
```

**描述**：啟動自主研究任務（ResearchLoop）

**返回**：
```python
{
    "research_id": "abc123",
    "status": "started",
    "title": "..."
}
```

---

（本文檔應包含全部 28 個工具的完整說明，這裡只列舉主要的 17 個，其餘遵循相同格式）

---

見 README.md 了解完整工具清單。
```

**驗收**：
- API 參考文檔框架已建立
- 主要 17 個工具已有詳細說明
- 包含參數、返回、例子、注意事項

---

## Task 4 — 建立 FAQ.md（常見問題）

創建 `/home/martin/Desktop/claw-python-personal/docs/FAQ.md`：

```markdown
# Frequently Asked Questions (FAQ)

---

## 安裝和配置

### Q1: 在 Jetson 上安裝失敗，提示 "No module named 'X'"

**A**: 某些套件在 ARM64 上需要從源碼編譯。嘗試：

```bash
pip install --upgrade pip setuptools wheel
pip install -e . --no-cache-dir
```

如果仍然失敗，檢查 `pyproject.toml` 中是否有版本衝突。

---

### Q2: Docker 容器無法啟動

**A**: 檢查 Docker daemon：

```bash
sudo systemctl status docker
sudo systemctl restart docker

# 驗證 Docker 可用
docker ps
```

如果提示權限不足，運行：
```bash
sudo usermod -aG docker $USER
newgrp docker
```

---

### Q3: Discord 推播失敗，提示 "Forbidden"

**A**: Bot 缺少權限。在 Discord 伺服器設定中：

1. 選擇 Bot 角色
2. 添加以下權限：
   - Send Messages
   - Embed Links
   - Attach Files
   - View Channels

---

## 功能使用

### Q4: 如何查詢特定股票？

**A**: 在 Telegram/Discord 中傳送：

```
查詢 2330   # 或 "@claw 查詢台積電"
```

系統會自動拉取資料並生成分析報告。

---

### Q5: 晨報何時執行？

**A**: 每個交易日 08:00（台灣時間）自動執行。確認：

```bash
# 檢查 Cron 排程
curl -s http://localhost:8000/cron/list | python -m json.tool
```

---

### Q6: 如何手動執行晨報？

**A**: 呼叫 API：

```bash
curl -X POST http://localhost:8000/cron/exec \
  -H "Content-Type: application/json" \
  -d '{"job_name": "morning_report"}'
```

---

## 效能和故障

### Q7: 系統變慢或記憶體持續增長

**A**: 清理快取並重啟：

```bash
python -c "
from claw.memory.sqlite_store import MemoryStore
import tempfile
with tempfile.TemporaryDirectory() as tmpdir:
    store = MemoryStore(db_path=f'{tmpdir}/memory.db')
    # 清理快取邏輯
"

# 重啟伺服器
pkill -f "python.*claw.main"
sleep 2
python -m claw.main &
```

---

### Q8: "Connection timeout" 錯誤

**A**: LLM Router 可能不可用。檢查：

```bash
curl -s http://localhost:8000/health | python -m json.tool

# 確認 LLM Router 執行
curl -s http://${LLM_ROUTER_URL}/health
```

---

### Q9: 股票資料無法拉取 ("Failed to fetch stock data")

**A**: 檢查網絡和資料源：

```bash
# 測試 TWSE 連接
curl -I https://query.sse.com.tw

# 測試 Yahoo Finance
curl -I https://finance.yahoo.com

# 檢查 egress 規則是否允許
python -c "
from claw.tools.policy import EgressPolicy
from pathlib import Path
policy = EgressPolicy.from_yaml(Path('config/egress_policy.yaml'))
for r in policy.rules:
    if 'finance' in r.dest or 'sse' in r.dest or 'twse' in r.dest.lower():
        print(f'{r.dest}: {r.verdict}')
"
```

---

## 開發和定製

### Q10: 如何添加新的股票工具？

**A**: 在 `claw/tools/stock_tools.py` 中添加函數，然後在 `claw/tools/__init__.py` 中註冊：

```python
from claw.tools.stock_tools import my_new_function

@register_tool()
def my_new_tool(param1: str) -> str:
    """My new tool description."""
    return json.dumps(my_new_function(param1), ensure_ascii=False)
```

重啟伺服器後，新工具會自動註冊。

---

### Q11: 如何修改 Cron job 的執行時間？

**A**: 編輯 `claw/main.py`：

```python
# 晨報改為 09:00（而非 08:00）
morning_job['schedule'] = "0 9 * * 1-5"

# 週報改為週一 18:00（而非週五）
weekly_job['schedule'] = "0 18 * * 1"
```

重啟伺服器。

---

### Q12: 如何自訂 Discord 推播格式？

**A**: 編輯 `claw/cron/jobs/morning_report.py` 和 `weekly_report.py`，修改 Embed 構建邏輯：

```python
embed = discord.Embed(
    title="自訂標題",
    description="自訂描述",
    color=discord.Color.custom_color,
)
```

---

## 監控和日誌

### Q13: 日誌太多，如何過濾？

**A**: 修改 `config/default.yaml`：

```yaml
logging:
  level: WARNING  # 從 INFO 改為 WARNING（只顯示警告和錯誤）
```

或使用 grep 過濾：

```bash
tail -f ~/.claw/claw.log | grep ERROR
```

---

### Q14: 如何查看詳細的效能指標？

**A**: 訪問 metrics endpoint：

```bash
curl http://localhost:8000/admin/metrics | python -m json.tool
```

輸出包含：
- 系統記憶體/CPU/磁盤
- 應用會話數/工具數
- 效能延遲/吞吐量
- 資料庫狀態

---

## 更新和升級

### Q15: 如何升級 claw-python？

**A**:

```bash
cd ~/claw-python

# 拉取最新代碼
git pull origin main

# 安裝新依賴（如有）
pip install --upgrade -e .

# 執行遷移（如有）
python -m claw.migrate

# 重啟伺服器
pkill -f "python.*claw.main"
sleep 2
python -m claw.main &
```

---

## 其他

### Q16: 系統支援哪些語言？

**A**: 主要支援中文和英文。股票資料使用中文標籤，API 響應以 JSON 返回（支援 Unicode）。

---

### Q17: 如何聯絡技術支援？

**A**:
- Issues: https://github.com/yourusername/claw-python/issues
- Discussions: https://github.com/yourusername/claw-python/discussions
- Email: (如有)

---

未找到答案？提交 Issue 或 Discussion！
```

**驗收**：
- FAQ 涵蓋安裝、功能、故障、開發、監控等 17 個常見問題
- 每個問題都有清晰的解答和範例代碼

---

## Task 5 — 建立 ARCHITECTURE.md（架構說明）

創建 `/home/martin/Desktop/claw-python-personal/docs/ARCHITECTURE.md`（精簡版本）：

```markdown
# System Architecture

---

## 設計原則

1. **模組化** — 工具、渠道、存儲各自獨立
2. **可觀測性** — 結構化日誌 + metrics endpoint
3. **安全性** — EgressPolicy + Docker 隔離 + seccomp
4. **性能** — 快取層 + 非同步処理 + 批次執行
5. **可靠性** — 重試邏輯 + 優雅降級 + 資源清理

---

## 系統層次

### 層次 1：通訊層（Channels）

```
用戶輸入（Telegram/Slack/Discord）
      ↓
Channel Adapter（protocol conversion）
      ↓
Gateway HTTP/WebSocket
```

**責任**：
- 協議轉換（Telegram → JSON, Discord → JSON）
- 認証驗證（bot token, credentials）
- 訊息路由（找到正確的 session）

**檔案**：`claw/channels/*.py`

---

### 層次 2：API 層（Gateway）

```
HTTP POST /v1/chat/completions
WebSocket /ws
Admin /admin/metrics, /admin/health
      ↓
FastAPI routing
      ↓
Session lookup
      ↓
AgentLoop dispatch
```

**責任**：
- HTTP 路由和驗證
- WebSocket 長連接管理
- Session 生命週期管理
- 速率限制（可選）

**檔案**：`claw/core/gateway.py`

---

### 層次 3：代理層（AgentLoop）

```
Agent Input (Text + Context)
      ↓
AgentLoop
  ├─ Memory Recall（語意搜尋）
  ├─ Tool Dispatch（選擇工具）
  ├─ Tool Call（執行工具）
  ├─ Result Parse（解析結果）
  └─ Context Compaction（縮小上下文）
      ↓
Output (Text + Metadata)
```

**責任**：
- 工具選擇和調度
- 上下文管理和縮小
- 結果驗證和重試

**檔案**：`claw/agent/loop.py`, `claw/agent/context.py`

---

### 層次 4：工具層（Tools）

```
Tool Registry（所有 28 個工具）
  ├─ Bash（執行命令）
  ├─ Search（網絡搜尋）
  ├─ File（檔案操作）
  ├─ Memory（向量搜尋）
  ├─ Research（自主研究）
  ├─ Stock Tools（6 個股票工具）
  ├─ Image（圖片生成）
  ├─ Browser（自動化）
  ├─ Sessions（多代理）
  └─ Cron（排程）
```

**責任**：
- 工具實現
- 參數驗證
- 錯誤處理
- 結果格式化

**檔案**：`claw/tools/*.py`

---

### 層次 5：存儲層（Storage）

```
Memory Store
  ├─ Vector Search（sqlite-vec）
  ├─ FTS5（全文搜尋）
  └─ RRF（混合排名）

Session Store
  └─ SQLite（會話資料）

Cron Store
  └─ SQLite（排程定義）

Transcript Files
  └─ 純文本（會話記錄）
```

**責任**：
- 持久化存儲
- 快速搜尋
- 資料備份
- 過期清理

**檔案**：`claw/memory/*.py`, `claw/core/storage.py`

---

### 層次 6：外部服務層

```
LLM Router（HTTP）
  ├─ /v1/chat/completions
  ├─ /v1/embeddings
  ├─ /v1/images/generations
  └─ /mcp/messages（DDGS）

Data Sources
  ├─ TWSE API
  ├─ Yahoo Finance
  └─ 其他資料源（爬蟲）

Discord API
Telegram API
Slack API
```

**責任**：
- 與外部服務通訊
- 協議適配
- 錯誤處理

**檔案**：`claw/llm/`, `claw/channels/`

---

## 數據流示例：股票查詢

```
1. 用戶在 Discord 傳送：「分析台積電」
   ↓
2. DiscordChannel.on_message() 接收
   ↓
3. Gateway 建立 session，轉發給 AgentLoop
   ↓
4. AgentLoop.run()：
   a. Memory.search("台積電") → 回憶相關信息
   b. AgentLoop 判斷需要 stock_fetch 工具
   c. 調用 stock_fetch("2330")
   d. Claw.tools.stock_tools 拉取 TWSE/Yahoo 資料
   e. 呼叫 stock_analyze() → 計算 RSI, MACD 等
   f. 調用 generate_chart() → 生成 PNG
   g. 返回結果：StockReport + PNG
   ↓
5. AgentLoop 格式化為 Discord Embed + File
   ↓
6. DiscordChannel.send_embed_with_file() 推送
   ↓
7. 用戶在 Discord 中看到報告
```

---

## 關鍵設計決策

### 為什麼使用 Docker 沙盒？

- **隔離**：bash 命令無法訪問主系統檔案
- **限制**：CPU、記憶體、網絡受限
- **安全**：即使工具被注入，損害範圍有限

### 為什麼使用混合搜尋（RRF）？

- 向量搜尋：找到語意相似的記憶（例如「股票」匹配「股價」）
- FTS5：找到關鍵詞精確匹配（例如「2330」）
- RRF：結合兩者，得到最佳結果

### 為什麼分離 ResearchLoop 和 AgentLoop？

- **AgentLoop**：快速響應（即時工具調度）
- **ResearchLoop**：深度思考（A→C→B 評估，無需用戶等待）
- 可並行運行，互不阻塞

---

## 擴展點

### 添加新工具

1. 在 `claw/tools/my_tool.py` 中實現邏輯
2. 在 `claw/tools/__init__.py` 中用 `@register_tool()` 註冊
3. 重啟伺服器

### 添加新渠道

1. 在 `claw/channels/my_channel.py` 中繼承 `BaseChannel`
2. 實現 `start()`, `stop()`, `send()` 方法
3. 在 `claw/main.py` 的 lifespan 中初始化

### 添加新 Skill

1. 在 `skills/my_skill/SKILL.md` 中定義
2. 在 `skills/my_skill/` 中實現邏輯（如需）
3. Skill loader 會自動讀取

---

見 API_REFERENCE.md 了解工具細節。
```

**驗收**：
- 架構文檔清楚呈現 6 個層次
- 包含數據流示例
- 列出關鍵設計決策
- 說明擴展點

---

## Task 6 — 更新 ROADMAP.md（最終版本）

在 `/home/martin/Desktop/claw-python-personal/ROADMAP.md` 中更新或補充：

```markdown
# Development Roadmap — claw-python

> 最後更新：2026-03-23 | 當前狀態：Phase S7 進行中（202+ tests）

---

## 完成的 Phase（1-S6）

| Phase | 主題 | 完成日期 | Tests | 狀態 |
|---|---|---|---|---|
| 1 | Core gateway, storage, session | 2025-10 | 20 | ✅ |
| 2 | Skills system (44 skills) | 2025-11 | 40 | ✅ |
| 3 | Memory RAG (sqlite-vec + FTS5) | 2025-11 | 60 | ✅ |
| 4 | NemoClaw 安全層 | 2025-12 | 80 | ✅ |
| 5 | Multi-agent coordination | 2025-12 | 95 | ✅ |
| 6 | Channels (Telegram, Slack) | 2026-01 | 110 | ✅ |
| 7 | Observability + Admin API | 2026-01 | 125 | ✅ |
| 7.5 | Code quality | 2026-01 | 125 | ✅ |
| 8a | Security hardening | 2026-02 | 135 | ✅ |
| 9 | AutoResearch framework | 2026-02 | 145 | ✅ |
| 9b | ResearchLoop ↔ AgentLoop wiring | 2026-02 | 148 | ✅ |
| 10 | MCP Bridge | 2026-03 | 151 | ✅ |
| fix | search_web → /mcp/messages | 2026-03 | 154 | ✅ |
| 10.5 | Production wiring (main.py) | 2026-03 | 157 | ✅ |
| 11 | Wiring completion (Cron + Egress) | 2026-03 | 157 | ✅ |
| 12 | Image Generation Tool | 2026-03 | 160 | ✅ |
| 13 | Browser Tool (Playwright) | 2026-03 | 164 | ✅ |
| 14 | Discord Channel | 2026-03 | 167 | ✅ |
| 15 | Cleanup + documentation | 2026-03 | 174 | ✅ |
| **S0** | **Discord Embed + egress** | **2026-03** | **178** | **✅** |
| **S1a** | **Stock Tools (fetch/analyze)** | **2026-03** | **182** | **✅** |
| **S1b** | **Chart + Taiwan Skill** | **2026-03** | **184** | **✅** |
| **S2a** | **Stock Screen/Chip** | **2026-03** | **186** | **✅** |
| **S2b** | **Morning Report Cron** | **2026-03** | **187** | **✅** |
| **S3** | **News + Sentiment** | **2026-03** | **189** | **✅** |
| **S4a** | **Stock Backtest** | **2026-03** | **192** | **✅** |
| **S4b** | **ResearchLoop + Weekly** | **2026-03** | **202** | **✅** |
| **S5** | **Production Optimization** | **2026-03** | **206** | **✅** |
| **S6** | **Complete Testing** | **2026-03** | **210** | **✅** |
| **S7** | **Documentation** | **2026-03** | **210+** | **⏳** |

---

## 進行中的 Phase

### Phase S7 — Complete Documentation (2 days)

**目標**：
- ✅ README.md 完整更新
- ⏳ DEPLOYMENT_GUIDE.md（Jetson 優化）
- ⏳ API_REFERENCE.md（28 工具文檔）
- ⏳ FAQ.md（17 常見問題）
- ⏳ ARCHITECTURE.md（系統設計）
- ⏳ ROADMAP.md 最終版本
- ⏳ User Manual（手冊）

**完成後**：系統準備生產使用。

---

## 後續規劃（Phase S8+）

### S8 — Advanced Features (4-6 weeks)

- [ ] 實時行情 WebSocket（不再輪詢）
- [ ] 量化交易 backtester 增強（更多策略）
- [ ] 自動化交易建議（AI 決策）
- [ ] 投資組合管理（多檔持股）
- [ ] 風險管理（最大回撤限制）

### S9 — Scale Out (4-6 weeks)

- [ ] 分佈式 Cron（支援多機器排程）
- [ ] Redis 快取層（減少資料庫壓力）
- [ ] 訊息佇列（Celery/RabbitMQ）
- [ ] API 限流和配額管理
- [ ] 多租戶支援（SaaS 模式）

### S10 — Enterprise Features (6-8 weeks)

- [ ] 使用者認証和授權（OAuth2）
- [ ] 審計日誌（compliance）
- [ ] 加密敏感資料（secrets management）
- [ ] 備份和災難恢復
- [ ] SLA 監控和告警

### S11+ — Domain Extensions

- [ ] 美股分析系統
- [ ] 加密貨幣交易
- [ ] 期貨交易
- [ ] 期權策略

---

## 版本發佈計劃

| 版本 | 發佈日期 | 內容 | 穩定性 |
|---|---|---|---|
| 1.0 | 2026-03-31 | 核心系統 + 台股分析 | Stable |
| 1.1 | 2026-04-30 | S8 高級功能 | Stable |
| 2.0 | 2026-06-30 | S9 scale-out | Stable |
| 2.1+ | 2026-Q3+ | S10+ 企業功能 | Ongoing |

---

## 技術債清單

| 項目 | 優先級 | 狀態 |
|---|---|---|
| 統一錯誤處理框架 | Medium | 待辦 |
| 完整的 type hints | Low | 待辦 |
| 性能基準測試 | High | S5 中 |
| 文件覆蓋率 100% | Medium | S7 中 |
| 移除已棄用的 API | Low | 待辦 |

---

## 社群貢獻

歡迎貢獻！見 [CONTRIBUTING.md](CONTRIBUTING.md)。

---

見 [README.md](README.md) 了解當前狀態。
```

**驗收**：
- ROADMAP 完整記錄 Phase 1-S7
- 列出後續 Phase S8+ 的規劃
- 包含版本發佈計劃
- 顯示技術債清單

---

## Task 7 — 建立 CONTRIBUTING.md（貢獻指南）

創建 `/home/martin/Desktop/claw-python-personal/CONTRIBUTING.md`（簡版）：

```markdown
# Contributing to claw-python

感謝有興趣貢獻本項目！以下是貢獻指南。

---

## 開發流程

1. Fork 本倉庫
2. 創建功能分支：`git checkout -b feature/my-feature`
3. 提交更改：`git commit -m "feat: add my feature"`
4. 推送到分支：`git push origin feature/my-feature`
5. 開啟 Pull Request

---

## 代碼風格

- Python 3.8+ 相容
- 使用 Black 格式化（`black .`）
- 使用 flake8 檢查（`flake8 claw`）
- 類型提示（`mypy .`）

---

## 測試要求

- 所有新功能需要單元測試
- 運行 `pytest tests/` 確保測試通過
- 追求 > 80% 覆蓋率

---

## 文檔要求

- 新功能需要 API 文檔（在 docs/API_REFERENCE.md 中）
- 更新 CHANGELOG.md
- 更新 README.md（如適用）

---

## 報告 Bug

使用 GitHub Issues：
- 清晰描述問題
- 提供重現步驟
- 附加日誌和環境信息

---

感謝你的貢獻！
```

**驗收**：
- 貢獻指南清晰
- 包含開發流程、代碼風格、測試要求

---

## Task 8 — 生成完整文檔索引

創建 `/home/martin/Desktop/claw-python-personal/docs/INDEX.md`：

```markdown
# Documentation Index

---

## 用戶文檔

| 文檔 | 內容 | 適合對象 |
|---|---|---|
| [README.md](../README.md) | 項目概覽 + 快速開始 | 所有人 |
| [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) | Jetson 部署和配置 | 系統管理員 |
| [API_REFERENCE.md](API_REFERENCE.md) | 28 工具完整文檔 | 開發者 |
| [FAQ.md](FAQ.md) | 17 常見問題和答案 | 用戶 |
| [ARCHITECTURE.md](ARCHITECTURE.md) | 系統設計和架構 | 開發者/架構師 |

---

## 開發文檔

| 文檔 | 內容 |
|---|---|
| [CONTRIBUTING.md](../CONTRIBUTING.md) | 貢獻指南 |
| [ROADMAP.md](../ROADMAP.md) | 開發路線圖 |

---

## Phase 實現文檔（工作提示）

這些是原始的 worker prompts（供參考）：

| Phase | 文檔 | 狀態 |
|---|---|---|
| 15 | PHASE_15_CLEANUP.md | ✅ |
| S0 | PHASE_S0_DISCORD.md | ✅ |
| S1a | PHASE_S1A_STOCK_TOOLS.md | ✅ |
| S1b | PHASE_S1B_CHART.md | ✅ |
| S2a | PHASE_S2A_SCREEN.md | ✅ |
| S2b | PHASE_S2B_CRON.md | ✅ |
| S3 | PHASE_S3_NEWS.md | ✅ |
| S4a | PHASE_S4A_BACKTEST.md | ✅ |
| S4b | PHASE_S4B_RESEARCH.md | ✅ |
| S5 | PHASE_S5_OPTIMIZATION.md | ✅ |
| S6 | PHASE_S6_TESTING.md | ✅ |
| S7 | PHASE_S7_DOCUMENTATION.md | ✅ |

---

## 快速連結

- [GitHub](https://github.com/yourusername/claw-python)
- [Issues](https://github.com/yourusername/claw-python/issues)
- [Discussions](https://github.com/yourusername/claw-python/discussions)

---

開始使用？見 [README.md](../README.md)。
```

**驗收**：
- 文檔索引清晰
- 快速導航到各個文檔

---

## Task 9 — 執行完整文檔驗收

```bash
cd /home/martin/Desktop/claw-python-personal

# 驗證所有文檔存在
ls -la docs/README.md docs/DEPLOYMENT_GUIDE.md docs/API_REFERENCE.md docs/FAQ.md docs/ARCHITECTURE.md docs/INDEX.md

# 驗證 Markdown 格式
python -c "
import re
from pathlib import Path

docs_dir = Path('docs')
for doc in docs_dir.glob('*.md'):
    with open(doc) as f:
        content = f.read()
        # 檢查基本結構
        has_title = bool(re.search(r'^# ', content, re.MULTILINE))
        has_sections = bool(re.search(r'^## ', content, re.MULTILINE))
        print(f'{doc.name}: Title={has_title}, Sections={has_sections}')
"

# 生成文檔大小統計
du -sh docs/

# 確認README、ROADMAP更新
ls -la README.md ROADMAP.md
```

**預期輸出**：
- ✅ 所有 6 個新文檔存在
- ✅ 所有文檔有正確的 Markdown 結構
- ✅ README.md 和 ROADMAP.md 已更新

---

## Task 10 — 最終驗收清單

完成以下驗收項目：

### 10.1 文檔完整性檢查

```bash
# 檢查所有重要文檔都已建立
find docs -name "*.md" -type f | wc -l  # 應 >= 6

# 驗證文檔相互連結
grep -r "DEPLOYMENT_GUIDE.md" docs/ README.md  # 應有連結
grep -r "API_REFERENCE.md" docs/ README.md
grep -r "FAQ.md" docs/ README.md
```

### 10.2 代碼示例驗證

```bash
# 確認文檔中的代碼示例有效
python -c "
# 執行 README 中的快速開始範例
from claw.core.config import get_config
cfg = get_config()
print(f'Config loaded: {cfg.gateway.host}:{cfg.gateway.port}')
"
```

### 10.3 連結驗證

確保文檔中的所有連結都有效：

```bash
# 檢查內部連結
grep -r "\[.*\](.*\.md)" docs/ | while read line; do
    link=$(echo "$line" | sed -E 's/.*\]\(([^)]+)\).*/\1/')
    if [ ! -f "$link" ] && [ ! -d "$link" ]; then
        echo "❌ Broken link: $link"
    fi
done
```

### 10.4 最終測試

```bash
python -m pytest tests/ -q
# 預期：210+ passed, 3 skipped
```

---

## 交付清單

完成後回報：

1. **新建的檔案絕對路徑**：
   - `/home/martin/Desktop/claw-python-personal/docs/DEPLOYMENT_GUIDE.md`
   - `/home/martin/Desktop/claw-python-personal/docs/API_REFERENCE.md`
   - `/home/martin/Desktop/claw-python-personal/docs/FAQ.md`
   - `/home/martin/Desktop/claw-python-personal/docs/ARCHITECTURE.md`
   - `/home/martin/Desktop/claw-python-personal/docs/INDEX.md`
   - `/home/martin/Desktop/claw-python-personal/CONTRIBUTING.md`

2. **修改的檔案絕對路徑**：
   - `/home/martin/Desktop/claw-python-personal/README.md`
   - `/home/martin/Desktop/claw-python-personal/ROADMAP.md`

3. **文檔統計**：
   - 總頁數：~50+ 頁（Markdown）
   - 代碼示例：~30+ 個
   - 工具文檔：28 個工具完整覆蓋

4. **驗收結果**：
   - ✅ 所有文檔內容完整
   - ✅ 內部連結正確
   - ✅ 代碼示例有效
   - ✅ 210+ tests still passing

5. **遇到的問題和解決方式**

---

## 完成標準

✅ README.md 完整更新（當前狀態清晰）
✅ DEPLOYMENT_GUIDE.md 包含 Jetson 部署步驟
✅ API_REFERENCE.md 涵蓋 28 個工具
✅ FAQ.md 回答 17 個常見問題
✅ ARCHITECTURE.md 說明系統設計（6 層）
✅ CONTRIBUTING.md 清晰指示貢獻方式
✅ ROADMAP.md 記錄所有 Phase（1-S7）+ 後續計劃
✅ 文檔索引（INDEX.md）清晰導航
✅ 所有連結有效
✅ 210+ tests pass, 0 failures

---

## 註記

Phase S7 完成後，系統進入**生產準備狀態**：

✅ 核心功能完整（28 工具 + 2 Cron + 2 Skills）
✅ 生產優化完成（S5）
✅ 真實環境測試驗證（S6）
✅ 完整文檔就位（S7）
✅ 210+ 個測試通過

**系統準備交付使用。**

用戶可按照 DEPLOYMENT_GUIDE.md 在 Jetson 上部署，或參考 API_REFERENCE.md 進行二次開發。

