# API Reference — All 28 Tools

> 完整的 claw-python 工具 API 文檔。

---

## 基礎工具

### bash — Execute Shell Commands

**描述**：在隔離的 Docker 容器中執行 bash 命令

**簽名**：`def bash(command: str) -> str`

**參數**：
- `command` (str): bash 命令

**安全注意**：
- 命令執行於沙盒環境（network=none, read_only）
- 不支援互動式命令
- 輸出限制 10KB

---

### search_web — Search with DDGS

**描述**：使用 DuckDuckGo 搜尋

**簽名**：`def search_web(query: str, max_results: int = 10) -> str`

**參數**：
- `query` (str): 搜尋查詢
- `max_results` (int): 最多返回結果數

---

### web_fetch — Fetch Web Content

**描述**：HTTP GET/POST 請求

**簽名**：`def web_fetch(url: str, method: str = "GET") -> str`

---

## 檔案工具

### file_read — Read File

**描述**：讀取工作區內的檔案

**簽名**：`def file_read(path: str) -> str`

**限制**：最多 100KB

---

### file_write — Write File

**簽名**：`def file_write(path: str, content: str) -> str`

---

### file_list — List Files

**簽名**：`def file_list(path: str = ".") -> str`

---

### file_delete — Delete File

**簽名**：`def file_delete(path: str) -> str`

---

## 記憶體工具

### memory_save — Save to Memory

**描述**：向量 + FTS5 儲存

**簽名**：`def memory_save(content: str, metadata: dict = None) -> str`

---

### memory_search — Search Memory

**描述**：語意搜尋記憶

**簽名**：`def memory_search(query: str, limit: int = 5) -> str`

---

## 股票工具

### stock_fetch — Fetch Stock Data

**描述**：從 TWSE/Yahoo Finance 拉取 OHLCV 資料

**簽名**：`def stock_fetch(symbol: str, period: str = "1y") -> dict`

**參數**：
- `symbol` (str): 股票代碼（例如 "2330"）
- `period` (str): "1mo", "3mo", "1y"

**返回**：
```python
{
    "symbol": "2330",
    "name": "台積電",
    "current": 600.0,
    "ohlcv": [
        {"date": "2026-03-22", "open": 598.5, "high": 605.0,
         "low": 595.0, "close": 600.0, "volume": 18500000},
        ...
    ]
}
```

---

### stock_analyze — Technical Analysis

**描述**：計算技術指標

**簽名**：`def stock_analyze(symbol: str, period: str = "3mo") -> str`

**返回**：JSON 格式的分析報告

---

### generate_chart — Generate K-Line Chart

**描述**：生成 K 線圖 (PNG)

**簽名**：`def generate_chart(symbol: str, ohlcv_list: list) -> bytes`

---

### stock_screen — Screen Taiwan 50

**描述**：篩選台灣50中符合條件的強勢股

**簽名**：`def stock_screen(criteria: dict = None) -> list`

**返回**：前 15 個最強勢股

---

### stock_chip — Institutional Chip Analysis

**描述**：查詢法人買賣超

**簽名**：`def stock_chip(symbol: str) -> dict`

---

### stock_news — Fetch Stock News

**描述**：搜尋個股相關新聞

**簽名**：`def stock_news(symbol: str, limit: int = 5) -> list`

---

## 研究工具

### research_start — Start Research Task

**描述**：啟動自主研究任務

**簽名**：`def research_start(title: str, plan: str) -> dict`

---

### research_status — Check Research Status

**簽名**：`def research_status(research_id: str) -> dict`

---

### experiment_record — Record Experiment

**簽名**：`def experiment_record(research_id: str, result: dict) -> dict`

---

## Cron 工具

### cron_add — Add Scheduled Job

**簽名**：`def cron_add(name: str, schedule: str, prompt: str) -> dict`

**參數**：
- `schedule`: Cron 表達式（例如 "0 8 * * 1-5"）

---

### cron_list — List Scheduled Jobs

**簽名**：`def cron_list() -> list`

---

### cron_delete — Delete Scheduled Job

**簽名**：`def cron_delete(name: str) -> dict`

---

## 生成工具

### image_gen — Generate Image

**描述**：使用 Router /v1/images/generations

**簽名**：`def image_gen(prompt: str) -> bytes`

---

## 瀏覽器工具

### browser_navigate — Navigate to URL

**簽名**：`def browser_navigate(url: str) -> str`

---

### browser_extract — Extract Page Content

**簽名**：`def browser_extract(selector: str) -> str`

---

### browser_close — Close Browser

**簽名**：`def browser_close() -> str`

---

## 多代理工具

### sessions_send — Send Message to Agent

**簽名**：`def sessions_send(session_id: str, message: str) -> str`

---

### sessions_spawn — Spawn New Agent

**簽名**：`def sessions_spawn(prompt: str) -> dict`

---

### sessions_list — List Active Sessions

**簽名**：`def sessions_list() -> list`

---

## MCP 工具（動態）

由 `claw/tools/mcp_bridge.py` 動態載入的工具。

---

見 [README.md](../README.md) 了解完整工具清單。
