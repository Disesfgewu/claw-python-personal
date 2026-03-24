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

用戶輸入 → Channel Adapter → Gateway HTTP/WebSocket

**責任**：
- 協議轉換（Telegram → JSON, Discord → JSON）
- 認証驗證
- 訊息路由

---

### 層次 2：API 層（Gateway）

HTTP POST /v1/chat → FastAPI routing → Session lookup → AgentLoop

**責任**：
- HTTP 路由和驗證
- WebSocket 長連接管理
- Session 生命週期管理

**檔案**：`claw/core/gateway.py`

---

### 層次 3：代理層（AgentLoop）

Agent Input → Memory Recall → Tool Dispatch → Tool Call → Output

**責任**：
- 工具選擇和調度
- 上下文管理和縮小
- 結果驗證和重試

**檔案**：`claw/agent/loop.py`

---

### 層次 4：工具層（Tools）

28 個工具分類：
- Execution (bash)
- Search (search_web, web_fetch)
- File (file_read/write/list/delete)
- Memory (memory_save/search)
- Research (research_*)
- Stock (6 個股票工具)
- Image (image_gen)
- Browser (browser_*)
- Sessions (sessions_*)
- Cron (cron_*)

**檔案**：`claw/tools/*.py`

---

### 層次 5：存儲層（Storage）

Memory Store → Vector Search (sqlite-vec) + FTS5 + RRF

Session Store → SQLite

Transcript Files → 純文本

**檔案**：`claw/memory/*.py`, `claw/core/storage.py`

---

### 層次 6：外部服務層

LLM Router (HTTP)
- /v1/chat/completions
- /v1/embeddings
- /v1/images/generations
- /mcp/messages (DDGS)

Data Sources
- TWSE API
- Yahoo Finance

Channels
- Discord API
- Telegram API
- Slack API

---

## 數據流示例：股票查詢

1. 用戶在 Discord：「分析台積電」
2. DiscordChannel.on_message() 接收
3. Gateway 建立 session，轉發給 AgentLoop
4. AgentLoop.run()：
   - Memory.search("台積電")
   - 調用 stock_fetch("2330")
   - 調用 stock_analyze()
   - 調用 generate_chart()
5. 格式化為 Discord Embed + File
6. 推送到 Discord

---

## 關鍵設計決策

### 為什麼使用 Docker 沙盒？

- **隔離**：bash 命令無法訪問主系統
- **限制**：CPU、記憶體、網絡受限
- **安全**：損害範圍有限

### 為什麼使用混合搜尋（RRF）？

- 向量搜尋：找到語意相似
- FTS5：找到精確匹配
- RRF：結合兩者

### 為什麼分離 ResearchLoop 和 AgentLoop？

- AgentLoop：快速響應
- ResearchLoop：深度思考
- 可並行運行

---

## 擴展點

### 添加新工具

1. 在 `claw/tools/my_tool.py` 中實現
2. 在 `claw/tools/__init__.py` 中註冊
3. 重啟伺服器

### 添加新渠道

1. 在 `claw/channels/my_channel.py` 中繼承 `BaseChannel`
2. 實現 `start()`, `stop()`, `send()` 方法
3. 在 `claw/main.py` 中初始化

---

見 [API_REFERENCE.md](API_REFERENCE.md) 了解工具細節。
