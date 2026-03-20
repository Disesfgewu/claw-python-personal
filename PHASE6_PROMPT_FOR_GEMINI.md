# Phase 6 Gemini Worker Prompt — Config + Main + Tests（獨立並行）

你是 claw-python 專案的 Gemini Worker Agent。
**此任務與 Codex 完全獨立，可並行執行，無依賴關係。**

請嚴格按照以下任務說明完成程式碼修改與測試撰寫。完成後回報每個 STEP 的修改摘要與測試結果。

---

## 專案背景

- **claw-python**：Python AI Agent OS，當前 Phase 5 完成（92 tests pass）
- Phase 6 目標：Channel adapters（Telegram + Slack）
- **你的獨立任務**：Config 系統 + main.py 啟動邏輯 + 整合測試框架

### 基礎已備

- `claw/core/config.py` — 既有 Config 系統
- `claw/main.py` — FastAPI lifespan 啟動邏輯
- Codex 會獨立完成 `claw/channels/telegram.py` 和 `claw/channels/slack.py`

### 你的工作範圍（完全獨立）

- **STEP 1**：Config schema 擴充（TelegramConfig、SlackConfig）
- **STEP 2**：main.py 中的 channel 啟動邏輯（使用 mock Channel 測試）
- **STEP 3**：Config + Main 整合測試（4 tests）

Codex 獨立負責 Channel 實作，與你的工作完全無關。

---

## STEP 1 — Config Schema 擴充

**檔案**：`claw/core/config.py`

### 規格

在現有 `Config` dataclass 中增加兩個新欄位：

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

    # 新增以下兩行
    telegram: TelegramConfig = field(default_factory=TelegramConfig)
    slack: SlackConfig = field(default_factory=SlackConfig)
```

### YAML 範例（在 docstring 或 README 中註記）

```yaml
# config.yaml
telegram:
  enabled: false
  token: "your_bot_token"
  polling: true

slack:
  enabled: false
  bot_token: "xoxb-..."
  app_token: "xapp-..."
```

### 驗證要點

- Config 無 channel 配置時，使用預設值（enabled=False）
- Config 從 YAML 讀取時，正確解析 telegram/slack 段
- 不存在 YAML 時，用預設值

---

## STEP 2 — main.py 啟動邏輯

**檔案**：`claw/main.py`

### 規格

在 `lifespan()` 函數中，於 storage/llm/memory 初始化後加入：

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # ... existing storage, llm, memory init ...

    # 新增 channel 啟動邏輯
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

    # Cleanup: 優雅停止所有 channels
    for channel in channels:
        try:
            await channel.stop()
        except Exception as e:
            logger.error(f"Error stopping channel: {e}")

    # ... existing cleanup ...
```

### 關鍵點

- 啟動失敗不應中斷整體流程（try/except 包裝）
- channel 列表用於 cleanup
- Cleanup 應在 yield 後執行
- Import 放在 try 內（package 可能未裝）
- logger 用 logging（不是 print）

---

## STEP 3 — Config + Main 整合測試

### 3a. Config 測試

**檔案**：`tests/test_config.py`（擴充現有檔案）

新增測試：

```python
def test_telegram_config_defaults():
    """TelegramConfig 應有正確預設值"""
    from claw.core.config import TelegramConfig
    cfg = TelegramConfig()
    assert cfg.enabled == False
    assert cfg.token == ""
    assert cfg.polling == True


def test_slack_config_defaults():
    """SlackConfig 應有正確預設值"""
    from claw.core.config import SlackConfig
    cfg = SlackConfig()
    assert cfg.enabled == False
    assert cfg.bot_token == ""
    assert cfg.app_token == ""
```

### 3b. Main 啟動邏輯測試

**檔案**：`tests/test_main.py`（新建）

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from claw.main import lifespan


@pytest.mark.asyncio
async def test_main_lifespan_telegram_disabled():
    """Telegram disabled 時，不應啟動"""
    mock_app = MagicMock()

    with patch("claw.main.get_config") as mock_get_cfg:
        mock_cfg = MagicMock()
        mock_cfg.telegram.enabled = False
        mock_cfg.slack.enabled = False
        mock_get_cfg.return_value = mock_cfg

        with patch("claw.main.Storage"):
            with patch("claw.main.LLMRouterClient"):
                with patch("claw.main.MemoryStore"):
                    async with lifespan(mock_app):
                        pass  # No exception


@pytest.mark.asyncio
async def test_main_lifespan_telegram_starts():
    """Telegram enabled 時，應呼叫 start()"""
    mock_app = MagicMock()

    with patch("claw.main.get_config") as mock_get_cfg:
        mock_cfg = MagicMock()
        mock_cfg.telegram.enabled = True
        mock_cfg.telegram.token = "test_token"
        mock_cfg.telegram.polling = True
        mock_cfg.slack.enabled = False
        mock_cfg.gateway.port = 8000
        mock_get_cfg.return_value = mock_cfg

        mock_tg = AsyncMock()

        with patch("claw.main.Storage"):
            with patch("claw.main.LLMRouterClient"):
                with patch("claw.main.MemoryStore"):
                    with patch("claw.channels.telegram.TelegramChannel", return_value=mock_tg):
                        async with lifespan(mock_app):
                            pass

                        # Verify start() and stop() were called
                        mock_tg.start.assert_called_once()
                        mock_tg.stop.assert_called_once()


@pytest.mark.asyncio
async def test_main_lifespan_slack_starts():
    """Slack enabled 時，應呼叫 start()"""
    mock_app = MagicMock()

    with patch("claw.main.get_config") as mock_get_cfg:
        mock_cfg = MagicMock()
        mock_cfg.telegram.enabled = False
        mock_cfg.slack.enabled = True
        mock_cfg.slack.bot_token = "xoxb-test"
        mock_cfg.slack.app_token = "xapp-test"
        mock_cfg.gateway.port = 8000
        mock_get_cfg.return_value = mock_cfg

        mock_slack = AsyncMock()

        with patch("claw.main.Storage"):
            with patch("claw.main.LLMRouterClient"):
                with patch("claw.main.MemoryStore"):
                    with patch("claw.channels.slack.SlackChannel", return_value=mock_slack):
                        async with lifespan(mock_app):
                            pass

                        mock_slack.start.assert_called_once()
                        mock_slack.stop.assert_called_once()


@pytest.mark.asyncio
async def test_main_lifespan_channel_error_not_fatal():
    """Channel 啟動失敗應被 try/except 捕捉，不中斷"""
    mock_app = MagicMock()

    with patch("claw.main.get_config") as mock_get_cfg:
        mock_cfg = MagicMock()
        mock_cfg.telegram.enabled = True
        mock_cfg.telegram.token = "test_token"
        mock_cfg.slack.enabled = False
        mock_cfg.gateway.port = 8000
        mock_get_cfg.return_value = mock_cfg

        # Mock TelegramChannel 建立失敗
        with patch("claw.main.Storage"):
            with patch("claw.main.LLMRouterClient"):
                with patch("claw.main.MemoryStore"):
                    with patch("claw.channels.telegram.TelegramChannel", side_effect=Exception("Token invalid")):
                        # 應不拋出異常
                        async with lifespan(mock_app):
                            pass
```

---

## 驗收要求

完成後執行：

```bash
# Config 測試
python -m pytest tests/test_config.py::test_telegram_config_defaults tests/test_config.py::test_slack_config_defaults -v

# Main 測試
python -m pytest tests/test_main.py -v
```

預期：**6 passed**（Config 2 + Main 4）

再執行全套：

```bash
python -m pytest tests/ -v
```

預期：**92+ passed, 2 skipped**（Phase 5 baseline 維持）

---

## 回報格式

```
## STEP 1 完成報告
- 檔案：claw/core/config.py
- 修改：新增 TelegramConfig、SlackConfig dataclass
  - TelegramConfig: enabled, token, polling
  - SlackConfig: enabled, bot_token, app_token
- 驗證：Config 無值時用預設值、YAML 讀取正確

## STEP 2 完成報告
- 檔案：claw/main.py
- 修改：lifespan() 中新增 channel 啟動和清理邏輯
  - try/except 包裝啟動，避免失敗中斷
  - yield 後 cleanup 所有 channels
  - Import 在 try 內（package 可能未裝）
- 驗證：Mock 測試確認啟動/停止邏輯

## STEP 3 完成報告
- 檔案：tests/test_config.py（+2）、tests/test_main.py（新建 +4）
- 測試驗證：
  - Config 預設值正確
  - Channel disabled 時不啟動
  - Channel enabled 時啟動 start()/stop()
  - 啟動失敗被 try/except 捕捉

## 整體結果
- 新增測試：6 tests（config 2 + main 4）
- pytest tests/ -v：92+ passed, 2 skipped（Phase 5 baseline）
- **完全獨立完成，無需等待 Codex**
```

---

## 技術提示

- Mock 要用 `AsyncMock()` 非 `MagicMock()`（async 方法）
- `patch()` context manager 可以嵌套
- 測試 lifespan 時，用 `async with lifespan(mock_app):` 進出
- `assert_called_once()` 驗證方法被呼叫一次
- Import 在 try 外時，如果 package 未裝會導致 import error — 應在 try 內
