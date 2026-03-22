# Phase 9b Worker Prompt — ResearchLoop → AgentLoop 接線

你是實作 claw-python Phase 9b 的 worker。工作目錄：`/home/martin/Desktop/claw-python-personal/`。
當前狀態：145 tests 通過，0 failures。**嚴格按照順序，每步驗證後再繼續。**

---

## 背景問題

`claw/research/loop.py` 的 `_execute()` 方法目前直接呼叫 `self.llm.stream()`：

```python
async def _execute(self, hypothesis: str, session_id: str) -> tuple[str, str]:
    req = CompletionRequest(messages=[...], model="auto", max_tokens=1024)
    buf = ""
    async for chunk in self.llm.stream(req):
        if chunk.content:
            buf += chunk.content
    return hypothesis, buf.strip()
```

這表示 research 實驗只是 LLM 文字生成，**工具（web_fetch, bash, file_read, memory_search）完全不會被呼叫**。
需要改成走 `AgentLoop.run()`，讓 agent 真正能執行工具。

---

## 閱讀清單（開始前必讀）

- `claw/agent/loop.py`：AgentLoop class，特別是 `__init__` 參數和 `run()` signature
- `claw/agent/events.py`：TextChunk, ToolCallResult, RunComplete, RunError
- `claw/core/storage.py`：SessionRow dataclass，`create_session()` 方法
- `claw/research/loop.py`：ResearchLoop 目前的實作
- `tests/test_research_loop.py`：現有測試的寫法模式

---

## Task 1 — 修改 `claw/research/loop.py`

### 1a. 修改 `ResearchLoop.__init__` 加入 `agent_loop` 參數

```python
class ResearchLoop:
    def __init__(
        self,
        llm,
        ledger: ResearchLedger | None = None,
        agent_loop=None,   # AgentLoop | None — 若提供則用於真實工具執行
    ):
        self.llm = llm
        self.ledger = ledger or ResearchLedger()
        self.planner = ResearchPlanner(llm)
        self.agent_loop = agent_loop  # Optional[AgentLoop]
```

### 1b. 替換 `_execute()` 方法

用以下實作完整替換 `_execute()` 方法（從 `async def _execute` 到方法結尾）：

```python
async def _execute(self, hypothesis: str, session_id: str) -> tuple[str, str]:
    """
    Execute a research hypothesis.
    If agent_loop is available, use it (real tool calls).
    Otherwise fall back to direct LLM generation.
    """
    if self.agent_loop is not None:
        return await self._execute_via_agent(hypothesis, session_id)
    return await self._execute_via_llm(hypothesis)

async def _execute_via_agent(self, hypothesis: str, session_id: str) -> tuple[str, str]:
    """Run hypothesis through AgentLoop so tools are available."""
    from claw.core.storage import SessionRow
    from claw.agent.events import TextChunk, ToolCallResult, RunComplete, RunError
    from datetime import datetime, timezone

    # Create a temporary sub-session for this experiment
    sub_session_id = f"research:{session_id}:{hypothesis[:20].replace(' ', '_')}"
    now = datetime.now(timezone.utc).isoformat()

    # Ensure sub-session exists in storage
    existing = await self.agent_loop.storage.get_session(sub_session_id)
    if existing is None:
        await self.agent_loop.storage.create_session(SessionRow(
            session_id=sub_session_id,
            scope="research",
            channel="internal",
            agent_id="research",
            system_prompt=None,
            queue_mode="collect",
            sandbox=False,
            created_at=now,
            last_active=now,
            config={},
        ))

    prompt = (
        f"Research hypothesis to investigate:\n\n"
        f"{hypothesis}\n\n"
        f"Use available tools (web_fetch, bash, file_read, memory_search) as needed. "
        f"Report your findings concisely in 2-3 sentences."
    )

    text_parts: list[str] = []
    tool_summaries: list[str] = []

    async for event in self.agent_loop.run(
        session_id=sub_session_id,
        user_message=prompt,
        model="auto",
    ):
        if isinstance(event, TextChunk):
            text_parts.append(event.text)
        elif isinstance(event, ToolCallResult):
            # Summarise tool output (truncate)
            summary = f"[{event.tool_name}] {str(event.result)[:200]}"
            tool_summaries.append(summary)
        elif isinstance(event, RunError):
            logger.warning(f"research sub-session error: {event.error}")

    output_parts = tool_summaries + text_parts
    output = "\n".join(output_parts).strip() or "(no output)"
    approach = f"AgentLoop sub-session with tools"
    return approach, output

async def _execute_via_llm(self, hypothesis: str) -> tuple[str, str]:
    """Fallback: direct LLM stream without tool execution."""
    from claw.llm.router_client import CompletionRequest, ChatMessage
    prompt = (
        f"Analyze this research hypothesis and report findings:\n\n"
        f"Hypothesis: {hypothesis}\n\n"
        f"Be concise and factual."
    )
    req = CompletionRequest(
        messages=[ChatMessage(role="user", content=prompt)],
        model="auto",
        max_tokens=512,
    )
    buf = ""
    async for chunk in self.llm.stream(req):
        if chunk.content:
            buf += chunk.content
    return "direct-llm", buf.strip()
```

### 1c. 修改模組底部的 singleton 與 setter

在檔案末尾（現有的 `get_research_loop` / `set_research_loop` 之後）加入：

```python
def init_research_loop(llm, storage=None, egress=None, memory=None) -> ResearchLoop:
    """
    Convenience factory: builds AgentLoop internally so ResearchLoop can use tools.
    Call this from main.py instead of constructing manually.
    """
    from claw.agent.loop import AgentLoop
    from claw.research.ledger import ResearchLedger

    agent_loop = None
    if storage is not None:
        agent_loop = AgentLoop(storage=storage, llm=llm, egress=egress, memory=memory)

    loop = ResearchLoop(llm=llm, agent_loop=agent_loop)
    set_research_loop(loop)
    return loop
```

---

## Task 2 — 建立 `tests/test_research_execute.py`（3 tests）

```python
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, AsyncMock
from claw.research.loop import ResearchLoop
from claw.research.ledger import ResearchLedger
from claw.core.storage import Storage, SessionRow
from claw.agent.events import TextChunk, ToolCallResult, RunComplete


async def _aiter(items):
    for item in items:
        yield item


@pytest.fixture
async def storage(tmp_path):
    db = str(tmp_path / "test.db")
    s = Storage(db_path=db, transcript_dir=str(tmp_path / "transcripts"))
    await s.init()
    return s


@pytest.mark.asyncio
async def test_execute_fallback_without_agent_loop(storage):
    """Without agent_loop, _execute falls back to direct LLM."""
    mock_llm = AsyncMock()
    chunk = MagicMock()
    chunk.content = "LLM fallback output"
    mock_llm.stream = AsyncMock(return_value=_aiter([chunk]))

    loop = ResearchLoop(llm=mock_llm, ledger=ResearchLedger(db_path=storage.db_path))
    assert loop.agent_loop is None

    approach, output = await loop._execute_via_llm("test hypothesis")
    assert approach == "direct-llm"
    assert "LLM fallback output" in output


@pytest.mark.asyncio
async def test_execute_via_agent_creates_sub_session(storage):
    """With agent_loop, _execute creates a sub-session and collects events."""
    from datetime import datetime, timezone

    mock_llm = AsyncMock()
    mock_agent_loop = MagicMock()
    mock_agent_loop.storage = storage

    text_event = TextChunk(text="Found relevant data")
    tool_event = ToolCallResult(tool_name="web_fetch", call_id="1", result="page content here")
    complete_event = RunComplete(message="done", total_tokens=50)

    mock_agent_loop.run = AsyncMock(return_value=_aiter([text_event, tool_event, complete_event]))

    loop = ResearchLoop(llm=mock_llm, ledger=ResearchLedger(db_path=storage.db_path), agent_loop=mock_agent_loop)
    approach, output = await loop._execute_via_agent("research hypothesis about X", "agent:main")

    assert approach == "AgentLoop sub-session with tools"
    assert "web_fetch" in output
    assert "Found relevant data" in output


@pytest.mark.asyncio
async def test_execute_dispatches_to_correct_method(storage):
    """_execute() routes to _execute_via_agent when agent_loop present, else _execute_via_llm."""
    mock_llm = AsyncMock()

    # Without agent_loop
    loop_no_agent = ResearchLoop(llm=mock_llm, ledger=ResearchLedger(db_path=storage.db_path))
    loop_no_agent._execute_via_llm = AsyncMock(return_value=("direct-llm", "output"))
    loop_no_agent._execute_via_agent = AsyncMock(return_value=("agent", "output"))

    await loop_no_agent._execute("hyp", "agent:main")
    loop_no_agent._execute_via_llm.assert_called_once()
    loop_no_agent._execute_via_agent.assert_not_called()

    # With agent_loop
    mock_agent_loop = MagicMock()
    mock_agent_loop.storage = storage
    loop_with_agent = ResearchLoop(llm=mock_llm, ledger=ResearchLedger(db_path=storage.db_path), agent_loop=mock_agent_loop)
    loop_with_agent._execute_via_llm = AsyncMock(return_value=("direct-llm", "output"))
    loop_with_agent._execute_via_agent = AsyncMock(return_value=("agent", "output"))

    await loop_with_agent._execute("hyp", "agent:main")
    loop_with_agent._execute_via_agent.assert_called_once()
    loop_with_agent._execute_via_llm.assert_not_called()
```

---

## Task 3 — 執行測試

```bash
cd /home/martin/Desktop/claw-python-personal
python -m pytest tests/ -x --tb=short
```

預期：**148 tests 通過，0 failures**（145 + 3 新增）

---

## 交付清單

完成後回報：
1. 修改的檔案絕對路徑 + 改了什麼
2. 新建的檔案絕對路徑
3. pytest 最終輸出最後 5 行
4. 遇到的問題和解決方式

---

## 預期測試計數

| 來源 | 數量 |
|---|---|
| Phase 9 (existing) | 145 |
| test_research_execute.py | +3 |
| **目標** | **148** |
