# Phase 6 — Channel Adapters：Telegram + Slack

> **目標**：接通主流 messaging 平台，讓用戶可通過 Telegram 和 Slack 直接與 agent 互動。
> **預期成果**：+3~5 新測試，支援私訊、群組、thread、媒體附件。

---

## 現況分析（Phase 5 完成後）

### 已存在的基礎

| 項目 | 完成度 | 用途 |
|------|--------|------|
| `claw/core/gateway.py` | ✅ 完整 | FastAPI WS 控制平面、HTTP /v1 入口 |
| `claw/core/queue.py` | ✅ 完整 | Lane-aware message queue（per-session）|
| `claw/agent/loop.py` | ✅ 完整 | Agent execution + memory recall/save |
| `claw/core/storage.py` | ✅ 完整 | Session 管理、message history、egress audit |

### Channels 架構

當前的 multi-channel 模型：

```
Telegram/Slack ──(HTTP webhook)──► Gateway ──(queue)──► AgentLoop ──(events)──► Channel adapter
                                        ▲                                            │
                                        └─────── 回傳訊息 ◄─────────────────────────┘
```

**Session ID 規則**：
- Telegram 私訊：`agent:tg:user:{user_id}`
- Telegram 群組：`agent:tg:group:{group_id}`
- Slack DM：`agent:slack:dm:{user_id}`
- Slack Channel：`agent:slack:channel:{channel_id}`

### 缺少的實作

1. **TelegramChannel** 適配器 — webhook 接收 + SSE 流式發送
2. **SlackChannel** 適配器 — socket mode 或 webhook + thread 回覆
3. **Media handling** — 圖片/檔案轉換為 multipart content
4. **Rate limiting** — 0.5s throttle 避免被 block
5. **配置管理** — `config/` 中的 telegram/slack 段

---

## Phase 6 步驟清單

### STEP 1 — TelegramChannel 基礎實作

**檔案**: `claw/channels/telegram.py`

**規格**：

1. 安裝依賴：`python-telegram-bot>=21.0`

2. **TelegramChannel 類**：
   ```python
   class TelegramChannel:
       def __init__(self, token: str, base_url: str = "http://localhost:8000"):
           self.bot = telegram.Bot(token=token)
           self.base_url = base_url  # claw-python gateway URL
           self.app = telegram.ext.Application.builder().token(token).build()

       async def start(self):
           """啟動 polling 或 webhook"""

       async def stop(self):
           """停止 polling"""

       async def on_message(self, update, context):
           """處理訊息，POST 到 gateway"""

       async def on_media(self, update, context):
           """處理圖片/檔案"""

       async def send_response(self, session_id: str, content: str):
           """從 gateway 收訊息並發回給 user"""
   ```

3. **Message 流程**：
   - `update.message.text` → extract user_id / group_id
   - 決定 session_id（private vs group）
   - POST `POST {base_url}/v1/chat/completions` with `session_id`
   - 逐 chunk 接收串流回應，組裝為 Telegram message
   - 超過 Telegram 4096 字符限制時分批發送
   - 0.5s throttle 避免 rate limit

4. **Media 處理**：
   - `update.message.photo` → 下載 file → base64 → 作為 `image_url` content
   - `update.message.document` → 取 MIME type → 轉成 text（若可能）或回報「不支援」

5. **Session ID 映射**：
   ```python
   def get_session_id(self, update: telegram.Update) -> str:
       if update.message.chat.type == "private":
           return f"agent:tg:user:{update.message.from_user.id}"
       else:  # group / supergroup
           return f"agent:tg:group:{update.message.chat.id}"
   ```

**測試**：
- `test_telegram_private_message` — user sends text → session_id correct → response received
- `test_telegram_group_message` — group mentions bot → group session_id → response in group
- `test_telegram_media_handling` — user sends photo → converted to image content

---

### STEP 2 — SlackChannel 基礎實作

**檔案**: `claw/channels/slack.py`

**規格**：

1. 安裝依賴：`slack-bolt>=1.18.0`

2. **SlackChannel 類**（使用 Socket Mode）：
   ```python
   class SlackChannel:
       def __init__(self, bot_token: str, app_token: str, base_url: str):
           self.app = App(token=bot_token)
           self.socket_handler = SocketModeHandler(self.app, app_token)
           self.base_url = base_url

       async def start(self):
           """啟動 Socket Mode"""

       async def on_app_mention(self, event, client):
           """Bot 被 mention"""

       async def on_direct_message(self, event, client):
           """私訊"""

       async def send_response(self, session_id: str, content: str, thread_ts: str = None):
           """回覆訊息（支援 thread）"""
   ```

3. **Message 流程**：
   - `event.channel` → DM 或 channel
   - `event.user` → 決定 session_id
   - Thread support：若 `event.thread_ts` 存在，回覆在該 thread 中
   - POST 到 gateway 一致流程
   - Block kit formatting（可選，基礎版本用 plain text）

4. **Session ID 映射**：
   ```python
   def get_session_id(self, event: dict) -> str:
       channel = event["channel"]
       user = event["user"]
       if channel.startswith("D"):  # Direct Message
           return f"agent:slack:dm:{user}"
       else:
           return f"agent:slack:channel:{channel}"
   ```

**測試**：
- `test_slack_mention` — bot mention in channel → response in same channel
- `test_slack_direct_message` — DM to bot → DM response

---

### STEP 3 — Config 管理 + Main 啟動

**檔案**: `claw/core/config.py`（擴充），`claw/main.py`

**規格**：

1. **Config schema 增加**：
   ```python
   @dataclass
   class TelegramConfig:
       enabled: bool = False
       token: str = ""
       polling: bool = True  # True=polling, False=webhook

   @dataclass
   class SlackConfig:
       enabled: bool = False
       bot_token: str = ""
       app_token: str = ""  # 若用 Socket Mode

   @dataclass
   class Config:
       # ... existing ...
       telegram: TelegramConfig = field(default_factory=TelegramConfig)
       slack: SlackConfig = field(default_factory=SlackConfig)
   ```

2. **Main 啟動 channels**：
   ```python
   # claw/main.py lifespan()
   if cfg.telegram.enabled:
       tg_channel = TelegramChannel(cfg.telegram.token, base_url=f"http://localhost:{cfg.gateway.port}")
       await tg_channel.start()
       # 註冊 cleanup hook

   if cfg.slack.enabled:
       slack_channel = SlackChannel(cfg.slack.bot_token, cfg.slack.app_token, ...)
       await slack_channel.start()
   ```

3. **YAML config 例子**：
   ```yaml
   telegram:
     enabled: true
     token: "your_bot_token"
     polling: true

   slack:
     enabled: false
     bot_token: ""
     app_token: ""
   ```

**測試**：
- `test_config_telegram_defaults` — 檔案缺失時用預設值
- `test_config_slack_from_yaml` — 從 YAML 讀取 slack config

---

## 整合流程圖

```
Telegram User
    │
    ├─ Private message ────────────┐
    │                              │
    └─ Group mention ──────────┐   │
                               ▼   ▼
                        TelegramChannel.on_message()
                               │
                               ├─ Determine session_id
                               ├─ POST /v1/chat/completions
                               └─ Stream response back
                                      │
                                      ▼
                                 Gateway
                                      │
                                      ├─ Queue.submit()
                                      ├─ AgentLoop.run()
                                      └─ Events: TextChunk, ToolCall, RunComplete
                                           │
                                           ├─ Streaming to client
                                           └─ Storage + Transcript

Slack User
    │
    ├─ App mention in channel ─┐
    │                          │
    └─ Direct message ────────┬┤
                              ▼
                        SlackChannel.on_*()
                               │
                               ├─ Extract session_id
                               ├─ Check thread_ts
                               ├─ POST /v1/chat/completions
                               └─ Reply in thread (if applicable)
```

---

## 依賴與配置

| 項目 | 版本 | 狀態 |
|------|------|------|
| python-telegram-bot | >=21.0 | 在 pyproject.toml `[channels]` 可選 |
| slack-bolt | >=1.18.0 | 在 pyproject.toml `[channels]` 可選 |

**安裝**：
```bash
pip install -e ".[channels]"
```

---

## 測試策略

### 單元測試（無外部依賴）

- **test_telegram.py**：mock telegram.Bot，測試 session_id 映射、message parsing
- **test_slack.py**：mock Slack client，測試 mention 解析、thread 支援

### 整合測試（可選，需要 tokens）

- 若環境變數 `TELEGRAM_TOKEN` / `SLACK_BOT_TOKEN` 存在，運行實際 API 呼叫

**預期測試數**：2~3 個（mock），+1~2 個（integration if available）

---

## 時程與優先級

| STEP | 優先級 | 複雜度 | 估計工作量 |
|------|--------|-------|---------|
| 1 | ⭐⭐⭐ | 中 | 4h |
| 2 | ⭐⭐ | 中 | 3h |
| 3 | ⭐⭐⭐ | 低 | 1h |

**建議順序**：STEP 1 → STEP 2 → STEP 3

---

## 驗收標準

```bash
python -m pytest tests/test_telegram.py tests/test_slack.py -v
```

預期：**3~4 passed**（2 telegram + 2 slack minimum）

全套測試：
```bash
python -m pytest tests/ -v
```

預期：**95+ passed, 2 skipped**（+3~5 new channel tests）

---

## 分工指引

**Codex**（複雜非同步整合）：STEP 1 + STEP 2
- TelegramChannel 的 webhook/polling 邏輯
- SlackChannel 的 Socket Mode / 事件處理
- 兩邊的 streaming response + throttle

**Gemini**（配置+測試）：STEP 3
- Config schema 擴充 + yaml 解析
- main.py 啟動邏輯
- Mock 測試編寫

---

## 前置條件

- Phase 5 全數通過（92 tests）
- LLMRouterClient 可用，`/v1/chat/completions` 工作
- Session storage 正常運作

---

## 下一步（Phase 7 提示）

Phase 7 將聚焦於 **Observability**：
- Structured logging（structlog）
- Prometheus metrics
- Jaeger tracing（可選）
- Admin API 擴充（度量查詢）

預計 +6~8 tests，總計 ~103 tests。
