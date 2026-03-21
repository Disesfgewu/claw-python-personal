# PHASE 7.5 Codex Worker Prompt — Critical Pylance Fixes

> 你是 claw-python 專案的 Codex Worker Agent。
> **此任務是 PHASE 7.5 代碼品質改善工作的關鍵部分。**
> 請嚴格按照以下任務說明完成代碼修復。完成後回報每個 STEP 的修改摘要與測試結果。

---

## 專案背景

- **claw-python**：已完成 Phase 6，106 tests passing
- **當前狀態**：PM 審計發現 26 個 Pylance issues（8 critical + 12 warning）
- **PHASE 7.5 目標**：修復 critical + warning issues，提升代碼品質至 95%+
- **你的獨立任務**：修復 4 個 critical issues + 相關 warning issues

---

## 工作範圍

### Codex 負責的 Critical Issues

你需要修復以下 **4 個 critical issues** + **相關的 warning issues**：

| Issue | 位置 | 優先級 | 複雜度 |
|-------|------|--------|--------|
| P1 | gateway.py:23 | 🔴 Critical | 低 |
| P2 | telegram.py:44 | 🔴 Critical | 低 |
| P3 | slack.py:48 | 🔴 Critical | 低 |
| P4 | memory/manager.py:58 | 🔴 Critical | 中 |

**Gemini** 負責其他 warning issues 和配置驗證。

---

## STEP 1 — gateway.py 修復

**檔案**：`claw/core/gateway.py`

### 問題描述

```python
# ❌ 現在（line 23-26）
def _require_dependencies() -> tuple[Storage, MessageQueue, LLMRouterClient]:
    if storage is None or queue is None or llm is None:
        raise RuntimeError("gateway dependencies are not configured")
    return storage, queue, llm  # Pylance 警告：可能返回 None
```

### 規格

修復類型檢查問題，確保 Pylance 不報錯：

```python
# ✅ 修復後
def _require_dependencies() -> tuple[Storage, MessageQueue, LLMRouterClient]:
    if storage is None or queue is None or llm is None:
        raise RuntimeError("gateway dependencies are not configured")
    assert storage is not None
    assert queue is not None
    assert llm is not None
    return storage, queue, llm
```

### 驗收標準

- [ ] 修改後 `_require_dependencies()` 函數無 Pylance 類型警告
- [ ] 運行 `pytest tests/test_gateway.py -v` 全部通過
- [ ] 全套 `pytest tests/ -v` 仍為 106/106 passed

---

## STEP 2 — telegram.py 修復

**檔案**：`claw/channels/telegram.py`

### 問題描述

```python
# ❌ 現在（line 44-46）
async def start(self) -> None:
    # ...
    if self.polling and self.app.updater:  # ❌ Pylance：updater 可能為 None
        await self.app.updater.start_polling()
```

### 規格

添加 None 檢查，並改進日誌記錄：

```python
# ✅ 修復後
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
            logger.info("TelegramChannel polling started successfully")
        else:
            logger.warning("No updater available, polling mode disabled")
    else:
        logger.info("TelegramChannel started in webhook mode (not implemented)")
```

### 驗收標準

- [ ] 修改後 `start()` 方法無 Pylance None guard 警告
- [ ] 添加適當的日誌記錄（info/warning）
- [ ] 運行 `pytest tests/test_telegram.py -v` 全部通過
- [ ] 全套 `pytest tests/ -v` 仍為 106/106 passed

---

## STEP 3 — slack.py 修復

**檔案**：`claw/channels/slack.py`

### 問題描述

```python
# ❌ 現在（line 47-51）
self._socket_handler = AsyncSocketModeHandler(self.app, self.app_token)
if hasattr(self._socket_handler, "start_async"):  # ❌ hasattr 不可靠
    await self._socket_handler.start_async()
else:
    await self._socket_handler.start()
```

### 規格

改為異常處理方式，更加健壯：

```python
# ✅ 修復後
self._socket_handler = AsyncSocketModeHandler(self.app, self.app_token)

# 嘗試新版本方法，回退到舊版本
try:
    await self._socket_handler.start_async()
    logger.info("SlackChannel started with start_async() (new API)")
except AttributeError:
    logger.info("Using legacy SlackChannel.start() method (old API)")
    await self._socket_handler.start()
```

### 驗收標準

- [ ] 修改後 `start()` 方法無 Pylance hasattr 警告
- [ ] 添加適當的日誌記錄
- [ ] 異常處理邏輯清晰
- [ ] 運行 `pytest tests/test_slack.py -v` 全部通過
- [ ] 全套 `pytest tests/ -v` 仍為 106/106 passed

---

## STEP 4 — memory/manager.py 修復

**檔案**：`claw/memory/manager.py`

### 問題描述

```python
# ❌ 現在（line 56-66）
async def _get_embedding(self, text: str) -> list[float]:
    try:
        resp = await self.llm._client.post(  # ❌ 訪問私有 API
            f"{self.llm.base_url}/v1/embeddings",
            json={"input": text, "model": "default"},
        )
```

### 規格

此問題需要兩部分修復：

#### A. 在 `claw/llm/router_client.py` 中添加公開方法

在 `LLMRouterClient` 類中添加新方法：

```python
# claw/llm/router_client.py 中添加
async def get_embedding(self, text: str) -> list[float]:
    """
    Generate embedding via /v1/embeddings endpoint.

    Args:
        text: Input text to embed

    Returns:
        Embedding vector as list of floats

    Raises:
        Exception: If embedding generation fails
    """
    try:
        resp = await self._client.post(
            f"{self.base_url}/v1/embeddings",
            json={"input": text, "model": "default"},
        )
        resp.raise_for_status()
        data = resp.json()
        if "data" not in data or len(data["data"]) == 0:
            raise ValueError("Invalid embedding response format")
        return data["data"][0]["embedding"]
    except Exception as e:
        logger.error(f"Embedding request failed: {e}")
        raise
```

#### B. 在 `claw/memory/manager.py` 中改用公開方法

```python
# ✅ 修復後
async def _get_embedding(self, text: str) -> list[float]:
    try:
        # 使用公開 API 而非私有成員
        embedding = await self.llm.get_embedding(text)
        return embedding
    except Exception as e:
        logger.error(f"Embedding generation failed: {e}")
        return [0.0] * _FALLBACK_DIM
```

### 驗收標準

- [ ] 在 `LLMRouterClient` 中添加了 `get_embedding()` 公開方法
- [ ] `MemoryManager._get_embedding()` 改為使用公開方法
- [ ] 無 Pylance 私有 API 訪問警告
- [ ] 錯誤處理完善
- [ ] 運行 `pytest tests/test_memory.py -v` 全部通過
- [ ] 運行 `pytest tests/test_router_client.py -v` 全部通過
- [ ] 全套 `pytest tests/ -v` 仍為 106/106 passed

---

## STEP 5 — 補充測試（針對修復的代碼）

**檔案**：`tests/test_gateway.py`、`tests/test_telegram.py`、`tests/test_slack.py`、`tests/test_router_client.py`

### 規格

為修復的代碼添加補充測試，確保邏輯正確：

```python
# tests/test_gateway.py - 添加
@pytest.mark.asyncio
async def test_require_dependencies_with_all_none():
    """_require_dependencies 在所有依賴都是 None 時應拋出異常"""
    import claw.core.gateway as gw
    # 保存原始值
    original_storage = gw.storage
    original_queue = gw.queue
    original_llm = gw.llm

    try:
        # 設置為 None
        gw.storage = None
        gw.queue = None
        gw.llm = None

        with pytest.raises(RuntimeError, match="dependencies are not configured"):
            gw._require_dependencies()
    finally:
        # 恢復原始值
        gw.storage = original_storage
        gw.queue = original_queue
        gw.llm = original_llm

# tests/test_telegram.py - 添加
@pytest.mark.asyncio
async def test_telegram_start_with_polling_enabled(monkeypatch):
    """start() 在 polling=True 且 updater 存在時應調用 start_polling()"""
    ch = TelegramChannel("test_token", polling=True)

    # Mock Application 和 updater
    mock_updater = AsyncMock()
    mock_app = AsyncMock()
    mock_app.updater = mock_updater

    async def mock_builder_build():
        return mock_app

    mock_builder = MagicMock()
    mock_builder.build.return_value = mock_app
    mock_builder.token.return_value = mock_builder

    monkeypatch.setattr("telegram.ext.Application.builder", lambda: mock_builder)

    await ch.start()

    # 驗證 start_polling 被調用
    mock_updater.start_polling.assert_called_once()

# tests/test_slack.py - 添加
@pytest.mark.asyncio
async def test_slack_start_fallback_to_old_api(monkeypatch):
    """start() 當 start_async() 不存在時應回退到 start()"""
    ch = SlackChannel("xoxb-token", "xapp-token")

    mock_handler = AsyncMock()
    # 模擬 start_async() 不存在
    del mock_handler.start_async

    monkeypatch.setattr("slack_bolt.adapter.socket_mode.AsyncSocketModeHandler",
                       lambda *args, **kwargs: mock_handler)

    # 應不拋出異常，改為調用 start()
    await ch.start()
    mock_handler.start.assert_called_once()

# tests/test_router_client.py - 添加
@pytest.mark.asyncio
async def test_llm_router_get_embedding_success(monkeypatch):
    """get_embedding() 應正確返回嵌入向量"""
    client = LLMRouterClient(base_url="http://localhost:8000")

    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "data": [{"embedding": [0.1, 0.2, 0.3]}]
    }
    mock_resp.raise_for_status = MagicMock()

    mock_post = AsyncMock(return_value=mock_resp)
    monkeypatch.setattr(client._client, "post", mock_post)

    result = await client.get_embedding("test text")

    assert result == [0.1, 0.2, 0.3]
    mock_post.assert_called_once()
```

### 驗收標準

- [ ] 添加了 4 個補充測試（gateway + telegram + slack + router）
- [ ] 所有新測試通過
- [ ] 全套 `pytest tests/ -v` 為 110/110 passed（106 + 4 新）

---

## 驗收要求

完成後執行以下命令進行驗收：

```bash
# 運行修復相關的測試
python -m pytest tests/test_gateway.py tests/test_telegram.py tests/test_slack.py tests/test_router_client.py tests/test_memory.py -v

# 運行全套測試
python -m pytest tests/ -v
```

**預期結果**：
- 所有測試通過（110/110 或更多，因為可能有額外補充）
- 沒有新的 Pylance 警告
- Code quality 評分提升

---

## 回報格式

完成後按以下格式回報：

```
## STEP 1 完成報告
- 檔案：claw/core/gateway.py
- 修改：_require_dependencies() 添加 assert 確認非 None
- 驗證：無 Pylance 類型警告，所有相關測試通過

## STEP 2 完成報告
- 檔案：claw/channels/telegram.py
- 修改：start() 添加 updater None 檢查，改進日誌
- 驗證：無 Pylance 警告，test_telegram.py 全部通過

## STEP 3 完成報告
- 檔案：claw/channels/slack.py
- 修改：start() 改為異常處理 start_async/start()
- 驗證：無 Pylance hasattr 警告，test_slack.py 全部通過

## STEP 4 完成報告
- 檔案：claw/llm/router_client.py（新增）+ claw/memory/manager.py（修改）
- 修改：
  - LLMRouterClient 添加公開方法 get_embedding()
  - MemoryManager._get_embedding() 改用公開 API
- 驗證：無私有 API 訪問警告，test_memory.py + test_router_client.py 全部通過

## STEP 5 完成報告
- 檔案：tests/test_gateway.py + test_telegram.py + test_slack.py + test_router_client.py
- 新增：4 個補充測試
- 驗證：全部新測試通過，總計 110+ passed

## 整體結果
- 修復 Issues：4 個 critical + 相關 warning
- 測試成績：110/110 passed (或更多)
- Code Quality：提升至 9.5/10
- Pylance 警告：降至 0 (critical) + 8 (warning)
```

---

## 技術提示

1. **Assert 語句**：用於類型檢查，讓 Pylance 理解類型已確認
2. **None Guard**：在使用 Optional 類型前總是檢查 None
3. **異常處理**：優於 hasattr()，更清晰且更可靠
4. **公開 API**：不應訪問以 `_` 開頭的私有成員
5. **測試覆蓋**：修復的代碼應有補充測試確保邏輯正確

---

## 注意事項

- ⚠️ 修復後所有現有測試（106 個）必須仍通過
- ⚠️ 不應改變任何公開 API 的簽名
- ⚠️ 所有修改應有清晰的日誌記錄
- ⚠️ 異常處理應細分（不應捕捉過於寬泛的 Exception）
- ⚠️ 完成後應自行運行 pytest 驗證，不應交付有失敗的測試

---

**預期完成時間**：4-6 小時（包含測試）

**完成後** PM 將驗證所有修復並生成 PHASE 7.5 完成報告。
