# PHASE 7.5 Gemini Worker Prompt — Warning Issues + Type Annotations

> 你是 claw-python 專案的 Gemini Worker Agent。
> **此任務是 PHASE 7.5 代碼品質改善工作的關鍵部分。**
> 請嚴格按照以下任務說明完成代碼修復。完成後回報每個 STEP 的修改摘要與測試結果。

---

## 專案背景

- **claw-python**：已完成 Phase 6，106 tests passing
- **當前狀態**：PM 審計發現 26 個 Pylance issues（8 critical + 12 warning）
- **PHASE 7.5 目標**：修復 warning + info issues，提升代碼品質至 95%+
- **你的獨立任務**：修復 12 個 warning issues + 相關的 type annotation

---

## 工作範圍

### Gemini 負責的 Warning Issues

你需要修復以下 **12 個 warning issues**：

| # | Issue 類型 | 位置 | 優先級 | 複雜度 |
|---|-----------|------|--------|--------|
| W1 | Type Annotation Style | 全局（gateway.py 等） | 🟡 高 | 低 |
| W2 | Memory Result Narrowing | loop.py:96-107 | 🟡 高 | 低 |
| W3 | Config Validation | main.py:62-85 | 🟡 高 | 中 |
| W4 | hasattr() Reliability | slack.py（已由 Codex 修） | 🟡 高 | 低 |
| W5-W8 | 其他 Type Issues | 各處 | 🟡 中 | 低 |
| W9-W12 | Error Handling 細分 | 各 Channel | 🟡 中 | 中 |

**Codex** 負責 critical issues。

---

## STEP 1 — Type Annotation 標準化

**目標**：統一代碼風格，使用 `X | None` 而非 `Optional[X]`

### 掃描和修改

#### 1a. 檔案列表

運行以下命令找出所有使用 `Optional` 的地方：

```bash
grep -r "Optional\[" claw/ --include="*.py" -n
```

預期結果（需要修改的文件）：
- `claw/core/gateway.py`（至少 3 個）
- `claw/agent/loop.py`（至少 2 個）
- `claw/memory/manager.py`（至少 1 個）
- `claw/channels/` 各文件（可能有）

#### 1b. 修改方案

對每個文件進行以下修改：

```python
# ❌ 舊風格
from typing import Optional

storage: Optional[Storage] = None
result: Optional[str] = None

# ✅ 新風格（Python 3.10+）
storage: Storage | None = None
result: str | None = None
```

**特別注意**：
- 移除 `from typing import Optional` 導入（如果不再使用）
- 檢查函數簽名：`def func() -> Optional[X]:` → `def func() -> X | None:`
- 檢查參數類型：`param: Optional[X] = None` → `param: X | None = None`

#### 1c. gateway.py 具體修改

```python
# claw/core/gateway.py
# ❌ 舊（第 5 行）
from typing import Optional

# ✅ 新（移除此行或保留但不使用）

# ❌ 舊（第 18-20 行）
storage: Optional[Storage] = None
queue: Optional[MessageQueue] = None
llm: Optional[LLMRouterClient] = None

# ✅ 新
storage: Storage | None = None
queue: MessageQueue | None = None
llm: LLMRouterClient | None = None
```

### 驗收標準

- [ ] 所有 `Optional[X]` 改為 `X | None`
- [ ] 所有 `Union[X, Y]` 改為 `X | Y`
- [ ] 移除不必要的 `Optional` 導入
- [ ] 運行 `pytest tests/ -v` 仍為 106/106 passed
- [ ] Pylance 中 Optional 相關警告消除

---

## STEP 2 — Memory Result 型別檢查

**檔案**：`claw/agent/loop.py`

### 問題描述

```python
# ❌ 現在（line 96-107）
if self.memory:
    try:
        recalled = await self.memory.search(user_message, session_id=session_id, limit=3)
        if recalled:  # ⚠️ recalled 可能為空列表，應檢查
            memory_lines = "\n".join(
                f"[Memory {i+1}] {item.get('content', '')[:300]}"
                for i, item in enumerate(recalled)
            )
```

### 規格

改進 None 和 empty list 檢查：

```python
# ✅ 修復後
if self.memory:
    try:
        recalled = await self.memory.search(
            user_message,
            session_id=session_id,
            limit=3
        )
        # 明確檢查 recalled 非空
        if recalled and len(recalled) > 0:
            memory_lines = "\n".join(
                f"[Memory {i+1}] {item.get('content', '')[:300]}"
                for i, item in enumerate(recalled)
            )
            if memory_lines:
                sys_prompt += f"\n\n=== Recalled Memories ===\n{memory_lines}"
                logger.debug(f"Recalled {len(recalled)} memories for session {session_id}")
    except Exception as e:
        logger.warning(f"Memory recall failed: {e}")
        # 繼續執行，不中斷 LLM 調用
```

### 驗收標準

- [ ] 添加了 `len(recalled) > 0` 檢查
- [ ] 添加了 `memory_lines` 的檢查
- [ ] 添加了 debug 日誌
- [ ] 異常處理使用 warning 級別（不影響流程）
- [ ] 運行 `pytest tests/test_agent_loop.py -v` 全部通過

---

## STEP 3 — Configuration 驗證

**檔案**：`claw/main.py`

### 問題描述

```python
# ❌ 現在（line 59-85）
if cfg.telegram.enabled:
    try:
        from claw.channels.telegram import TelegramChannel
        tg = TelegramChannel(
            token=cfg.telegram.token,  # ⚠️ 未驗證 token 非空
            base_url=f"http://localhost:{cfg.gateway.port}",
            polling=cfg.telegram.polling,
        )
```

### 規格

添加配置驗證邏輯：

```python
# ✅ 修復後 - Telegram
if cfg.telegram.enabled:
    # ✅ 驗證必需配置
    if not cfg.telegram.token or not cfg.telegram.token.strip():
        logger.error(
            "Telegram is enabled but token is empty or whitespace. "
            "Set TELEGRAM_TOKEN environment variable or "
            "configure telegram.token in config/default.yaml"
        )
        # 跳過 Telegram 啟動，不中斷全局啟動
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
            logger.info("Telegram channel started successfully")
        except Exception as e:
            logger.error(f"Failed to start Telegram channel: {e}")

# ✅ 修復後 - Slack
if cfg.slack.enabled:
    # ✅ 驗證必需配置
    if not cfg.slack.bot_token or not cfg.slack.app_token:
        logger.error(
            "Slack is enabled but bot_token or app_token is empty. "
            "Set SLACK_BOT_TOKEN and SLACK_APP_TOKEN environment variables or "
            "configure slack.bot_token and slack.app_token in config/default.yaml"
        )
        # 跳過 Slack 啟動，不中斷全局啟動
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
            logger.info("Slack channel started successfully")
        except Exception as e:
            logger.error(f"Failed to start Slack channel: {e}")
```

### 驗收標準

- [ ] Telegram 配置驗證已添加
- [ ] Slack 配置驗證已添加
- [ ] 缺失配置時記錄 error 日誌但不中斷啟動
- [ ] 成功啟動時記錄 info 日誌
- [ ] 運行 `pytest tests/test_main.py -v` 全部通過（可能需要更新 mock）

---

## STEP 4 — Error Handling 細分

**目標**：改進異常處理，不應捕捉過於寬泛的 `Exception`

### 4a. channels/telegram.py 改進

```python
# ❌ 現在
except Exception as e:
    logger.error(f"Telegram gateway error: {e}")
    await self._send_response(chat_id, f"Error: {e}")

# ✅ 修復後
except asyncio.TimeoutError:
    logger.error(f"Gateway timeout for session {session_id}")
    await self._send_response(chat_id, "Error: Request timeout, please try again")
except httpx.HTTPStatusError as e:
    logger.error(f"Gateway HTTP error: {e.status_code} - {e.response.text}")
    await self._send_response(chat_id, f"Error: Gateway returned {e.status_code}")
except Exception as e:
    logger.error(f"Unexpected error in telegram handler", exc_info=True)
    await self._send_response(chat_id, "Error: Internal server error")
```

### 4b. channels/slack.py 改進

```python
# ❌ 現在
except Exception as e:
    logger.error(f"Slack gateway error: {e}")
    await self._send_response(channel, f"Error: {e}")

# ✅ 修復後
except asyncio.TimeoutError:
    logger.error(f"Gateway timeout for session {session_id}")
    await self._send_response(channel, "Error: Request timeout")
except httpx.HTTPStatusError as e:
    logger.error(f"Gateway HTTP error: {e.status_code}")
    await self._send_response(channel, f"Error: Gateway returned {e.status_code}")
except Exception as e:
    logger.error(f"Unexpected error in slack handler", exc_info=True)
    await self._send_response(channel, "Error: Internal server error")
```

### 驗收標準

- [ ] 添加了 asyncio.TimeoutError 捕捉
- [ ] 添加了 httpx.HTTPStatusError 捕捉
- [ ] 保留了寬泛的 Exception 作為後備
- [ ] 使用 `exc_info=True` 記錄完整堆棧
- [ ] 測試仍通過

---

## STEP 5 — 其他 Type Annotation 改進

**檔案**：各個需要改進的文件

### 5a. Dictionary 和 List 類型提示

```python
# ❌ 舊
def func(data: dict):
    pass

# ✅ 新
def func(data: dict[str, Any]):
    pass
```

### 5b. 使用 from __future__ import annotations

在文件開頭添加（如果不存在）：

```python
from __future__ import annotations
```

這允許使用更清晰的類型提示（如 `X | None`）而無需字符串化。

### 5c. Type Guard 使用

```python
# ✅ 改進
if not isinstance(value, str):
    logger.error(f"Expected str, got {type(value)}")
    return None

# 現在 Pylance 知道 value 是 str
```

### 驗收標準

- [ ] 所有主要文件都有 `from __future__ import annotations`
- [ ] Dict/List 類型提示更具體（帶有泛型參數）
- [ ] 使用了 type guard（isinstance）確認類型

---

## STEP 6 — 補充測試（Warning Issues）

**檔案**：`tests/test_main.py`、`tests/test_agent_loop.py`、`tests/test_channels.py`（新建或擴充）

### 規格

添加補充測試確保修復的邏輯正確：

```python
# tests/test_main.py - 補充
@pytest.mark.asyncio
async def test_main_lifespan_telegram_empty_token():
    """Telegram enabled 但 token 為空時應跳過啟動"""
    mock_app = MagicMock()

    with patch("claw.main.get_config") as mock_get_cfg:
        mock_cfg = MagicMock()
        mock_cfg.telegram.enabled = True
        mock_cfg.telegram.token = ""  # 空 token
        mock_cfg.slack.enabled = False
        mock_get_cfg.return_value = mock_cfg

        with patch("claw.main.Storage", return_value=AsyncMock()):
            with patch("claw.main.LLMRouterClient", return_value=AsyncMock()):
                with patch("claw.memory.sqlite_store.MemoryStore", return_value=AsyncMock()):
                    # 應不拋出異常，但不啟動 Telegram
                    async with lifespan(mock_app):
                        pass

# tests/test_agent_loop.py - 補充
@pytest.mark.asyncio
async def test_agent_loop_memory_recall_empty_list():
    """Memory recall 返回空列表時應不報錯"""
    # 準備 mock
    mock_storage = AsyncMock()
    mock_storage.get_session = AsyncMock(return_value=SessionRow(...))

    mock_llm = AsyncMock()
    mock_memory = AsyncMock()
    mock_memory.search = AsyncMock(return_value=[])  # 空列表

    loop = AgentLoop(storage=mock_storage, llm=mock_llm, memory=mock_memory)

    # 運行 agent
    events = []
    async for event in loop.run(session_id="test", user_message="hello"):
        events.append(event)

    # 應完成執行，不報錯
    assert any(isinstance(e, RunComplete) for e in events)

# tests/test_channels.py（新建）- 補充
@pytest.mark.asyncio
async def test_telegram_error_handling_timeout():
    """on_message 在 timeout 時應發送友好錯誤訊息"""
    ch = TelegramChannel("token")

    async def mock_call_gateway(*args, **kwargs):
        raise asyncio.TimeoutError("Gateway timeout")

    ch._call_gateway = mock_call_gateway

    sent_messages = []

    async def mock_send_response(chat_id, text):
        sent_messages.append((chat_id, text))

    ch._send_response = mock_send_response

    # 模擬 on_message 呼叫
    update = SimpleNamespace(message=SimpleNamespace(
        text="test",
        chat=SimpleNamespace(id=123, type="private"),
        from_user=SimpleNamespace(id=456)
    ))

    await ch.on_message(update, None)

    # 驗證發送了錯誤訊息
    assert len(sent_messages) == 1
    assert sent_messages[0][0] == 123
    assert "timeout" in sent_messages[0][1].lower()
```

### 驗收標準

- [ ] 添加了 3-4 個補充測試
- [ ] 測試覆蓋 config 驗證、memory 空列表、error handling
- [ ] 所有新測試通過
- [ ] 全套 `pytest tests/ -v` 為 110+ passed

---

## 驗收要求

完成後執行以下命令進行驗收：

```bash
# 運行修復相關的測試
python -m pytest tests/test_main.py tests/test_agent_loop.py -v

# 運行全套測試
python -m pytest tests/ -v

# 檢查 Optional 是否被正確替換
grep -r "Optional\[" claw/ --include="*.py" | grep -v "# " | wc -l
# 預期：0
```

**預期結果**：
- 所有測試通過（110+ passed）
- No remaining `Optional[X]` in code（除了注釋或字符串）
- Pylance 警告大幅減少

---

## 回報格式

完成後按以下格式回報：

```
## STEP 1 完成報告
- 修改：統一 Type Annotation 風格
  - Optional[X] → X | None: N 個修改
  - Union[X, Y] → X | Y: M 個修改
  - 受影響文件：gateway.py, loop.py, memory/manager.py, ...
- 驗證：grep 確認無剩餘 Optional 使用，所有測試通過

## STEP 2 完成報告
- 檔案：claw/agent/loop.py
- 修改：Memory recall 結果型別檢查改進
- 驗證：test_agent_loop.py 全部通過

## STEP 3 完成報告
- 檔案：claw/main.py
- 修改：Telegram 和 Slack 配置驗證邏輯
  - Telegram token 非空檢查
  - Slack token 非空檢查
  - 缺失配置時優雅跳過，不中斷啟動
- 驗證：test_main.py 全部通過

## STEP 4 完成報告
- 檔案：claw/channels/telegram.py + slack.py
- 修改：Error handling 細分
  - asyncio.TimeoutError 特別處理
  - httpx.HTTPStatusError 特別處理
  - 通用 Exception 作為後備
- 驗證：Channel 相關測試通過

## STEP 5 完成報告
- 修改：其他 Type Annotation 改進
  - Dict/List 泛型參數補全
  - from __future__ import annotations 添加
  - Type guard（isinstance）使用改進
- 驗證：所有受影響的測試通過

## STEP 6 完成報告
- 檔案：tests/test_main.py + test_agent_loop.py + test_channels.py
- 新增：4-5 個補充測試
  - Config validation 測試
  - Memory empty list 測試
  - Error handling timeout 測試
- 驗證：全部新測試通過，總計 110+ passed

## 整體結果
- 修復 Issues：12 個 warning + 6 個 info
- 測試成績：110+ passed (or 106 if no new tests added)
- Code Quality：提升至 9.5+/10
- Type Annotation Coverage：提升至 90%+
```

---

## 技術提示

1. **Optional 風格**：Python 3.10+ 推薦使用 `X | None`
2. **Type Guard**：使用 `isinstance()` 讓 Pylance 理解類型已驗證
3. **配置驗證**：檢查 token 非空且非 whitespace（使用 `.strip()`）
4. **Error 細分**：區分 TimeoutError、HTTPStatusError 和其他 Exception
5. **日誌級別**：Warning 用於預期的錯誤，Error 用於異常情況

---

## 注意事項

- ⚠️ 修復後所有現有測試（106 個）必須仍通過
- ⚠️ 不應改變任何公開 API 的簽名
- ⚠️ Type annotation 改進應保持代碼含義不變
- ⚠️ 配置驗證失敗時應記錄清晰的錯誤訊息，指導用戶如何修復
- ⚠️ 完成後應自行運行 pytest 驗證，不應交付有失敗的測試

---

**預期完成時間**：4-6 小時（包含補充測試）

**完成後** PM 將驗證所有修復並生成 PHASE 7.5 完成報告。
