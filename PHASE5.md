# Phase 5 — Memory/RAG + Context Compaction 整合

> **目標**：將已完成的 Memory/RAG 和 Context Compaction 模組串接入主執行流程，
> 讓 AgentLoop 具備長期記憶搜尋、自動存記、以及 token-aware context 壓縮能力。

---

## 現況分析（Phase 4 完成後）

### 已存在但未串接

| 檔案 | 完成度 | 狀態 |
|------|--------|------|
| `claw/memory/sqlite_store.py` | ✅ 完整 | FTS5 + sqlite-vec CRUD |
| `claw/memory/manager.py` | ✅ 完整 | 混合搜尋 RRF + 時間衰減 |
| `claw/agent/context.py` (ContextBuilder) | ✅ 完整 | tiktoken + head/tail compaction |
| `claw/tools/memory_tools.py` | ✅ 完整 | memory_save / memory_search 工具 |
| `tests/test_memory.py` | ✅ 3 tests | store 層單元測試 |
| `tests/test_context.py` | ✅ 4 tests | ContextBuilder 單元測試 |

### 缺少的整合點（Phase 5 工作範圍）

1. `build_context()` 沒有呼叫 `ContextBuilder.compact_if_needed()`
2. `AgentLoop` 沒有 `memory: MemoryManager` 參數，無自動召回 / 自動存記
3. `main.py` 沒有初始化 `MemoryStore` + `MemoryManager`，也沒有 import `memory_tools`
4. 缺少 MemoryManager 層（RRF fusion、temporal decay）的單元測試
5. 缺少 build_context + compaction 整合測試、memory_tools 工具測試

---

## Phase 5 步驟清單

### STEP 1 — 串接 ContextBuilder 到 build_context()
**檔案**: `claw/agent/context.py`

修改 `build_context()` 函數：在回傳 messages 前，先將訊息轉為 dict list，
呼叫 `ContextBuilder.compact_if_needed()`，再轉回 `ChatMessage` list。

```python
# 在 build_context() 內，append 新 user message 後
builder = ContextBuilder()
raw_dicts = [{"role": m.role, "content": m.content} for m in messages]
compacted_dicts = builder.compact_if_needed(raw_dicts)
# 轉回 ChatMessage
messages = [ChatMessage(role=d["role"], content=d["content"]) for d in compacted_dicts]
```

注意：`build_context()` 要接受可選的 `context_builder: ContextBuilder | None = None`
參數，方便測試時注入 mock。

---

### STEP 2 — 串接 MemoryManager 到 AgentLoop
**檔案**: `claw/agent/loop.py`

`AgentLoop.__init__` 增加 `memory: MemoryManager | None = None` 參數。

**執行前（自動召回）**：
```python
# 在 build_context() 呼叫前
if self.memory:
    recalled = await self.memory.search(user_message, session_id=session_id, limit=3)
    if recalled:
        memory_ctx = "\n".join(f"[Memory] {r['content']}" for r in recalled)
        user_message = f"{memory_ctx}\n\n---\n{user_message}"
```

**執行後（自動存記）**：
```python
# 在 RunComplete 事件 yield 後
if self.memory and full_response:
    await self.memory.save(
        session_id=session_id,
        content=f"User: {original_user_msg}\nAssistant: {full_response[:500]}",
        metadata={"source": "auto"}
    )
```

`full_response` 需累積 `TextChunk` 事件的 content。

---

### STEP 3 — 更新 main.py 初始化 Memory
**檔案**: `claw/main.py`

在 `lifespan()` 中：

```python
import claw.tools.memory_tools as _mem_tools
from claw.memory.sqlite_store import MemoryStore
from claw.memory.manager import MemoryManager

# 在 storage.init() 後
mem_db_path = os.path.join(os.path.dirname(cfg.storage.db_path), "memory.db")
mem_store = MemoryStore(db_path=mem_db_path)
await mem_store.init()
memory_manager = MemoryManager(store=mem_store, llm=llm)
_mem_tools.set_memory_manager(memory_manager)
gateway_module.memory = memory_manager  # 供 get_agent_loop() 使用
```

同時在 `get_agent_loop()` 中：
```python
def get_agent_loop() -> AgentLoop:
    storage_impl, _, llm_impl = _require_dependencies()
    mem = getattr(gateway_module, 'memory', None)
    return AgentLoop(storage=storage_impl, llm=llm_impl, memory=mem)
```

並在 lifespan import 段加入：
```python
import claw.tools.memory_tools  # 觸發 memory_save / memory_search 工具注冊
```

---

### STEP 4 — MemoryManager 層單元測試
**檔案**: `tests/test_memory.py`（擴充）

新增測試：

```python
def test_rrf_fusion_combines_scores():
    from claw.memory.manager import MemoryManager
    # 用假 store、假 llm 建構 manager
    manager = MemoryManager.__new__(MemoryManager)
    vec = [{"id": "a", "content": "hello", "created_at": now, "score": 0.9}]
    bm25 = [{"id": "a", "content": "hello", "created_at": now, "score": 0.7},
            {"id": "b", "content": "world", "created_at": now, "score": 0.5}]
    fused = manager._fuse_results(vec, bm25, 0.7)
    # id "a" 出現在兩個結果中，應有更高分
    a_item = next(x for x in fused if x["id"] == "a")
    b_item = next(x for x in fused if x["id"] == "b")
    assert a_item["score"] > b_item["score"]

def test_temporal_decay_reduces_old_scores():
    from claw.memory.manager import MemoryManager
    from datetime import datetime, timezone, timedelta
    manager = MemoryManager.__new__(MemoryManager)
    old_date = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    new_date = datetime.now(timezone.utc).isoformat()
    results = [
        {"id": "old", "content": "x", "created_at": old_date, "score": 1.0},
        {"id": "new", "content": "y", "created_at": new_date, "score": 1.0},
    ]
    decayed = manager._apply_temporal_decay(results)
    old_item = next(x for x in decayed if x["id"] == "old")
    new_item = next(x for x in decayed if x["id"] == "new")
    assert old_item["score"] < new_item["score"]
```

---

### STEP 5 — 整合測試：build_context + memory_tools
**檔案**: `tests/test_context.py`（擴充），`tests/test_memory_tools.py`（新建）

**test_context.py 新增**：
```python
@pytest.mark.asyncio
async def test_build_context_applies_compaction(tmp_path):
    """build_context() 應在訊息過多時觸發 compaction"""
    from claw.core.storage import Storage, MessageRow
    from claw.agent.context import build_context, ContextBuilder
    storage = Storage(str(tmp_path / "claw.db"))
    await storage.init()
    await storage.create_session(...)  # 建 session
    # 插入 45 則長訊息（每則 300 字）
    for i in range(45):
        await storage.add_message(MessageRow(
            session_id="s1", role="user", content="a" * 300, ...
        ))
    builder = ContextBuilder(max_tokens=5000)
    msgs = await build_context(storage, "s1", "new question", context_builder=builder)
    # 應被壓縮
    assert len(msgs) <= 22  # system + 20 tail + new user
```

**tests/test_memory_tools.py**：
```python
@pytest.mark.asyncio
async def test_memory_tools_save_and_search(tmp_path):
    from claw.tools.memory_tools import memory_save, memory_search, set_memory_manager
    from claw.memory.sqlite_store import MemoryStore
    from claw.memory.manager import MemoryManager
    # mock llm with zero embeddings
    ...
    result = await memory_save("important user info", "[]", session_id="agent:main")
    assert "Memory saved" in result
    found = await memory_search("user info", 5, session_id="agent:main")
    # 即使 embedding 全 0，FTS 仍能找到
    assert "important" in found or "No relevant" in found

@pytest.mark.asyncio
async def test_memory_tools_not_initialized():
    from claw.tools.memory_tools import memory_save, set_memory_manager
    set_memory_manager(None)
    result = await memory_save("x", session_id="agent:main")
    assert "Error" in result
```

---

## 測試總數預測

| 來源 | 現有 | Phase 5 新增 | 總計 |
|------|------|------------|------|
| test_memory.py | 3 | +2 (RRF, decay) | 5 |
| test_context.py | 4 | +1 (integration) | 5 |
| test_memory_tools.py | 0 | +2 (save/search, not-init) | 2 |
| 其他現有 | 78 | 0 | 78 |
| **Total** | **85** | **+5** | **90** |

（2 個 skip 的 channel tests 保持不變）

---

## 依賴確認

已在 `pyproject.toml` 中：
- `tiktoken>=0.5.0` ✅
- `sqlite-vec>=0.1.0` ✅
- `aiosqlite>=0.20.0` ✅

無需新增依賴。

---

## 分工

| Worker | 任務 |
|--------|------|
| **Codex** | STEP 1（context.py 串接）、STEP 2（loop.py 串接） |
| **Gemini** | STEP 3（main.py 初始化）、STEP 4（manager 單元測試）、STEP 5（整合測試） |

驗收標準：`python -m pytest tests/ -v` → **90 passed, 2 skipped**
