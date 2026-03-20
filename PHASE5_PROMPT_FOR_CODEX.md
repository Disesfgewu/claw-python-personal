# Phase 5 Codex Worker Prompt — Memory/RAG Integration

你是 claw-python 專案的 Codex Worker Agent。
請嚴格按照以下任務說明完成程式碼修改，**不要修改 STEP 範圍以外的任何檔案**。
完成後回報每個 STEP 的修改摘要與測試結果。

---

## 專案背景

- **claw-python**：Python AI Agent OS，目標硬體 Jetson Orin Nano Super
- **LLM-Router**：唯一 LLM 閘道，claw-python 不直接接觸 API key
- Phase 1-4 已完成，Phase 5 目標：將 Memory/RAG + ContextBuilder 串接入主執行流程

### 已存在且完整的模組（不需修改）

- `claw/memory/sqlite_store.py` — FTS5 + sqlite-vec CRUD
- `claw/memory/manager.py` — MemoryManager（hybrid search, RRF, temporal decay）
- `claw/tools/memory_tools.py` — memory_save / memory_search tools
- `tests/test_memory.py` — store 層 3 tests
- `tests/test_context.py` — ContextBuilder 4 tests

### 目前 gap

`build_context()` 未使用 ContextBuilder 壓縮；`AgentLoop` 無 memory 參數，無自動召回/存記。

---

## STEP 1 — 串接 ContextBuilder 到 build_context()

**目標檔案**：`claw/agent/context.py`

### 規格

1. `build_context()` 增加可選參數 `context_builder: ContextBuilder | None = None`
2. 在 append 新 user message **之前**，對歷史訊息做 compaction：
   - 將 history messages 轉換成 `list[dict]`（含 role、content）
   - 呼叫 `context_builder.compact_if_needed(dicts)`
   - 將壓縮後的 dicts 轉回 `ChatMessage` list（注意保留 `tool_call_id`）
3. 若 `context_builder` 為 None，建立預設 `ContextBuilder()` 使用（不 skip）
4. 新 user message 在壓縮後**再** append，不進入壓縮邏輯

### 注意事項

- `ContextBuilder.compact_if_needed()` 接受 `list[dict]`，其中每個 dict 有 `role` 和 `content` key
- 歷史訊息中的 `tool_call_id` 在轉成 dict 時可以忽略（不影響壓縮），但轉回 ChatMessage 時需還原
- 維持 `system_prompt` 在最前面的邏輯不變

### 實作提示

```python
async def build_context(
    storage: Storage,
    session_id: str,
    new_user_message: str,
    system_prompt: str | None = None,
    context_builder: "ContextBuilder | None" = None,
) -> list[ChatMessage]:
    history = await storage.get_messages(session_id, limit=MAX_CONTEXT_MESSAGES)

    if context_builder is None:
        context_builder = ContextBuilder()

    # 先建立歷史訊息
    history_msgs: list[ChatMessage] = []
    for row in history:
        content = row.content
        if isinstance(content, str):
            try:
                import json
                content = json.loads(content)
            except Exception:
                pass
        msg = ChatMessage(role=row.role, content=content)
        if row.tool_call_id:
            msg.tool_call_id = row.tool_call_id
        history_msgs.append(msg)

    # 轉 dict 做 compaction（只用 role + content）
    raw_dicts = [{"role": m.role, "content": m.content} for m in history_msgs]
    compacted_dicts = context_builder.compact_if_needed(raw_dicts)

    # 還原 ChatMessage（tool_call_id 依索引對應）
    # compaction 只保留尾端，對應到 history_msgs 尾端
    offset = len(history_msgs) - len(compacted_dicts)
    messages: list[ChatMessage] = []
    for i, d in enumerate(compacted_dicts):
        original_idx = offset + i
        if 0 <= original_idx < len(history_msgs):
            msg = history_msgs[original_idx]
        else:
            msg = ChatMessage(role=d["role"], content=d["content"])
        messages.append(msg)

    # 加新 user message
    messages.append(ChatMessage(role="user", content=new_user_message))
    return messages
```

**注意**：system_prompt 要在最前面插入，邏輯跟原本相同（`messages.insert(0, ...)`）。

---

## STEP 2 — 串接 MemoryManager 到 AgentLoop

**目標檔案**：`claw/agent/loop.py`

### 規格

1. `AgentLoop.__init__` 增加 `memory: "MemoryManager | None" = None` 參數，儲存為 `self.memory`

2. **執行前自動召回**（在 `build_context()` 呼叫之前）：
   ```python
   original_user_msg = user_message
   if self.memory:
       try:
           recalled = await self.memory.search(user_message, session_id=session_id, limit=3)
           if recalled:
               memory_lines = "\n".join(
                   f"[Memory {i+1}] {r['content'][:300]}"
                   for i, r in enumerate(recalled)
               )
               user_message = f"Relevant memories:\n{memory_lines}\n\n---\n{user_message}"
       except Exception as e:
           logger.warning(f"Memory recall failed: {e}")
   ```

3. **執行後自動存記**：
   - 需累積所有 `TextChunk` 事件的 content 為 `full_response` 字串
   - 在 `RunComplete` yield 之後：
   ```python
   if self.memory:
       try:
           combined = f"User: {original_user_msg}\nAssistant: {full_response[:600]}"
           await self.memory.save(
               session_id=session_id,
               content=combined,
               metadata={"source": "auto", "session": session_id},
           )
       except Exception as e:
           logger.warning(f"Memory auto-save failed: {e}")
   ```

4. `original_user_msg` 用於存記（保存原始未加 memory prefix 的訊息）

### 注意事項

- memory 操作全部包在 try/except 中，任何 memory 失敗都不應中斷 agent 執行
- `full_response` 變數要在 run() 方法的頂層初始化為 `""`，在 TextChunk 事件中累積
- TYPE annotation 用字串 `"MemoryManager | None"` 避免循環 import；實際 import 用 TYPE_CHECKING
  ```python
  from __future__ import annotations
  from typing import TYPE_CHECKING
  if TYPE_CHECKING:
      from claw.memory.manager import MemoryManager
  ```

---

## 驗收要求

完成後執行：

```bash
python -m pytest tests/test_context.py tests/test_memory.py -v
```

預期：**7 passed**（test_context 4 + test_memory 3）

再執行：

```bash
python -m pytest tests/ -v --ignore=tests/test_slack.py --ignore=tests/test_telegram.py
```

預期：**83 passed**（現有 83，不含 slack/telegram skip）

---

## 回報格式

```
## STEP 1 完成報告
- 修改檔案：claw/agent/context.py
- 主要變更：[說明]
- test_context.py：X passed

## STEP 2 完成報告
- 修改檔案：claw/agent/loop.py
- 主要變更：[說明]
- 測試結果：X passed

## 整體結果
- pytest tests/ (不含 slack/telegram)：X passed
- 遇到的問題：[若有]
```
