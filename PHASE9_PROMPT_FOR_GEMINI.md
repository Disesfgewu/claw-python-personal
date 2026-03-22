# Phase 9 Worker Prompt — AutoResearch 框架

你是實作 claw-python Phase 9 的 worker。工作目錄：`/home/martin/Desktop/claw-python-personal/`。
當前狀態：135 tests 通過，0 failures。**嚴格按照順序執行，每步完成後驗證再繼續。**

---

## 閱讀清單（開始前必讀）

- `claw/core/storage.py`：了解 SCHEMA_SQL 結構和 Storage class 的 init 方法
- `claw/tools/memory_tools.py`：tool 函數接收 session_id 的模式
- `claw/tools/research_tools.py`：（本任務建立）
- `claw/agent/loop.py`：AgentLoop 結構，了解如何呼叫 LLM
- `claw/llm/router_client.py`：LLMRouterClient，了解 complete() 或 stream() 的用法
- `tests/test_memory_tools.py`：tool 測試的寫法模式

---

## Task 1 — 建立 `claw/research/` 模組

### 1a. 建立 `claw/research/__init__.py`

```python
from __future__ import annotations
```

### 1b. 建立 `claw/research/experiment.py`

```python
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ExperimentStatus(str, Enum):
    KEEP    = "keep"
    DISCARD = "discard"
    CRASH   = "crash"


@dataclass
class ExperimentResult:
    task_id: str
    hypothesis: str
    approach: str
    output: str
    metric: float | None          # C層 eval_cmd 的數值結果，None = 未提供
    status: ExperimentStatus
    reasoning: str
    ts: str


@dataclass
class ResearchTask:
    task_id: str
    question: str
    criteria: str | None          # A層：用戶明確的成功標準
    eval_cmd: str | None          # C層：bash 命令，exit code 0 = 成功，或 stdout float
    status: str                   # "running" | "completed" | "stopped"
    max_experiments: int
    created_at: str
    completed_at: str | None = None
    experiments: list[ExperimentResult] = field(default_factory=list)
```

---

## Task 2 — 修改 `claw/core/storage.py`

在 `SCHEMA_SQL` 字串的末尾（`CREATE INDEX` 之後）加入兩張新表。

**在現有的 `CREATE INDEX IF NOT EXISTS idx_messages_session` 之後加入：**

```sql

-- Research framework tables (Phase 9)
CREATE TABLE IF NOT EXISTS research_tasks (
    task_id      TEXT PRIMARY KEY,
    question     TEXT NOT NULL,
    criteria     TEXT,
    eval_cmd     TEXT,
    status       TEXT NOT NULL DEFAULT 'running',
    max_exp      INTEGER NOT NULL DEFAULT 20,
    created_at   TEXT NOT NULL,
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS research_experiments (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id     TEXT NOT NULL REFERENCES research_tasks(task_id),
    hypothesis  TEXT NOT NULL,
    approach    TEXT NOT NULL,
    output      TEXT NOT NULL DEFAULT '',
    metric      REAL,
    status      TEXT NOT NULL,
    reasoning   TEXT NOT NULL DEFAULT '',
    ts          TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_research_exp_task
    ON research_experiments(task_id, ts DESC);
```

**重要**：只修改 `SCHEMA_SQL` 字串，不改動 `Storage` class 的其他方法。

---

## Task 3 — 建立 `claw/research/ledger.py`

```python
from __future__ import annotations

import uuid
import aiosqlite
from datetime import datetime, timezone
from pathlib import Path

from claw.core.storage import DB_PATH
from claw.research.experiment import ExperimentResult, ExperimentStatus, ResearchTask


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ResearchLedger:
    """SQLite-backed experiment ledger for AutoResearch tasks."""

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = str(Path(db_path).expanduser())

    async def create_task(
        self,
        question: str,
        criteria: str | None = None,
        eval_cmd: str | None = None,
        max_experiments: int = 20,
    ) -> str:
        task_id = uuid.uuid4().hex[:12]
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT INTO research_tasks(task_id, question, criteria, eval_cmd,
                   status, max_exp, created_at)
                   VALUES (?, ?, ?, ?, 'running', ?, ?)""",
                (task_id, question, criteria, eval_cmd, max_experiments, _now()),
            )
            await db.commit()
        return task_id

    async def record_experiment(self, result: ExperimentResult) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT INTO research_experiments
                   (task_id, hypothesis, approach, output, metric, status, reasoning, ts)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    result.task_id,
                    result.hypothesis,
                    result.approach,
                    result.output[:1000],
                    result.metric,
                    result.status.value,
                    result.reasoning,
                    result.ts,
                ),
            )
            await db.commit()

    async def complete_task(self, task_id: str, status: str = "completed") -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE research_tasks SET status=?, completed_at=? WHERE task_id=?",
                (status, _now(), task_id),
            )
            await db.commit()

    async def get_task(self, task_id: str) -> ResearchTask | None:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT * FROM research_tasks WHERE task_id=?", (task_id,)
            )
            row = await cur.fetchone()
            if not row:
                return None
            task = ResearchTask(
                task_id=row["task_id"],
                question=row["question"],
                criteria=row["criteria"],
                eval_cmd=row["eval_cmd"],
                status=row["status"],
                max_experiments=row["max_exp"],
                created_at=row["created_at"],
                completed_at=row["completed_at"],
            )
            cur2 = await db.execute(
                "SELECT * FROM research_experiments WHERE task_id=? ORDER BY ts ASC",
                (task_id,),
            )
            rows = await cur2.fetchall()
            task.experiments = [
                ExperimentResult(
                    task_id=r["task_id"],
                    hypothesis=r["hypothesis"],
                    approach=r["approach"],
                    output=r["output"],
                    metric=r["metric"],
                    status=ExperimentStatus(r["status"]),
                    reasoning=r["reasoning"],
                    ts=r["ts"],
                )
                for r in rows
            ]
            return task

    async def list_running_tasks(self) -> list[ResearchTask]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT * FROM research_tasks WHERE status='running' ORDER BY created_at DESC"
            )
            rows = await cur.fetchall()
            return [
                ResearchTask(
                    task_id=r["task_id"],
                    question=r["question"],
                    criteria=r["criteria"],
                    eval_cmd=r["eval_cmd"],
                    status=r["status"],
                    max_experiments=r["max_exp"],
                    created_at=r["created_at"],
                    completed_at=r["completed_at"],
                )
                for r in rows
            ]

    async def kept_experiments(self, task_id: str) -> list[ExperimentResult]:
        """Return only KEEP status experiments for a task."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT * FROM research_experiments WHERE task_id=? AND status='keep' ORDER BY ts ASC",
                (task_id,),
            )
            rows = await cur.fetchall()
            return [
                ExperimentResult(
                    task_id=r["task_id"],
                    hypothesis=r["hypothesis"],
                    approach=r["approach"],
                    output=r["output"],
                    metric=r["metric"],
                    status=ExperimentStatus(r["status"]),
                    reasoning=r["reasoning"],
                    ts=r["ts"],
                )
                for r in rows
            ]
```

---

## Task 4 — 建立 `claw/research/planner.py`

```python
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from claw.research.experiment import ExperimentResult

logger = logging.getLogger(__name__)

_DECOMPOSE_PROMPT = """You are a research planning assistant. Given a complex research question,
decompose it into 3-5 specific, independent, verifiable hypotheses or sub-approaches.

Each hypothesis must be:
- Concrete and actionable (can be tested in one experiment)
- Independent of the others
- Directly relevant to the research question

Return ONLY a numbered list, one hypothesis per line. No explanations."""

_NEXT_HYPOTHESIS_PROMPT = """You are guiding an autonomous research loop.

Research question: {question}

Completed experiments so far:
{history}

Generate the NEXT hypothesis to test. It must:
- Build on successful (KEEP) results if any exist
- Avoid repeating approaches that were discarded
- Be specific and immediately testable

Return ONLY the hypothesis, nothing else."""


class ResearchPlanner:
    """Generates and manages research hypotheses using the LLM."""

    def __init__(self, llm):
        self.llm = llm

    async def decompose(self, question: str) -> list[str]:
        """Break a complex question into initial hypotheses."""
        from claw.llm.router_client import CompletionRequest, ChatMessage
        req = CompletionRequest(
            messages=[
                ChatMessage(role="system", content=_DECOMPOSE_PROMPT),
                ChatMessage(role="user", content=f"Research question: {question}"),
            ],
            model="auto",
            max_tokens=512,
        )
        buf = ""
        async for chunk in self.llm.stream(req):
            if chunk.content:
                buf += chunk.content
        hypotheses = [
            line.lstrip("0123456789.-) ").strip()
            for line in buf.strip().splitlines()
            if line.strip() and line[0].isdigit()
        ]
        return hypotheses if hypotheses else [question]

    async def next_hypothesis(
        self,
        question: str,
        history: list[ExperimentResult],
    ) -> str:
        """Generate the next hypothesis based on history."""
        from claw.llm.router_client import CompletionRequest, ChatMessage

        history_text = "\n".join(
            f"- [{r.status.value.upper()}] {r.hypothesis}: {r.reasoning}"
            for r in history[-10:]  # last 10 experiments
        ) or "(no experiments yet)"

        prompt = _NEXT_HYPOTHESIS_PROMPT.format(
            question=question, history=history_text
        )
        req = CompletionRequest(
            messages=[ChatMessage(role="user", content=prompt)],
            model="auto",
            max_tokens=256,
        )
        buf = ""
        async for chunk in self.llm.stream(req):
            if chunk.content:
                buf += chunk.content
        return buf.strip() or question
```

---

## Task 5 — 建立 `claw/research/loop.py`

```python
from __future__ import annotations

import asyncio
import logging
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import AsyncIterator

from claw.research.experiment import ExperimentResult, ExperimentStatus, ResearchTask
from claw.research.ledger import ResearchLedger
from claw.research.planner import ResearchPlanner

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ExperimentCompleted:
    result: ExperimentResult


@dataclass
class ResearchCompleted:
    task_id: str
    kept: list[ExperimentResult]
    reason: str


@dataclass
class ResearchExhausted:
    task_id: str
    kept: list[ExperimentResult]


ResearchEvent = ExperimentCompleted | ResearchCompleted | ResearchExhausted


class ResearchLoop:
    """
    Autonomous research loop. Orchestrates:
      Planner → execute → evaluate (A→C→B) → keep/discard → iterate
    """

    def __init__(self, llm, ledger: ResearchLedger | None = None):
        self.llm = llm
        self.ledger = ledger or ResearchLedger()
        self.planner = ResearchPlanner(llm)

    async def run(
        self,
        question: str,
        success_criteria: str | None = None,
        eval_cmd: str | None = None,
        max_experiments: int = 20,
        session_id: str = "agent:main",
    ) -> AsyncIterator[ResearchEvent]:
        task_id = await self.ledger.create_task(
            question, success_criteria, eval_cmd, max_experiments
        )
        logger.info(f"research.start task_id={task_id} question={question[:80]}")

        all_results: list[ExperimentResult] = []

        # Decompose question into initial hypotheses
        hypotheses = await self.planner.decompose(question)
        hypothesis_queue = list(hypotheses)

        for exp_num in range(max_experiments):
            # Pick next hypothesis
            if hypothesis_queue:
                hypothesis = hypothesis_queue.pop(0)
            else:
                hypothesis = await self.planner.next_hypothesis(question, all_results)

            # Execute the experiment via agent loop
            approach, output = await self._execute(hypothesis, session_id)

            # Run eval_cmd if provided (C layer)
            metric = await self._run_eval_cmd(eval_cmd) if eval_cmd else None

            # Three-layer evaluation
            status, reasoning = await self._evaluate(
                output, metric, success_criteria, eval_cmd, all_results
            )

            result = ExperimentResult(
                task_id=task_id,
                hypothesis=hypothesis,
                approach=approach,
                output=output,
                metric=metric,
                status=status,
                reasoning=reasoning,
                ts=_now(),
            )
            await self.ledger.record_experiment(result)
            all_results.append(result)
            yield ExperimentCompleted(result)

            # Check termination
            if status == ExperimentStatus.KEEP:
                terminate, reason = await self._should_terminate(
                    result, success_criteria, eval_cmd, all_results
                )
                if terminate:
                    await self.ledger.complete_task(task_id, "completed")
                    yield ResearchCompleted(task_id, [r for r in all_results if r.status == ExperimentStatus.KEEP], reason)
                    return

        await self.ledger.complete_task(task_id, "exhausted")
        yield ResearchExhausted(task_id, [r for r in all_results if r.status == ExperimentStatus.KEEP])

    async def _execute(self, hypothesis: str, session_id: str) -> tuple[str, str]:
        """Ask LLM to execute the hypothesis using available tools. Returns (approach, output)."""
        from claw.llm.router_client import CompletionRequest, ChatMessage
        prompt = (
            f"Execute this research hypothesis and report findings:\n\n"
            f"Hypothesis: {hypothesis}\n\n"
            f"Use available tools (web_fetch, bash, file_read, memory_search) as needed. "
            f"Report your findings concisely."
        )
        req = CompletionRequest(
            messages=[ChatMessage(role="user", content=prompt)],
            model="auto",
            max_tokens=1024,
        )
        buf = ""
        async for chunk in self.llm.stream(req):
            if chunk.content:
                buf += chunk.content
        return hypothesis, buf.strip()

    async def _run_eval_cmd(self, eval_cmd: str) -> float | None:
        """Run eval_cmd. Returns float from stdout or 0.0/1.0 from exit code."""
        try:
            proc = await asyncio.create_subprocess_shell(
                eval_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=60)
            text = stdout.decode().strip()
            try:
                return float(text)
            except ValueError:
                return 0.0 if proc.returncode == 0 else 1.0
        except Exception as e:
            logger.warning(f"eval_cmd failed: {e}")
            return None

    async def _evaluate(
        self,
        output: str,
        metric: float | None,
        criteria: str | None,
        eval_cmd: str | None,
        history: list[ExperimentResult],
    ) -> tuple[ExperimentStatus, str]:
        """Three-layer termination evaluation: A → C → B."""
        # A: explicit criteria
        if criteria:
            verdict = await self._ask_llm_bool(
                f"Does this result satisfy the success criteria?\n"
                f"Criteria: {criteria}\n"
                f"Result: {output[:600]}"
            )
            return (
                ExperimentStatus.KEEP if verdict else ExperimentStatus.DISCARD,
                f"A-layer: criteria {'met' if verdict else 'not met'}",
            )

        # C: quantitative metric
        if eval_cmd and metric is not None:
            kept = [r for r in history if r.status == ExperimentStatus.KEEP and r.metric is not None]
            best = min((r.metric for r in kept), default=float("inf"))
            if metric < best:
                return ExperimentStatus.KEEP, f"C-layer: metric improved {metric:.4f} < {best:.4f}"
            return ExperimentStatus.DISCARD, f"C-layer: no improvement {metric:.4f} >= {best:.4f}"

        # B: LLM self-evaluation
        verdict = await self._ask_llm_bool(
            f"Is this a useful finding for the research?\n"
            f"Result: {output[:600]}"
        )
        return (
            ExperimentStatus.KEEP if verdict else ExperimentStatus.DISCARD,
            f"B-layer: llm {'approved' if verdict else 'rejected'}",
        )

    async def _should_terminate(
        self,
        latest: ExperimentResult,
        criteria: str | None,
        eval_cmd: str | None,
        history: list[ExperimentResult],
    ) -> tuple[bool, str]:
        """Decide whether to stop the loop after a KEEP result."""
        if criteria:
            # A-layer already confirmed criteria met
            return True, "success criteria satisfied"
        if eval_cmd and latest.metric is not None and latest.metric == 0.0:
            return True, "eval_cmd returned 0 (success)"
        # B-layer: check if LLM thinks research is complete
        kept = [r for r in history if r.status == ExperimentStatus.KEEP]
        if len(kept) >= 3:
            verdict = await self._ask_llm_bool(
                f"Given {len(kept)} successful findings, is the research complete?"
            )
            if verdict:
                return True, "B-layer: sufficient findings accumulated"
        return False, ""

    async def _ask_llm_bool(self, question: str) -> bool:
        from claw.llm.router_client import CompletionRequest, ChatMessage
        req = CompletionRequest(
            messages=[
                ChatMessage(
                    role="system",
                    content="Answer ONLY with 'yes' or 'no'. Nothing else.",
                ),
                ChatMessage(role="user", content=question),
            ],
            model="auto",
            max_tokens=8,
        )
        buf = ""
        async for chunk in self.llm.stream(req):
            if chunk.content:
                buf += chunk.content
        return "yes" in buf.lower()


# Module-level singleton
_loop: ResearchLoop | None = None


def get_research_loop() -> ResearchLoop | None:
    return _loop


def set_research_loop(loop: ResearchLoop) -> None:
    global _loop
    _loop = loop
```

---

## Task 6 — 建立 `claw/tools/research_tools.py`

```python
from __future__ import annotations

import json
from claw.tools.registry import tool

# Set by main.py via set_research_loop()
_loop = None


def set_research_loop_ref(loop) -> None:
    global _loop
    _loop = loop


@tool(
    name="research_start",
    description=(
        "Start an autonomous research loop on a complex question. "
        "The agent will decompose the question, run experiments iteratively, "
        "and stop when success criteria are met or max experiments reached."
    ),
    parameters={
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "The complex research question or task to investigate",
            },
            "criteria": {
                "type": "string",
                "description": "Optional: explicit success criteria string (A-layer). "
                               "If provided, loop stops when LLM confirms this is satisfied.",
            },
            "eval_cmd": {
                "type": "string",
                "description": "Optional: bash command to run after each experiment (C-layer). "
                               "Exit code 0 = success, or stdout float (lower=better).",
            },
            "max_experiments": {
                "type": "integer",
                "default": 20,
                "description": "Maximum number of experiments before stopping (default: 20)",
            },
        },
        "required": ["question"],
    },
    requires_main=True,
)
async def research_start(
    question: str,
    criteria: str = "",
    eval_cmd: str = "",
    max_experiments: int = 20,
    session_id: str = "agent:main",
) -> str:
    from claw.research.loop import get_research_loop
    loop = get_research_loop()
    if loop is None:
        return "Error: ResearchLoop not initialized. Call set_research_loop() in main.py."

    task_id = await loop.ledger.create_task(
        question=question,
        criteria=criteria or None,
        eval_cmd=eval_cmd or None,
        max_experiments=max_experiments,
    )
    return (
        f"Research task started.\n"
        f"task_id: {task_id}\n"
        f"question: {question}\n"
        f"criteria: {criteria or '(none — LLM self-evaluation)'}\n"
        f"eval_cmd: {eval_cmd or '(none)'}\n"
        f"max_experiments: {max_experiments}\n"
        f"Use research_status(task_id='{task_id}') to monitor progress."
    )


@tool(
    name="experiment_record",
    description="Record the result of a research experiment within an active research loop.",
    parameters={
        "type": "object",
        "properties": {
            "task_id": {"type": "string", "description": "The research task ID"},
            "hypothesis": {"type": "string", "description": "The hypothesis that was tested"},
            "approach": {"type": "string", "description": "The approach/method used"},
            "output": {"type": "string", "description": "The experiment output/findings"},
            "status": {
                "type": "string",
                "enum": ["keep", "discard", "crash"],
                "description": "keep=useful finding, discard=not useful, crash=execution failed",
            },
            "reasoning": {"type": "string", "description": "Why this status was assigned"},
        },
        "required": ["task_id", "hypothesis", "approach", "output", "status", "reasoning"],
    },
    requires_main=False,
)
async def experiment_record(
    task_id: str,
    hypothesis: str,
    approach: str,
    output: str,
    status: str,
    reasoning: str,
    session_id: str = "agent:main",
) -> str:
    from claw.research.ledger import ResearchLedger
    from claw.research.experiment import ExperimentResult, ExperimentStatus
    from claw.core.storage import DB_PATH
    from datetime import datetime, timezone

    try:
        exp_status = ExperimentStatus(status)
    except ValueError:
        return f"Error: invalid status '{status}'. Must be keep/discard/crash."

    ledger = ResearchLedger(DB_PATH)
    result = ExperimentResult(
        task_id=task_id,
        hypothesis=hypothesis,
        approach=approach,
        output=output,
        metric=None,
        status=exp_status,
        reasoning=reasoning,
        ts=datetime.now(timezone.utc).isoformat(),
    )
    await ledger.record_experiment(result)
    return f"✅ Experiment recorded [{status.upper()}] for task {task_id}"


@tool(
    name="research_status",
    description="Check the status of a research task, or list all running tasks.",
    parameters={
        "type": "object",
        "properties": {
            "task_id": {
                "type": "string",
                "description": "Optional: specific task ID to inspect. Omit to list all running tasks.",
            },
        },
    },
    requires_main=True,
)
async def research_status(
    task_id: str = "",
    session_id: str = "agent:main",
) -> str:
    from claw.research.ledger import ResearchLedger
    from claw.core.storage import DB_PATH

    ledger = ResearchLedger(DB_PATH)

    if task_id:
        task = await ledger.get_task(task_id)
        if task is None:
            return f"Error: task not found: {task_id}"
        kept = [e for e in task.experiments if e.status.value == "keep"]
        lines = [
            f"Task: {task.task_id}",
            f"Status: {task.status}",
            f"Question: {task.question}",
            f"Criteria: {task.criteria or '(LLM self-evaluation)'}",
            f"Experiments: {len(task.experiments)} total, {len(kept)} kept",
            "",
            "Recent experiments:",
        ]
        for e in task.experiments[-5:]:
            lines.append(f"  [{e.status.value.upper()}] {e.hypothesis[:60]}... — {e.reasoning[:80]}")
        return "\n".join(lines)

    # List all running tasks
    tasks = await ledger.list_running_tasks()
    if not tasks:
        return "(No running research tasks)"
    lines = ["Running research tasks:"]
    for t in tasks:
        lines.append(f"  {t.task_id}: {t.question[:80]}...")
    return "\n".join(lines)
```

---

## Task 7 — 建立 `claw/skills/autoresearch/SKILL.md`

建立目錄 `claw/skills/autoresearch/` 並建立 `SKILL.md`：

```markdown
---
name: autoresearch
description: Autonomous research loop — decompose complex questions, run experiments, keep/discard findings, self-iterate until solved
metadata:
  openclaw:
    requires:
      config: []
---

# AutoResearch

你是一個自主研究 agent。當用戶給你一個複雜問題或任務時，你必須：

## 工作流程

1. **啟動研究任務**
   - 呼叫 `research_start(question=..., criteria=..., eval_cmd=...)`
   - criteria 和 eval_cmd 是可選的，沒有就留空

2. **分解問題**
   - 把問題分解成 3-5 個具體的、可獨立驗證的子假設
   - 每次只執行一個假設

3. **執行實驗**
   - 使用 web_fetch、bash、file_read、memory_search 等工具
   - 每次實驗必須有明確的動作和可觀察的結果

4. **記錄結果**
   - 每次實驗後立即呼叫 `experiment_record`
   - KEEP：有效發現，記錄並沿此方向延伸
   - DISCARD：無效，換策略，不要重複
   - CRASH：執行失敗，修正後再試

5. **迭代**
   - 根據 KEEP 的結果，生成下一個更深入的假設
   - 根據 DISCARD 的原因，避免重複方向
   - NEVER STOP until success criteria met or max_experiments reached

## 終止條件

- **有明確標準（A層）**：LLM 確認結果滿足標準
- **有 eval_cmd（C層）**：指令回傳 0 或指標持續改善
- **無標準（B層）**：累積 3 個以上 KEEP 後，判斷研究是否完整
- **達到 max_experiments**：強制終止，回報已有的 KEEP 結果

## 原則

- 每次實驗必須有新的假設，不重複已試過的方法
- 失敗是資料，不是浪費——記錄失敗原因
- 優先利用記憶（memory_search）避免重複工作
- 結果要具體可引用，不能是模糊的感想
```

---

## Task 8 — 更新 `claw/tools/__init__.py`

在現有的兩行後加入：

```python
from claw.tools import research_tools as _research_tools  # noqa: F401
```

完成後 `claw/tools/__init__.py` 應為：

```python
from claw.tools import web_fetch as _web_fetch  # noqa: F401
from claw.tools import file_tools as _file_tools  # noqa: F401
from claw.tools import research_tools as _research_tools  # noqa: F401
```

---

## Task 9 — 建立測試

### `tests/test_research_ledger.py`（4 tests）

```python
from __future__ import annotations

import pytest
import os
import tempfile
from claw.research.ledger import ResearchLedger
from claw.research.experiment import ExperimentResult, ExperimentStatus
from claw.core.storage import Storage
from datetime import datetime, timezone


@pytest.fixture
async def ledger(tmp_path):
    db = str(tmp_path / "test.db")
    storage = Storage(db_path=db, transcript_dir=str(tmp_path / "transcripts"))
    await storage.init()
    return ResearchLedger(db_path=db)


@pytest.mark.asyncio
async def test_create_task(ledger):
    task_id = await ledger.create_task("What is the best sorting algorithm?")
    assert len(task_id) == 12
    task = await ledger.get_task(task_id)
    assert task is not None
    assert task.question == "What is the best sorting algorithm?"
    assert task.status == "running"


@pytest.mark.asyncio
async def test_record_experiment(ledger):
    task_id = await ledger.create_task("Test question")
    result = ExperimentResult(
        task_id=task_id,
        hypothesis="Try approach A",
        approach="Used web_fetch",
        output="Found that A works well",
        metric=None,
        status=ExperimentStatus.KEEP,
        reasoning="Clear improvement",
        ts=datetime.now(timezone.utc).isoformat(),
    )
    await ledger.record_experiment(result)
    task = await ledger.get_task(task_id)
    assert task is not None
    assert len(task.experiments) == 1
    assert task.experiments[0].status == ExperimentStatus.KEEP


@pytest.mark.asyncio
async def test_kept_experiments(ledger):
    task_id = await ledger.create_task("Test question")
    ts = datetime.now(timezone.utc).isoformat()
    for status, hyp in [
        (ExperimentStatus.KEEP, "good hypothesis"),
        (ExperimentStatus.DISCARD, "bad hypothesis"),
        (ExperimentStatus.KEEP, "another good one"),
    ]:
        await ledger.record_experiment(ExperimentResult(
            task_id=task_id, hypothesis=hyp, approach="approach",
            output="output", metric=None, status=status, reasoning="r", ts=ts,
        ))
    kept = await ledger.kept_experiments(task_id)
    assert len(kept) == 2
    assert all(e.status == ExperimentStatus.KEEP for e in kept)


@pytest.mark.asyncio
async def test_complete_task(ledger):
    task_id = await ledger.create_task("Complete me")
    await ledger.complete_task(task_id, "completed")
    task = await ledger.get_task(task_id)
    assert task is not None
    assert task.status == "completed"
    assert task.completed_at is not None
```

### `tests/test_research_loop.py`（4 tests）

```python
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from claw.research.loop import ResearchLoop, ResearchCompleted, ResearchExhausted
from claw.research.ledger import ResearchLedger
from claw.research.experiment import ExperimentStatus
from claw.core.storage import Storage


@pytest.fixture
async def loop_and_ledger(tmp_path):
    db = str(tmp_path / "test.db")
    storage = Storage(db_path=db, transcript_dir=str(tmp_path / "transcripts"))
    await storage.init()
    ledger = ResearchLedger(db_path=db)

    mock_llm = AsyncMock()
    mock_chunk = MagicMock()
    mock_chunk.content = "yes"
    mock_llm.stream = AsyncMock(return_value=_aiter([mock_chunk]))

    loop = ResearchLoop(llm=mock_llm, ledger=ledger)
    return loop, ledger


async def _aiter(items):
    for item in items:
        yield item


@pytest.mark.asyncio
async def test_a_layer_terminates_on_criteria(loop_and_ledger):
    """A-layer: if success_criteria provided and LLM says yes, loop completes."""
    loop, ledger = loop_and_ledger

    # Mock planner to return one hypothesis
    loop.planner.decompose = AsyncMock(return_value=["Test hypothesis"])
    loop.planner.next_hypothesis = AsyncMock(return_value="Next hypothesis")
    loop._execute = AsyncMock(return_value=("approach", "some output"))
    # LLM always says yes → criteria met immediately
    loop._ask_llm_bool = AsyncMock(return_value=True)

    events = []
    async for event in loop.run("research question", success_criteria="find something"):
        events.append(event)

    assert any(isinstance(e, ResearchCompleted) for e in events)
    completed = next(e for e in events if isinstance(e, ResearchCompleted))
    assert "criteria" in completed.reason


@pytest.mark.asyncio
async def test_c_layer_terminates_on_metric_improvement(loop_and_ledger):
    """C-layer: if eval_cmd returns improving metric, keep and eventually terminate."""
    loop, ledger = loop_and_ledger
    loop.planner.decompose = AsyncMock(return_value=["Hyp 1", "Hyp 2", "Hyp 3"])
    loop.planner.next_hypothesis = AsyncMock(return_value="New hyp")
    loop._execute = AsyncMock(return_value=("approach", "output"))

    # First call returns 1.0, subsequent improve to 0.0 (success)
    call_count = 0
    async def fake_eval(cmd):
        nonlocal call_count
        call_count += 1
        return 1.0 / call_count  # 1.0, 0.5, 0.33...
    loop._run_eval_cmd = fake_eval
    loop._ask_llm_bool = AsyncMock(return_value=True)

    events = []
    async for event in loop.run("question", eval_cmd="pytest", max_experiments=5):
        events.append(event)

    assert len(events) > 0


@pytest.mark.asyncio
async def test_b_layer_self_evaluation(loop_and_ledger):
    """B-layer: without criteria or eval_cmd, LLM self-judges."""
    loop, ledger = loop_and_ledger
    loop.planner.decompose = AsyncMock(return_value=["Hyp"])
    loop.planner.next_hypothesis = AsyncMock(return_value="New hyp")
    loop._execute = AsyncMock(return_value=("approach", "output"))
    # LLM says yes after 3 keeps → terminate
    loop._ask_llm_bool = AsyncMock(return_value=True)

    events = []
    async for event in loop.run("question", max_experiments=10):
        events.append(event)

    assert len(events) > 0


@pytest.mark.asyncio
async def test_max_experiments_exhausted(loop_and_ledger):
    """Loop stops at max_experiments if no termination criteria met."""
    loop, ledger = loop_and_ledger
    loop.planner.decompose = AsyncMock(return_value=["Hyp"])
    loop.planner.next_hypothesis = AsyncMock(return_value="Next")
    loop._execute = AsyncMock(return_value=("approach", "output"))
    loop._ask_llm_bool = AsyncMock(return_value=False)  # never satisfied

    events = []
    async for event in loop.run("question", max_experiments=3):
        events.append(event)

    assert any(isinstance(e, ResearchExhausted) for e in events)


### `tests/test_research_tools.py`（2 tests）

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch
from claw.core.storage import Storage


@pytest.fixture
async def storage_init(tmp_path):
    db = str(tmp_path / "test.db")
    storage = Storage(db_path=db, transcript_dir=str(tmp_path / "transcripts"))
    await storage.init()
    return db


@pytest.mark.asyncio
async def test_experiment_record_tool(storage_init):
    from claw.tools.research_tools import experiment_record
    with patch("claw.tools.research_tools.DB_PATH", storage_init):
        # Patch the import inside the function
        import claw.research.ledger as ledger_mod
        orig = ledger_mod.ResearchLedger.__init__
        def patched_init(self, db_path=None):
            orig(self, db_path=storage_init)
        with patch.object(ledger_mod.ResearchLedger, "__init__", patched_init):
            # First create a task directly
            ledger = ledger_mod.ResearchLedger(db_path=storage_init)
            task_id = await ledger.create_task("test question")
            result = await experiment_record(
                task_id=task_id,
                hypothesis="test hyp",
                approach="test approach",
                output="test output",
                status="keep",
                reasoning="good result",
            )
    assert "✅" in result or "recorded" in result.lower()


@pytest.mark.asyncio
async def test_research_status_no_tasks(storage_init):
    from claw.tools.research_tools import research_status
    import claw.research.ledger as ledger_mod
    def patched_init(self, db_path=None):
        ledger_mod.ResearchLedger.__init__(self, db_path=storage_init)
    with patch.object(ledger_mod.ResearchLedger, "__init__", patched_init):
        with patch("claw.tools.research_tools.DB_PATH", storage_init):
            result = await research_status()
    assert "No running" in result or "task" in result.lower()
```

**注意**：`test_research_tools.py` 的 `test_research_loop.py` 的最後一個 fixture 定義是獨立檔案，需要拆開。請將 `test_research_tools.py` 放成獨立的 `tests/test_research_tools.py`。

---

## Task 10 — 執行測試

```bash
cd /home/martin/Desktop/claw-python-personal
python -m pytest tests/ -x --tb=short
```

預期：**145 tests 通過，0 failures**

---

## 交付清單

完成後回報：

1. 每個新建/修改的檔案（絕對路徑）
2. pytest 最終輸出最後 5 行
3. 任何遇到的問題和解決方式

---

## 預期測試計數

| 來源 | 數量 |
|---|---|
| 既有 tests（Phase 8a） | 135 |
| test_research_ledger.py | +4 |
| test_research_loop.py | +4 |
| test_research_tools.py | +2 |
| **目標** | **145** |
