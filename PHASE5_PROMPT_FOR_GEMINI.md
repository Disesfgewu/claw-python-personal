# Phase 5 Gemini Worker Prompt — main.py 初始化 + 整合測試

你是 claw-python 專案的 Gemini Worker Agent。
請嚴格按照以下任務說明完成程式碼修改與測試撰寫。
完成後回報每個 STEP 的修改摘要與測試結果。

---

## 專案背景

- **claw-python**：Python AI Agent OS，目標硬體 Jetson Orin Nano Super
- Phase 1-4 已完成，Phase 5 目標：將 Memory/RAG 串接入主執行流程

### 已完成（Codex 負責）

- STEP 1：`build_context()` 已接受 `context_builder` 參數並串接 ContextBuilder
- STEP 2：`AgentLoop` 已接受 `memory` 參數並實作自動召回/存記

### 你負責的部分

- STEP 3：`main.py` 初始化 MemoryStore + MemoryManager
- STEP 4：MemoryManager 單元測試（RRF fusion + temporal decay）
- STEP 5：整合測試（build_context + memory_tools）

---

## STEP 3 — 更新 main.py 初始化 Memory

**目標檔案**：`claw/main.py`

### 規格

在 `lifespan()` 函數中，於 `storage.init()` 之後加入：

```python
import os
import claw.tools.memory_tools as _mem_tools
from claw.memory.sqlite_store import MemoryStore
from claw.memory.manager import MemoryManager

# Memory 初始化
mem_db_path = os.path.join(
    os.path.dirname(os.path.expanduser(cfg.storage.db_path)),
    "memory.db"
)
mem_store = MemoryStore(db_path=mem_db_path)
await mem_store.init()
memory_manager = MemoryManager(store=mem_store, llm=llm)
_mem_tools.set_memory_manager(memory_manager)
gateway_module.memory = memory_manager
```

在頂層 import 區加入：
```python
import claw.tools.memory_tools  # 觸發 memory_save / memory_search 工具注冊
```

更新 `gateway.py` 的 `get_agent_loop()` 函數：

**目標檔案**：`claw/core/gateway.py`

```python
def get_agent_loop() -> AgentLoop:
    storage_impl, _, llm_impl = _require_dependencies()
    mem = getattr(gateway_module, 'memory', None)  # 可能為 None（測試環境）
    return AgentLoop(storage=storage_impl, llm=llm_impl, memory=mem)
```

注意：在 gateway.py 的 module 頂部增加：
```python
import claw.core.gateway as gateway_module  # self-reference for memory attr
```
不對，gateway.py 本身不需要這個。正確做法：
```python
def get_agent_loop() -> AgentLoop:
    storage_impl, _, llm_impl = _require_dependencies()
    import claw.core.gateway as _gw
    mem = getattr(_gw, 'memory', None)
    return AgentLoop(storage=storage_impl, llm=llm_impl, memory=mem)
```

---

## STEP 4 — MemoryManager 單元測試

**目標檔案**：`tests/test_memory.py`（在現有 3 tests 後面追加）

### 新增 2 個測試

#### 測試 1：RRF fusion 合併結果

```python
from datetime import datetime, timezone

def test_rrf_fusion_combines_scores():
    """出現在 vector + BM25 兩個結果的 id，RRF score 應大於只出現一次的。"""
    from claw.memory.manager import MemoryManager
    manager = MemoryManager.__new__(MemoryManager)

    now_str = datetime.now(timezone.utc).isoformat()
    vec = [
        {"id": "a", "content": "hello world", "created_at": now_str, "score": 0.9},
        {"id": "b", "content": "foo bar", "created_at": now_str, "score": 0.5},
    ]
    bm25 = [
        {"id": "a", "content": "hello world", "created_at": now_str, "score": 0.8},
        {"id": "c", "content": "baz qux", "created_at": now_str, "score": 0.4},
    ]
    fused = manager._fuse_results(vec, bm25, 0.7)

    id_to_score = {item["id"]: item["score"] for item in fused}
    # "a" 同時出現在 vec + bm25，score 應最高
    assert id_to_score["a"] > id_to_score.get("b", 0)
    assert id_to_score["a"] > id_to_score.get("c", 0)
```

#### 測試 2：時間衰減降低舊記憶分數

```python
def test_temporal_decay_reduces_old_scores():
    """30 天前的記憶 score 應顯著低於新記憶。"""
    from claw.memory.manager import MemoryManager
    from datetime import datetime, timezone, timedelta
    manager = MemoryManager.__new__(MemoryManager)

    old_date = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    new_date = datetime.now(timezone.utc).isoformat()
    results = [
        {"id": "old", "content": "old memory", "created_at": old_date, "score": 1.0},
        {"id": "new", "content": "new memory", "created_at": new_date, "score": 1.0},
    ]
    decayed = manager._apply_temporal_decay(results)
    id_to_score = {r["id"]: r["score"] for r in decayed}
    assert id_to_score["new"] > id_to_score["old"]
    # 30 天衰減率 5%/天：exp(-0.05*30) ≈ 0.22
    assert id_to_score["old"] < 0.3
```

---

## STEP 5 — 整合測試

### 5a. build_context + compaction 整合測試

**目標檔案**：`tests/test_context.py`（追加在現有 4 tests 後）

```python
import pytest
import json
from claw.core.storage import Storage, SessionRow, MessageRow
from claw.agent.context import build_context, ContextBuilder
from claw.core.storage import now_iso


@pytest.mark.asyncio
async def test_build_context_applies_compaction(tmp_path):
    """訊息過多時，build_context 應觸發 ContextBuilder 壓縮。"""
    storage = Storage(str(tmp_path / "claw.db"))
    await storage.init()
    await storage.create_session(SessionRow(
        session_id="s1", scope="main", channel=None, agent_id="default",
        system_prompt=None, queue_mode="collect", sandbox=False,
        created_at=now_iso(), last_active=now_iso(),
    ))
    # 插入 45 則每則 300 字的訊息（遠超 50 token 限制）
    for i in range(45):
        await storage.add_message(MessageRow(
            session_id="s1",
            role="user" if i % 2 == 0 else "assistant",
            content="a" * 300,
            created_at=now_iso(),
        ))

    # max_tokens=50 強制觸發壓縮
    builder = ContextBuilder(max_tokens=50)
    if builder.encoder is None:
        pytest.skip("tiktoken not available")

    msgs = await build_context(storage, "s1", "new question", context_builder=builder)
    # 壓縮後不超過 system(0) + 20 tail + 1 new user = 21
    assert len(msgs) <= 22
    # 最後一則必定是新的 user message
    assert msgs[-1].role == "user"
    assert msgs[-1].content == "new question"
```

### 5b. memory_tools 工具測試

**目標檔案**：`tests/test_memory_tools.py`（新建）

```python
"""
tests/test_memory_tools.py — memory_save / memory_search 工具測試
"""
import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.mark.asyncio
async def test_memory_tools_not_initialized():
    """MemoryManager 未初始化時應回傳 Error 字串。"""
    from claw.tools import memory_tools
    memory_tools.set_memory_manager(None)

    result = await memory_tools.memory_save("some content", "[]", session_id="agent:main")
    assert "Error" in result

    result2 = await memory_tools.memory_search("query", 5, session_id="agent:main")
    assert "Error" in result2


@pytest.mark.asyncio
async def test_memory_save_calls_manager(tmp_path):
    """memory_save 應呼叫 MemoryManager.save() 並回傳 memory id。"""
    from claw.tools import memory_tools

    mock_mm = MagicMock()
    mock_mm.save = AsyncMock(return_value="abc12345-0000-0000-0000-000000000000")
    memory_tools.set_memory_manager(mock_mm)

    result = await memory_tools.memory_save(
        "test content", '["tag1"]', session_id="agent:main"
    )
    assert "abc12345" in result
    mock_mm.save.assert_called_once()
    call_kwargs = mock_mm.save.call_args
    assert call_kwargs[0][1] == "test content"  # content 是第 2 個位置參數


@pytest.mark.asyncio
async def test_memory_search_returns_results():
    """memory_search 有結果時應回傳格式化字串。"""
    from claw.tools import memory_tools
    from datetime import datetime, timezone

    mock_mm = MagicMock()
    mock_mm.search = AsyncMock(return_value=[
        {
            "id": "id1",
            "content": "important meeting notes",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "score": 0.85,
        }
    ])
    memory_tools.set_memory_manager(mock_mm)

    result = await memory_tools.memory_search("meeting", 5, session_id="agent:main")
    assert "important meeting notes" in result
    assert "0.85" in result


@pytest.mark.asyncio
async def test_memory_search_empty_results():
    """memory_search 無結果時應回傳 No relevant memory。"""
    from claw.tools import memory_tools

    mock_mm = MagicMock()
    mock_mm.search = AsyncMock(return_value=[])
    memory_tools.set_memory_manager(mock_mm)

    result = await memory_tools.memory_search("nothing", 5, session_id="agent:main")
    assert "No relevant" in result
```

---

## 驗收要求

完成後執行：

```bash
python -m pytest tests/test_memory.py tests/test_context.py tests/test_memory_tools.py -v
```

預期：**12 passed**（test_memory 5 + test_context 5 + test_memory_tools 4）

再執行全套測試：

```bash
python -m pytest tests/ -v
```

預期：**90 passed, 2 skipped**（slack/telegram 仍 skip）

---

## 回報格式

```
## STEP 3 完成報告
- 修改檔案：claw/main.py, claw/core/gateway.py
- 主要變更：[說明]

## STEP 4 完成報告
- 修改檔案：tests/test_memory.py
- 新增測試：test_rrf_fusion_combines_scores, test_temporal_decay_reduces_old_scores
- 測試結果：5 passed

## STEP 5 完成報告
- 修改檔案：tests/test_context.py（+1）, tests/test_memory_tools.py（新建 +4）
- 測試結果：test_context 5 passed, test_memory_tools 4 passed

## 整體結果
- 全套 pytest tests/：X passed, 2 skipped
- 遇到的問題：[若有]
```
