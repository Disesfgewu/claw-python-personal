# Phase 6 Codex Worker Prompt — Telegram + Slack Channel Adapters（獨立並行）

你是 claw-python 專案的 Codex Worker Agent。
**此任務與 Gemini 完全獨立，可並行執行，無依賴關係。**

請嚴格按照以下任務說明完成程式碼修改。完成後回報每個 STEP 的修改摘要與測試結果。

---

## 專案背景

- **claw-python**：Python AI Agent OS，當前 Phase 5 完成（92 tests pass）
- **Phase 6 目標**：Channel adapters（Telegram + Slack）
- **LLM-Router**：唯一 LLM 閘道，adapters 透過 Gateway `/v1/chat/completions` 呼叫

### 基礎已備

- `claw/core/gateway.py` — HTTP `/v1/chat/completions` 端點（支援 session_id）
- `httpx` — 用於 POST 和 SSE 串流（已在 pyproject.toml）

### 你的工作範圍（完全獨立）

只負責實作兩個 Channel 類及其基礎單元測試，**不涉及 config 系統或 main.py 啟動**：

- **STEP 1**：TelegramChannel 類實作
- **STEP 2**：SlackChannel 類實作
- **STEP 3**：Channel 基礎單元測試（8 tests）

Gemini 獨立負責 config 和 main.py，與你的工作完全無關。

---

## STEP 1 — TelegramChannel 實作

**檔案**：`claw/channels/telegram.py`（新建）

**注意**：此檔案是完全獨立的類定義，不涉及啟動配置。Gemini 會負責在 main.py 中實例化和啟動。

### 規格

1. **TelegramChannel 類**：
   - `__init__(self, token: str, base_url: str = "http://localhost:8000", polling: bool = True)`
   - `async start(self)` — 啟動 polling
   - `async stop(self)` — 優雅停止
   - `async on_message(update, context)` — 訊息處理
   - `async _send_response(chat_id, text)` — 發送訊息給使用者

2. **核心邏輯**：
   - **Session ID 映射**（內部邏輯）：
     ```python
     def _get_session_id(self, update: telegram.Update) -> str:
         if update.message.chat.type == "private":
             return f"agent:tg:user:{update.message.from_user.id}"
         else:
             return f"agent:tg:group:{update.message.chat.id}"
     ```

   - **Message 流程**：
     1. 收到 `update.message.text`
     2. 呼叫 `_get_session_id()` 決定 session
     3. **POST** `{base_url}/v1/chat/completions` 以 SSE 串流
     4. 解析 JSON chunk，累積 response
     5. 超過 4096 字符時分批發送（0.5s throttle）

3. **對接 Gateway**：
   - POST body 必須有 `session_id`、`messages`、`stream: True`
   - 接收 SSE：`data: {...}` 行
   - 解析 `choices[0].delta.content`

4. **Rate limiting**：
   - `_send_response()` 中每則訊息前 `await asyncio.sleep(0.5)`

5. **錯誤處理**：
   - 網路錯誤 → try/except，logger.error()
   - 不做 session 建立（Gateway 自動處理）
   - 簡單回報「Error: ...」給使用者

### 技術提示

- 使用 `telegram.ext.Application` 建立 bot
- 註冊 `MessageHandler` 處理 TEXT/PHOTO/Document
- `on_message(update, context)` 中：
  1. 檢查 `update.message` 存在
  2. 呼叫 `_get_session_id()` 取 session
  3. 用 `httpx.AsyncClient().stream()` POST 到 gateway
  4. 迴圈讀 `resp.aiter_lines()`，過濾 `data:` 開頭行
  5. JSON 解析，累積 `choices[0].delta.content`
  6. 呼叫 `_send_response()` 發送（含 0.5s sleep）
- 錯誤用 try/except，logger.error()

---

## STEP 2 — SlackChannel 實作

**檔案**：`claw/channels/slack.py`（新建）

**注意**：此檔案是完全獨立的類定義，不涉及啟動配置。Gemini 會負責在 main.py 中實例化和啟動。

### 規格

1. **SlackChannel 類**（Socket Mode）：
   - `__init__(self, bot_token: str, app_token: str, base_url: str = "http://localhost:8000")`
   - `async start(self)` — 啟動 Socket Mode handler
   - `async stop(self)` — 優雅停止
   - `async _on_app_mention(event)` — 處理 @bot mention
   - `async _on_direct_message(event)` — 處理 DM
   - `async _send_response(channel, text, thread_ts=None)` — 發送訊息

2. **核心邏輯**：
   - **Session ID 映射**（內部）：
     ```python
     def _get_session_id(self, event: dict) -> str:
         channel = event["channel"]
         user = event["user"]
         if channel.startswith("D"):
             return f"agent:slack:dm:{user}"
         else:
             return f"agent:slack:channel:{channel}"
     ```

   - **Message 流程**（mention + DM 相同）：
     1. 從 event 取 channel、user、text
     2. 呼叫 `_get_session_id()` 決定 session
     3. **POST** `/v1/chat/completions` 以 SSE 串流
     4. 累積 response
     5. 呼叫 `_send_response()` 發回 Slack

3. **對接 Gateway**：
   - POST body 同 Telegram：`session_id`、`messages`、`stream: True`
   - 接收 SSE：`data: {...}` 行
   - 解析 `choices[0].delta.content`

4. **Thread 支援**：
   - 若 `event.get("thread_ts")` 存在，在 `_send_response()` 中傳遞 `thread_ts` 參數
   - `client.chat_postMessage(channel=ch, text=text, thread_ts=thread_ts)`

5. **錯誤處理**：
   - 網路錯誤 → try/except，logger.error()
   - 回覆簡單錯誤訊息到 channel

### 技術提示

- 使用 `slack_bolt.async_app.AsyncApp`
- 設定 `AsyncSocketModeHandler(app, app_token)`
- 註冊 `@app.event("app_mention")` 和 `@app.message()` handler
- `_on_app_mention(event)` 和 `_on_direct_message(event)` 中：
  1. 從 event 取 channel、user、text、thread_ts
  2. 呼叫 `_get_session_id()` 取 session
  3. 用 `httpx.AsyncClient().stream()` POST 到 gateway（同 Telegram）
  4. 累積 response
  5. 呼叫 `_send_response(channel, text, thread_ts)` — 尊重 thread_ts 參數
- 錯誤用 try/except，logger.error()

---

## STEP 3 — 基礎單元測試（Channel 邏輯）

**檔案**：`tests/test_telegram.py`、`tests/test_slack.py`（新增/擴充）

**注意**：測試只驗證 Channel 類的邏輯（session_id 映射、message parsing），使用 mock 不呼叫實際 API。

### Telegram 測試（4 tests）

```python
def test_telegram_private_message_session_id():
    """Private 訊息應映射到 agent:tg:user:{id}"""

def test_telegram_group_message_session_id():
    """Group 訊息應映射到 agent:tg:group:{id}"""

def test_telegram_on_message_posts_to_gateway():
    """on_message 應 POST 到 base_url/v1/chat/completions，正確格式"""

def test_telegram_send_response_throttle():
    """_send_response 應 0.5s throttle，4096 字符分批"""
```

### Slack 測試（4 tests）

```python
def test_slack_dm_session_id():
    """DM（channel 以 D 開頭）應映射到 agent:slack:dm:{user}"""

def test_slack_channel_mention_session_id():
    """Channel mention 應映射到 agent:slack:channel:{channel}"""

def test_slack_on_mention_posts_to_gateway():
    """_on_app_mention 應 POST 到 base_url/v1/chat/completions"""

def test_slack_thread_reply():
    """_send_response 應尊重 thread_ts 參數"""
```

---

## 驗收要求

完成後執行：

```bash
python -m pytest tests/test_telegram.py tests/test_slack.py -v
```

預期：**8 passed**（Telegram 4 + Slack 4）

再執行全套：

```bash
python -m pytest tests/ -v
```

預期：**92+ passed, 2 skipped**（Phase 5 baseline 無變化，因為你只加類，不改現有代碼）

---

## 回報格式

```
## STEP 1 完成報告
- 檔案：claw/channels/telegram.py
- 實作：TelegramChannel（polling start/stop、on_message 處理、session_id 映射、rate limiting）
- 關鍵驗證：message text → gateway SSE → response 累積 → throttle 發送

## STEP 2 完成報告
- 檔案：claw/channels/slack.py
- 實作：SlackChannel（Socket Mode setup、mention/DM 處理、session_id 映射、thread 支援）
- 關鍵驗證：mention/DM → gateway SSE → response 發回 channel/thread

## STEP 3 完成報告
- 檔案：tests/test_telegram.py（4 tests）、tests/test_slack.py（4 tests）
- 測試驗證：session_id 映射正確、gateway POST 格式正確、throttle/thread 邏輯正確
- 全部使用 mock，無外部依賴

## 整體結果
- 新增測試：8 tests（Codex 單獨驗證）
- pytest tests/test_telegram.py tests/test_slack.py -v：8 passed
- 遇到的問題：[若有]
- **完全獨立完成，無需等待 Gemini**
```
