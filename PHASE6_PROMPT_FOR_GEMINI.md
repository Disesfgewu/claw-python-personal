# Phase 6 Gemini Worker Prompt — Config + Tests

你是 claw-python 專案的 Gemini Worker Agent。
請嚴格按照以下任務說明完成程式碼修改與測試撰寫。
完成後回報每個 STEP 的修改摘要與測試結果。

---

## 專案背景

- **claw-python**：Python AI Agent OS，當前 Phase 5 完成（92 tests pass）
- Phase 6 目標：Telegram + Slack channel adapters
- 你負責：Config 管理 + Channel 測試 + Main 啟動邏輯

### 已完成（Codex 負責）

- STEP 1：TelegramChannel 完整實作（polling + webhook）
- STEP 2：SlackChannel 完整實作（Socket Mode）

### 你的工作範圍

- STEP 3：Config schema 擴充 + main.py 啟動邏輯
- STEP 4：Telegram 和 Slack channel 測試（mock）

---

## STEP 3 — Config 管理 + Main 啟動

### 3a. Config Schema 擴充

**檔案**：`claw/core/config.py`

在現有 Config dataclass 中增加：

```python
from dataclasses import dataclass, field

@dataclass
class TelegramConfig:
    enabled: bool = False
    token: str = ""
    polling: bool = True  # True=polling, False=webhook

@dataclass
class SlackConfig:
    enabled: bool = False
    bot_token: str = ""
    app_token: str = ""  # Socket Mode app token

@dataclass
class Config:
    # ... existing fields ...
    telegram: TelegramConfig = field(default_factory=TelegramConfig)
    slack: SlackConfig = field(default_factory=SlackConfig)
```

YAML 範例（在 docstring 或 config.yaml.example）：

```yaml
telegram:
  enabled: false
  token: "your_bot_token_here"
  polling: true

slack:
  enabled: false
  bot_token: "xoxb-..."
  app_token: "xapp-..."
```

### 3b. Main.py 啟動邏輯

**檔案**：`claw/main.py`

在 `lifespan()` 中，於 `gateway_module` 初始化後加入：

```python
import asyncio
from claw.core.config import get_config

@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = get_config()

    # ... existing storage, llm, memory init ...

    # Start channels
    channels = []

    if cfg.telegram.enabled:
        try:
            from claw.channels.telegram import TelegramChannel
            tg = TelegramChannel(
                token=cfg.telegram.token,
                base_url=f"http://localhost:{cfg.gateway.port}",
                polling=cfg.telegram.polling,
            )
            await tg.start()
            channels.append(tg)
            logger.info("Telegram channel started")
        except Exception as e:
            logger.error(f"Failed to start Telegram channel: {e}")

    if cfg.slack.enabled:
        try:
            from claw.channels.slack import SlackChannel
            slack = SlackChannel(
                bot_token=cfg.slack.bot_token,
                app_token=cfg.slack.app_token,
                base_url=f"http://localhost:{cfg.gateway.port}",
            )
            await slack.start()
            channels.append(slack)
            logger.info("Slack channel started")
        except Exception as e:
            logger.error(f"Failed to start Slack channel: {e}")

    yield

    # Cleanup
    for channel in channels:
        try:
            await channel.stop()
        except Exception as e:
            logger.error(f"Error stopping channel: {e}")

    # ... existing cleanup ...
```

**注意**：
- channel 啟動順序無關（並行可行）
- 啟動失敗不應中斷整體流程（try/except 包裝）
- 需在 yield 後優雅停止 channels

---

## STEP 4 — Channel 測試

### 4a. Telegram 測試

**檔案**：`tests/test_telegram.py`（已在 git status，需擴充）

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from claw.channels.telegram import TelegramChannel
import telegram


@pytest.mark.asyncio
async def test_telegram_private_message_session_id():
    """Private message should generate agent:tg:user:{id} session_id"""
    channel = TelegramChannel(token="test_token")

    # Mock update
    mock_update = MagicMock(spec=telegram.Update)
    mock_update.message.chat.type = "private"
    mock_update.message.from_user.id = 12345

    session_id = channel._get_session_id(mock_update)
    assert session_id == "agent:tg:user:12345"


@pytest.mark.asyncio
async def test_telegram_group_message_session_id():
    """Group message should generate agent:tg:group:{id} session_id"""
    channel = TelegramChannel(token="test_token")

    mock_update = MagicMock(spec=telegram.Update)
    mock_update.message.chat.type = "group"
    mock_update.message.chat.id = 67890

    session_id = channel._get_session_id(mock_update)
    assert session_id == "agent:tg:group:67890"


@pytest.mark.asyncio
async def test_telegram_on_message_posts_to_gateway():
    """on_message should POST to gateway with correct payload"""
    channel = TelegramChannel(token="test_token", base_url="http://test:8000")

    # Mock bot and httpx
    channel.bot = AsyncMock()
    mock_response = AsyncMock()

    # Mock SSE stream
    async def mock_stream(*args, **kwargs):
        lines = [
            'data: {"choices": [{"delta": {"content": "Hello"}}]}',
            'data: {"choices": [{"delta": {"content": " world"}}]}',
        ]
        for line in lines:
            yield line

    mock_response.aiter_lines = mock_stream

    with patch("httpx.AsyncClient.stream") as mock_client:
        mock_client.return_value.__aenter__.return_value = mock_response

        mock_update = MagicMock(spec=telegram.Update)
        mock_update.message.text = "Test message"
        mock_update.message.chat.type = "private"
        mock_update.message.from_user.id = 123

        mock_context = MagicMock()

        await channel.on_message(mock_update, mock_context)

        # Verify POST was called with correct payload
        mock_client.assert_called_once()
        call_args = mock_client.call_args
        assert call_args[0][0] == "POST"
        assert "http://test:8000/v1/chat/completions" in call_args[0][1]

        json_body = call_args[1]["json"]
        assert json_body["session_id"] == "agent:tg:user:123"
        assert json_body["messages"][0]["content"] == "Test message"


@pytest.mark.asyncio
async def test_telegram_send_response_with_throttle():
    """send_response should throttle messages"""
    channel = TelegramChannel(token="test_token")
    channel.bot = AsyncMock()

    long_text = "x" * 10000  # 10k chars, will split

    import time
    start = time.time()
    await channel._send_response(123, long_text)
    elapsed = time.time() - start

    # Should have called send_message 3 times (10000 / 4096 + 1)
    assert channel.bot.send_message.call_count == 3
    # Should have throttled (0.5s each time)
    assert elapsed >= 1.0  # 3 messages * 0.5s throttle
```

### 4b. Slack 測試

**檔案**：`tests/test_slack.py`（已在 git status，需擴充）

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from claw.channels.slack import SlackChannel


@pytest.mark.asyncio
async def test_slack_dm_session_id():
    """Direct message should generate agent:slack:dm:{user_id} session_id"""
    channel = SlackChannel(bot_token="test_bot", app_token="test_app")

    event = {
        "channel": "D123456",  # DM channels start with D
        "user": "U789",
    }

    session_id = channel._get_session_id(event)
    assert session_id == "agent:slack:dm:U789"


@pytest.mark.asyncio
async def test_slack_channel_mention_session_id():
    """Channel mention should generate agent:slack:channel:{channel_id} session_id"""
    channel = SlackChannel(bot_token="test_bot", app_token="test_app")

    event = {
        "channel": "C123456",  # Channel mentions
        "user": "U789",
    }

    session_id = channel._get_session_id(event)
    assert session_id == "agent:slack:channel:C123456"


@pytest.mark.asyncio
async def test_slack_on_mention_posts_to_gateway():
    """on_app_mention should POST to gateway"""
    channel = SlackChannel(bot_token="test_bot", app_token="test_app")
    channel.app = MagicMock()
    channel.app.client = AsyncMock()

    event = {
        "channel": "C123456",
        "user": "U789",
        "text": "<@U999> test query",
        "thread_ts": None,
    }

    # Mock httpx stream
    async def mock_stream(*args, **kwargs):
        lines = [
            'data: {"choices": [{"delta": {"content": "Response"}}]}',
        ]
        for line in lines:
            yield line

    mock_response = AsyncMock()
    mock_response.aiter_lines = mock_stream

    with patch("httpx.AsyncClient.stream") as mock_client:
        mock_client.return_value.__aenter__.return_value = mock_response

        await channel._on_app_mention(event)

        # Verify POST to gateway
        mock_client.assert_called_once()
        call_args = mock_client.call_args
        assert "chat/completions" in call_args[0][1]


@pytest.mark.asyncio
async def test_slack_thread_reply():
    """send_response should respect thread_ts"""
    channel = SlackChannel(bot_token="test_bot", app_token="test_app")
    channel.app = MagicMock()
    channel.app.client = AsyncMock()

    await channel._send_response("C123", "Test", thread_ts="123.456")

    # Verify chat_postMessage called with thread_ts
    channel.app.client.chat_postMessage.assert_called_once()
    call_kwargs = channel.app.client.chat_postMessage.call_args[1]
    assert call_kwargs["thread_ts"] == "123.456"
    assert call_kwargs["channel"] == "C123"
    assert call_kwargs["text"] == "Test"
```

### 4c. Config 測試（可選）

**檔案**：`tests/test_config.py`（擴充現有檔案）

```python
def test_telegram_config_defaults():
    """Telegram config should have sensible defaults"""
    from claw.core.config import TelegramConfig
    cfg = TelegramConfig()
    assert cfg.enabled == False
    assert cfg.token == ""
    assert cfg.polling == True


def test_slack_config_from_yaml():
    """Slack config should load from YAML"""
    import yaml
    yaml_str = """
slack:
  enabled: true
  bot_token: "xoxb-test"
  app_token: "xapp-test"
"""
    data = yaml.safe_load(yaml_str)
    from claw.core.config import SlackConfig
    slack_cfg = SlackConfig(**data["slack"])
    assert slack_cfg.enabled == True
    assert slack_cfg.bot_token == "xoxb-test"
```

---

## 驗收要求

完成後執行：

```bash
python -m pytest tests/test_telegram.py tests/test_slack.py -v
```

預期：**4+ passed**

再執行全套：

```bash
python -m pytest tests/ -v
```

預期：**95+ passed, 2 skipped**

---

## 回報格式

```
## STEP 3 完成報告
- 修改檔案：claw/core/config.py, claw/main.py
- 主要變更：
  - Config: TelegramConfig + SlackConfig dataclass
  - main.py: lifespan 中 channel 啟動邏輯
  - YAML config 例子

## STEP 4 完成報告
- 修改檔案：tests/test_telegram.py, tests/test_slack.py
- 新增測試：
  - test_telegram_private_message_session_id
  - test_telegram_group_message_session_id
  - test_telegram_on_message_posts_to_gateway
  - test_telegram_send_response_with_throttle
  - test_slack_dm_session_id
  - test_slack_channel_mention_session_id
  - test_slack_on_mention_posts_to_gateway
  - test_slack_thread_reply
- 測試結果：8 passed

## 整體結果
- 全套 pytest tests/：X passed, 2 skipped
- 遇到的問題：[若有]
```

---

## 提示

- 所有 async 操作要用 `AsyncMock`
- Gateway 在 localhost:8000（可配置）
- 模擬 httpx stream 時，記得 `async def mock_stream()` + `yield`
- Telegram rate limit 用 0.5s throttle
- Slack thread reply 的 `thread_ts` 來自 `event.get("thread_ts")`
