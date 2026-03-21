# Pylance 錯誤修復指南

## 已識別的 Pylance 錯誤清單與修復方案

---

## 🔴 Critical Errors

### Error 1: gateway.py - Type Narrowing Failure

**位置**：`claw/core/gateway.py:23-26`

**Pylance 報錯**：
```
Function declared to return 'tuple[Storage, MessageQueue, LLMRouterClient]'
but condition can leave it returning 'tuple[Storage | None, MessageQueue | None, LLMRouterClient | None]'
```

**根本原因**：
```python
def _require_dependencies() -> tuple[Storage, MessageQueue, LLMRouterClient]:
    if storage is None or queue is None or llm is None:
        raise RuntimeError("gateway dependencies are not configured")
    # ⚠️ Pylance 無法確認在 raise 後，storage/queue/llm 確實非 None
    return storage, queue, llm
```

**修復方案**：

**方案 A（使用 assert）**：
```python
def _require_dependencies() -> tuple[Storage, MessageQueue, LLMRouterClient]:
    if storage is None or queue is None or llm is None:
        raise RuntimeError("gateway dependencies are not configured")
    assert storage is not None
    assert queue is not None
    assert llm is not None
    return storage, queue, llm
```

**方案 B（使用 type: ignore）**：
```python
def _require_dependencies() -> tuple[Storage, MessageQueue, LLMRouterClient]:
    if storage is None or queue is None or llm is None:
        raise RuntimeError("gateway dependencies are not configured")
    return storage, queue, llm  # type: ignore[return-value]
```

**推薦**：方案 A（更清晰）

---

### Error 2: channels/telegram.py - Missing None Guard

**位置**：`claw/channels/telegram.py:44-46`

**Pylance 報錯**：
```
"application" is possibly unbound
"updater" is possibly unbound
```

**現有代碼**：
```python
async def start(self) -> None:
    try:
        from telegram.ext import Application, MessageHandler, filters
    except Exception as e:
        raise ImportError("python-telegram-bot not installed") from e

    self.app = Application.builder().token(self.token).build()
    # ...
    if self.polling and self.app.updater:  # ⚠️ self.app.updater 可能為 None
        await self.app.updater.start_polling()
```

**修復方案**：

```python
async def start(self) -> None:
    try:
        from telegram.ext import Application, MessageHandler, filters
    except Exception as e:
        raise ImportError("python-telegram-bot not installed") from e

    self.app = Application.builder().token(self.token).build()
    self.app.add_handler(
        MessageHandler(
            filters.TEXT | filters.PHOTO | filters.Document.ALL,
            self.on_message,
        )
    )
    await self.app.initialize()
    await self.app.start()

    # ✅ 正確檢查 updater
    if self.polling:
        updater = self.app.updater
        if updater is not None:
            await updater.start_polling()
            logger.info("TelegramChannel polling started")
        else:
            logger.warning("No updater available, polling disabled")
    else:
        logger.info("TelegramChannel webhook mode (not implemented)")
```

---

### Error 3: channels/telegram.py - Unsafe Message Access

**位置**：`claw/channels/telegram.py:56-61`

**Pylance 報錯**：
```
"update.message" is possibly None
"update.message.text" is possibly None
```

**現有代碼**：
```python
async def on_message(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> None:
    if not update or not update.message:
        return
    text = update.message.text  # ⚠️ Pylance 看不到前面的 None 檢查
```

**修復方案**：

```python
async def on_message(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> None:
    if update is None or update.message is None:
        logger.debug("Received update without message")
        return

    message = update.message
    if message.text is None:
        logger.debug(f"Ignoring non-text message type: {message.content_type if hasattr(message, 'content_type') else 'unknown'}")
        return

    text: str = message.text
    chat_id: int = message.chat.id
    # ... 後續代碼中 text 和 chat_id 已被確認為非 None
```

**類型提示補充**：
```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from telegram import Update
    from telegram.ext import ContextTypes
```

---

### Error 4: memory/manager.py - Private API Access

**位置**：`claw/memory/manager.py:58`

**Pylance 報錯**：
```
"_client" is not a known member of "LLMRouterClient"
Cannot access private member "_client"
```

**現有代碼**：
```python
async def _get_embedding(self, text: str) -> list[float]:
    try:
        resp = await self.llm._client.post(  # ⚠️ _client 是私有成員
            f"{self.llm.base_url}/v1/embeddings",
            json={"input": text, "model": "default"},
        )
```

**修復方案**：

方案1：提供公開方法在 LLMRouterClient

```python
# claw/llm/router_client.py 中添加
class LLMRouterClient:
    async def get_embedding(self, text: str) -> list[float]:
        """Generate embedding via /v1/embeddings endpoint."""
        try:
            resp = await self._client.post(
                f"{self.base_url}/v1/embeddings",
                json={"input": text, "model": "default"},
            )
            resp.raise_for_status()
            data = resp.json()
            return data["data"][0]["embedding"]
        except Exception as e:
            logger.error(f"Embedding request failed: {e}")
            raise
```

方案2：在 manager.py 中改為訪問公開屬性

```python
# claw/memory/manager.py
async def _get_embedding(self, text: str) -> list[float]:
    try:
        # 改為使用公開 API
        embedding = await self.llm.get_embedding(text)
        return embedding
    except Exception as e:
        logger.error(f"Embedding generation failed: {e}")
        return [0.0] * _FALLBACK_DIM
```

---

## 🟡 Warning Issues

### Warning 1: Type Annotation - Optional vs Union

**位置**：`claw/core/gateway.py:5, 18-20`

**Pylance 警告**：
```
Use of 'Optional' is deprecated; use 'X | None' instead
```

**現有代碼**：
```python
from typing import Optional

storage: Optional[Storage] = None
queue: Optional[MessageQueue] = None
llm: Optional[LLMRouterClient] = None
```

**修復方案**：

```python
# 移除 Optional 導入
# from typing import Optional  ❌

storage: Storage | None = None
queue: MessageQueue | None = None
llm: LLMRouterClient | None = None
```

**全文件掃描**：
```bash
# 找出所有使用 Optional 的地方
grep -r "Optional\[" claw/ --include="*.py"
```

應替換為：
- `Optional[X]` → `X | None`
- `Union[X, Y]` → `X | Y`

---

### Warning 2: Unchecked Type Narrowing

**位置**：`claw/agent/loop.py:96-107`

**Pylance 警告**：
```
Item "None" has no attribute "get"
List index out of range
```

**現有代碼**：
```python
if self.memory:
    try:
        recalled = await self.memory.search(user_message, session_id=session_id, limit=3)
        if recalled:  # ⚠️ recalled 可能為空列表
            memory_lines = "\n".join(
                f"[Memory {i+1}] {item.get('content', '')[:300]}"
                for i, item in enumerate(recalled)
            )
```

**修復方案**：

```python
if self.memory:
    try:
        recalled = await self.memory.search(
            user_message,
            session_id=session_id,
            limit=3
        )
        if recalled and len(recalled) > 0:
            # ✅ 確保 recalled 非空
            memory_lines = "\n".join(
                f"[Memory {i+1}] {item.get('content', '')[:300]}"
                for i, item in enumerate(recalled)
            )
            if memory_lines:
                sys_prompt += f"\n\n=== Recalled Memories ===\n{memory_lines}"
                logger.debug(f"Recalled {len(recalled)} memories for session {session_id}")
    except Exception as e:
        logger.warning(f"Memory recall failed: {e}")
        # 繼續，不中斷 LLM 調用
```

---

### Warning 3: Unreliable Type Checking

**位置**：`claw/channels/slack.py:48`

**Pylance 警告**：
```
Object of type "AsyncSocketModeHandler" has no attribute "start_async"
(but may have attribute dynamically assigned)
```

**現有代碼**：
```python
self._socket_handler = AsyncSocketModeHandler(self.app, self.app_token)
if hasattr(self._socket_handler, "start_async"):  # ⚠️ hasattr 在類型檢查時不可靠
    await self._socket_handler.start_async()
else:
    await self._socket_handler.start()
```

**修復方案**：

```python
self._socket_handler = AsyncSocketModeHandler(self.app, self.app_token)

# ✅ 方案 A：版本檢查
import slack_bolt
slack_bolt_version = tuple(map(int, slack_bolt.__version__.split('.')[:2]))
if slack_bolt_version >= (1, 18):
    await self._socket_handler.start_async()
else:
    await self._socket_handler.start()

# ✅ 方案 B：異常處理
try:
    # 嘗試新版方法
    await self._socket_handler.start_async()
except AttributeError:
    # 回退舊版方法
    logger.info("Using legacy SlackChannel.start() method")
    await self._socket_handler.start()
```

推薦方案 B（更健壯）

---

### Warning 4: Configuration Validation Missing

**位置**：`claw/main.py:62-66`

**Pylance 警告**：
```
Argument of type "str" cannot be assigned to parameter "token" of type "str" in function "__init__"
(Config.telegram.token may be empty string)
```

**現有代碼**：
```python
if cfg.telegram.enabled:
    try:
        from claw.channels.telegram import TelegramChannel
        tg = TelegramChannel(
            token=cfg.telegram.token,  # ⚠️ 可能為空字符串
```

**修復方案**：

```python
if cfg.telegram.enabled:
    # ✅ 驗證必需的配置
    if not cfg.telegram.token or not cfg.telegram.token.strip():
        logger.error(
            "Telegram.enabled=True but token is empty or whitespace. "
            "Set TELEGRAM_TOKEN environment variable or config.telegram.token in config/default.yaml"
        )
        # 不中斷啟動，只跳過 Telegram
        pass
    else:
        try:
            from claw.channels.telegram import TelegramChannel
            tg = TelegramChannel(
                token=cfg.telegram.token.strip(),
                base_url=f"http://localhost:{cfg.gateway.port}",
                polling=cfg.telegram.polling,
            )
            await tg.start()
            channels.append(tg)
            logger.info("Telegram channel started")
        except Exception as e:
            logger.error(f"Failed to start Telegram channel: {e}")

# Slack 同樣處理
if cfg.slack.enabled:
    if not cfg.slack.bot_token or not cfg.slack.app_token:
        logger.error(
            "Slack.enabled=True but bot_token or app_token is empty. "
            "Set SLACK_BOT_TOKEN and SLACK_APP_TOKEN environment variables"
        )
        pass
    else:
        try:
            from claw.channels.slack import SlackChannel
            slack = SlackChannel(
                bot_token=cfg.slack.bot_token.strip(),
                app_token=cfg.slack.app_token.strip(),
                base_url=f"http://localhost:{cfg.gateway.port}",
            )
            await slack.start()
            channels.append(slack)
            logger.info("Slack channel started")
        except Exception as e:
            logger.error(f"Failed to start Slack channel: {e}")
```

---

## 🟢 Info Issues

### Info 1: Logging Context Missing

**位置**：全局（所有文件）

**Pylance 提示**：
```
Logger should include session_id and request_id context
Consider using contextvars for automatic propagation
```

**問題**：
```python
logger.error(f"Error in TelegramChannel: {e}")  # ❌ 無法追蹤來源
```

**修復方案**：

添加上下文

```python
# claw/core/logging_context.py
import contextvars
from typing import Optional

_session_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    'session_id', default=None
)
_request_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    'request_id', default=None
)

def set_session_context(session_id: str) -> None:
    _session_id.set(session_id)

def get_session_context() -> Optional[str]:
    return _session_id.get()

def set_request_context(request_id: str) -> None:
    _request_id.set(request_id)

def get_request_context() -> Optional[str]:
    return _request_id.get()
```

在 Channel 中使用：

```python
# claw/channels/telegram.py
from claw.core.logging_context import set_session_context, get_session_context

async def on_message(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> None:
    if update is None or update.message is None:
        return

    message = update.message
    text = message.text
    if text is None:
        return

    chat_id = message.chat.id
    session_id = self._get_session_id(update)

    # ✅ 設置日誌上下文
    set_session_context(session_id)

    try:
        logger.debug(f"Processing message from {chat_id}: {text[:50]}")
        response_text = await self._call_gateway(session_id, text)
        if response_text:
            await self._send_response(chat_id, response_text)
    except Exception as e:
        logger.error(f"Failed to process message", exc_info=True)
        await self._send_response(chat_id, f"Error: {str(e)[:100]}")
```

---

### Info 2: Sensitive Data Redaction

**位置**：所有日誌輸出

**Pylance 提示**：
```
Sensitive data may be logged (token, api_key, password)
Consider using redaction filter
```

**修復方案**：

```python
# claw/core/logging_redaction.py
import re
from typing import Any

_REDACT_PATTERNS = [
    r'(token["\']?\s*[:=]\s*)["\']?[^"\'\s]{10,}["\']?',
    r'(api[_-]?key["\']?\s*[:=]\s*)["\']?[^"\'\s]{10,}["\']?',
    r'(password["\']?\s*[:=]\s*)["\']?[^"\'\s]{10,}["\']?',
    r'(bearer\s+)[^\s]{10,}',
]

def redact_sensitive(text: str) -> str:
    """Remove sensitive data from log messages."""
    for pattern in _REDACT_PATTERNS:
        text = re.sub(pattern, r'\1[REDACTED]', text, flags=re.IGNORECASE)
    return text

class RedactingFilter(logging.Filter):
    def filter(self, record):
        record.msg = redact_sensitive(str(record.msg))
        if record.args:
            if isinstance(record.args, dict):
                record.args = {k: redact_sensitive(str(v)) for k, v in record.args.items()}
            elif isinstance(record.args, tuple):
                record.args = tuple(redact_sensitive(str(arg)) for arg in record.args)
        return True

# 在 main.py 中應用
import logging
from claw.core.logging_redaction import RedactingFilter

logging.getLogger().addFilter(RedactingFilter())
```

---

## 修復優先順序與時間估計

| 優先級 | 錯誤 | 位置 | 複雜度 | 時間 | 影響 |
|-------|------|------|--------|------|------|
| 🔴 P1 | Type narrowing | gateway.py:23 | 低 | 5 min | Pylance critical |
| 🔴 P1 | None guard (TG) | telegram.py:44 | 低 | 10 min | Runtime crash |
| 🔴 P1 | None guard (Slack) | slack.py:48 | 低 | 10 min | Runtime crash |
| 🔴 P1 | Private API | memory/manager.py:58 | 中 | 30 min | API design |
| 🟡 P2 | Optional → \| None | gateway.py:5-20 | 低 | 20 min | Code style |
| 🟡 P2 | Memory narrowing | loop.py:96 | 低 | 15 min | Pylance warning |
| 🟡 P2 | hasattr() check | slack.py:48 | 低 | 20 min | Version compat |
| 🟡 P2 | Config validation | main.py:62 | 中 | 30 min | Robustness |
| 🟢 P3 | Logging context | all files | 高 | 2 h | Observability |
| 🟢 P3 | Redaction | all files | 高 | 2 h | Security |

**總時間估計**：8-10 小時（包含測試）

---

## 修復檢查清單

- [ ] 運行 Pylance 檢查：`pylance --check claw/`
- [ ] 修復所有 Critical errors
- [ ] 修復所有 Warning issues
- [ ] 運行 pytest：確保 106/106 tests 仍通過
- [ ] 運行 mypy（如果安裝）：`mypy claw/`
- [ ] 代碼審查：確保沒有引入新的邏輯錯誤

---

## 相關文檔

- PHASE7.5_PM_AUDIT.md - 完整審計報告
- PHASE6 完成報告 - Channel 實現
- Phase 7 規劃 - Observability 層

