# Phase 6 Codex Worker Prompt — Telegram + Slack Channel Adapters

你是 claw-python 專案的 Codex Worker Agent。
請嚴格按照以下任務說明完成程式碼修改。完成後回報每個 STEP 的修改摘要與測試結果。

---

## 專案背景

- **claw-python**：Python AI Agent OS，當前 Phase 5 完成（92 tests pass）
- **Phase 6 目標**：Telegram + Slack channel adapters，支援私訊、群組、thread
- **LLM-Router**：唯一 LLM 閘道，channel adapters 透過 Gateway `/v1/chat/completions` 呼叫

### 基礎已備

- `claw/core/gateway.py` — FastAPI WS + HTTP 入口（支援 session_id 傳遞）
- `claw/core/queue.py` — Lane-aware queue（per-session）
- `claw/agent/loop.py` — Agent execution + memory

### 你的工作範圍

- STEP 1：TelegramChannel 完整實作（polling + webhook ready）
- STEP 2：SlackChannel 完整實作（Socket Mode）

---

## STEP 1 — TelegramChannel 實作

**檔案**：`claw/channels/telegram.py`（新建）

### 規格

1. **TelegramChannel 類**：
   - `__init__(self, token: str, base_url: str, polling: bool = True)`
   - `async start(self)` — 啟動 polling 或 webhook listener
   - `async stop(self)` — 優雅停止
   - `async on_message(update, context)` — 訊息處理
   - `async on_media(update, context)` — 媒體處理（photo, document）
   - `async send_response(session_id, content)` — 回傳訊息給 user

2. **Session ID 決策邏輯**：
   ```python
   def _get_session_id(self, update: telegram.Update) -> str:
       if update.message.chat.type == "private":
           return f"agent:tg:user:{update.message.from_user.id}"
       else:  # group, supergroup, channel
           return f"agent:tg:group:{update.message.chat.id}"
   ```

3. **Message 流程**：
   - 收到 `update.message.text`
   - 呼叫 `_get_session_id()`
   - **POST** `{base_url}/v1/chat/completions`：
     ```python
     body = {
         "session_id": session_id,
         "messages": [{"role": "user", "content": text}],
         "stream": True,
     }
     ```
   - 串流接收 `data: {...}` SSE chunks
   - 解析 JSON 取 `choices[0].delta.content`
   - 累積 response 字串
   - 超過 4096 字符時分批發送

4. **Media 處理**：
   - Photo：`update.message.photo[-1]` → `get_file()` → download → base64 encode
     - 轉成 multipart content：
       ```python
       content = [
           {"type": "text", "text": caption or ""},
           {"type": "image", "image": {"url": f"data:image/jpeg;base64,{b64}"}}
       ]
       ```
   - Document：取 MIME type，若是 text 試圖解析，否則回報「不支援」

5. **Rate limiting**：
   - 發送訊息時使用 0.5s throttle（asyncio.sleep(0.5) 在 send 前）
   - 避免被 Telegram 限速

6. **錯誤處理**：
   - 網路錯誤、timeout → 回傳「服務暫不可用」給 user
   - Session 不存在 → 自動建立新 session（Gateway 會處理）
   - Tool 執行失敗 → 將錯誤訊息轉發給 user

### 實作提示

```python
from __future__ import annotations
import asyncio
import logging
from typing import Optional
import telegram
from telegram.ext import Application, MessageHandler, filters, ContextTypes
import httpx

logger = logging.getLogger(__name__)

class TelegramChannel:
    def __init__(self, token: str, base_url: str = "http://localhost:8000", polling: bool = True):
        self.token = token
        self.base_url = base_url
        self.polling = polling
        self.app = Application.builder().token(token).build()
        self.bot = telegram.Bot(token=token)
        self._setup_handlers()

    def _setup_handlers(self):
        self.app.add_handler(MessageHandler(filters.TEXT | filters.PHOTO | filters.Document.ALL, self.on_message))

    async def on_message(self, update: telegram.Update, context: ContextTypes.DEFAULT_TYPE):
        """Main message handler"""
        if not update.message:
            return

        session_id = self._get_session_id(update)
        user_id = update.message.from_user.id if update.message.from_user else None

        # Handle different message types
        if update.message.text:
            content = update.message.text
        elif update.message.photo:
            content = await self._handle_photo(update)
        # ... other media types

        # POST to gateway
        try:
            async with httpx.AsyncClient() as client:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/v1/chat/completions",
                    json={"session_id": session_id, "messages": [{"role": "user", "content": content}], "stream": True},
                    timeout=60,
                ) as resp:
                    full_response = ""
                    async for line in resp.aiter_lines():
                        if line.startswith("data: "):
                            import json
                            chunk_data = json.loads(line[6:])
                            if "choices" in chunk_data and len(chunk_data["choices"]) > 0:
                                delta = chunk_data["choices"][0].get("delta", {})
                                if "content" in delta:
                                    full_response += delta["content"]

                    # Send response (handle >4096 char limit)
                    await self._send_response(user_id, full_response)
        except Exception as e:
            logger.error(f"Error in on_message: {e}")
            await self.bot.send_message(chat_id=user_id, text=f"Error: {str(e)}")

    async def _handle_photo(self, update: telegram.Update) -> list:
        """Convert photo to multipart content"""
        # 下載圖片 → base64 → 轉成 multipart
        pass

    async def _send_response(self, chat_id: int, text: str):
        """Send response with 4096 char limit and throttle"""
        for i in range(0, len(text), 4096):
            chunk = text[i:i+4096]
            await self.bot.send_message(chat_id=chat_id, text=chunk)
            await asyncio.sleep(0.5)  # Throttle

    async def start(self):
        """Start polling or webhook"""
        await self.app.initialize()
        await self.app.start()
        if self.polling:
            await self.app.updater.start_polling()
        logger.info("TelegramChannel started")

    async def stop(self):
        """Stop gracefully"""
        if self.polling:
            await self.app.updater.stop()
        await self.app.stop()
        await self.app.shutdown()
        logger.info("TelegramChannel stopped")

    def _get_session_id(self, update: telegram.Update) -> str:
        if update.message.chat.type == "private":
            return f"agent:tg:user:{update.message.from_user.id}"
        else:
            return f"agent:tg:group:{update.message.chat.id}"
```

---

## STEP 2 — SlackChannel 實作

**檔案**：`claw/channels/slack.py`（新建）

### 規格

1. **SlackChannel 類**（Socket Mode）：
   - `__init__(self, bot_token: str, app_token: str, base_url: str)`
   - `async start(self)` — 啟動 Socket Mode
   - `async stop(self)` — 優雅停止
   - `async on_app_mention(event)` — Bot 被 mention
   - `async on_direct_message(event)` — 私訊
   - `async send_response(session_id, content, thread_ts=None)` — 回覆

2. **Session ID 決策**：
   ```python
   def _get_session_id(self, event: dict) -> str:
       channel = event["channel"]
       user = event["user"]
       if channel.startswith("D"):  # Direct Message
           return f"agent:slack:dm:{user}"
       else:
           return f"agent:slack:channel:{channel}"
   ```

3. **Message 流程**：
   - 收到 `@bot mention` 或 DM
   - 決策 session_id
   - **POST** `/v1/chat/completions` 相同流程
   - 串流接收 SSE
   - 回覆在相同 channel，若 `thread_ts` 存在，回覆在 thread

4. **Thread 支援**：
   ```python
   if event.get("thread_ts"):
       # Reply in thread
       await client.chat_postMessage(
           channel=channel,
           text=response,
           thread_ts=event["thread_ts"],
       )
   else:
       # Reply in channel
       await client.chat_postMessage(channel=channel, text=response)
   ```

5. **Block Kit（可選，基礎版本用 plain text）**：
   - 若回應包含特殊格式，可考慮用 mrkdwn
   - 基礎版本：直接 `text` 欄位即可

### 實作提示

```python
from __future__ import annotations
import asyncio
import logging
from slack_bolt.async_app import AsyncApp
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
import httpx
import json

logger = logging.getLogger(__name__)

class SlackChannel:
    def __init__(self, bot_token: str, app_token: str, base_url: str = "http://localhost:8000"):
        self.bot_token = bot_token
        self.app_token = app_token
        self.base_url = base_url
        self.app = AsyncApp(token=bot_token)
        self.handler = AsyncSocketModeHandler(self.app, app_token)
        self._setup_handlers()

    def _setup_handlers(self):
        @self.app.event("app_mention")
        async def handle_mention(event, say):
            await self._on_app_mention(event)

        @self.app.message(filters.type_message())
        async def handle_message(event, say):
            # Check if this is a DM (channel starts with 'D')
            if event["channel"].startswith("D"):
                await self._on_direct_message(event)

    async def _on_app_mention(self, event: dict):
        """Handle @bot mention"""
        channel = event["channel"]
        user = event["user"]
        text = event["text"].replace(f"<@{self.app.client._client_id}>", "").strip()
        thread_ts = event.get("thread_ts")

        session_id = self._get_session_id(event)

        try:
            async with httpx.AsyncClient() as client:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/v1/chat/completions",
                    json={"session_id": session_id, "messages": [{"role": "user", "content": text}], "stream": True},
                    timeout=60,
                ) as resp:
                    full_response = ""
                    async for line in resp.aiter_lines():
                        if line.startswith("data: "):
                            chunk_data = json.loads(line[6:])
                            if "choices" in chunk_data and len(chunk_data["choices"]) > 0:
                                delta = chunk_data["choices"][0].get("delta", {})
                                if "content" in delta:
                                    full_response += delta["content"]

                    # Send response
                    await self._send_response(channel, full_response, thread_ts)
        except Exception as e:
            logger.error(f"Error in mention handler: {e}")
            await self.app.client.chat_postMessage(
                channel=channel, text=f"Error: {str(e)}", thread_ts=thread_ts
            )

    async def _on_direct_message(self, event: dict):
        """Handle DM"""
        channel = event["channel"]
        text = event["text"]
        session_id = self._get_session_id(event)

        try:
            async with httpx.AsyncClient() as client:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/v1/chat/completions",
                    json={"session_id": session_id, "messages": [{"role": "user", "content": text}], "stream": True},
                    timeout=60,
                ) as resp:
                    full_response = ""
                    async for line in resp.aiter_lines():
                        if line.startswith("data: "):
                            chunk_data = json.loads(line[6:])
                            if "choices" in chunk_data and len(chunk_data["choices"]) > 0:
                                delta = chunk_data["choices"][0].get("delta", {})
                                if "content" in delta:
                                    full_response += delta["content"]

                    await self._send_response(channel, full_response)
        except Exception as e:
            logger.error(f"Error in DM handler: {e}")
            await self.app.client.chat_postMessage(channel=channel, text=f"Error: {str(e)}")

    async def _send_response(self, channel: str, text: str, thread_ts: str = None):
        """Send response to Slack"""
        await self.app.client.chat_postMessage(
            channel=channel,
            text=text,
            thread_ts=thread_ts,
        )

    async def start(self):
        """Start Socket Mode handler"""
        await self.handler.start_async()
        logger.info("SlackChannel started")

    async def stop(self):
        """Stop gracefully"""
        await self.handler.stop_async()
        logger.info("SlackChannel stopped")

    def _get_session_id(self, event: dict) -> str:
        channel = event["channel"]
        user = event["user"]
        if channel.startswith("D"):
            return f"agent:slack:dm:{user}"
        else:
            return f"agent:slack:channel:{channel}"
```

---

## 驗收要求

完成後執行：

```bash
python -m pytest tests/test_telegram.py tests/test_slack.py -v
```

預期：**4 passed**（2 telegram + 2 slack minimum）

再執行全套：

```bash
python -m pytest tests/ -v
```

預期：**95+ passed, 2 skipped**

---

## 回報格式

```
## STEP 1 完成報告
- 修改檔案：claw/channels/telegram.py
- 主要變更：[TelegramChannel 實作摘要]
- 關鍵功能驗證：polling 正常、message/photo 處理、rate limiting

## STEP 2 完成報告
- 修改檔案：claw/channels/slack.py
- 主要變更：[SlackChannel 實作摘要]
- 關鍵功能驗證：mention handling、DM、thread reply

## 整體結果
- 新增測試：[test count]
- pytest tests/ -v：X passed
- 遇到的問題：[若有]
```
