# Phase 3 Implementation Prompt for Claude Sonnet 4.6

**You are an experienced Python backend engineer implementing Phase 3 of claw-python.**

---

## Context

claw-python is a Python rewrite of OpenClaw, an AI agent system using LLM-Router as the sole LLM gateway.

**Current state (Phase 2 complete):**
- 54 tests passing (`pytest tests/ -v`)
- Modules: `claw/agent/`, `claw/core/`, `claw/tools/`, `claw/skills/`, `claw/sandbox/`
- Working: Agent loop, tool calling, hooks, Docker sandbox, skills loader

**Phase 3 goals:**
1. Slash command system (`/reset`, `/history`, `/skills`)
2. Cron scheduler (APScheduler + SQLite store)
3. Multi-agent ACP (`sessions_send`, `sessions_spawn`, `sessions_list`)
4. Media handling basics (MIME, store, LLM-Router integration)
5. Channel abstraction layer (base class, policy)

**DO NOT implement Telegram/Discord adapters yet** — only the base abstractions.

---

## Implementation Order (Follow Strictly)

### STEP 0: Dependencies

Update `pyproject.toml`:

```toml
[project]
dependencies = [
    # ... existing items, ADD these:
    "apscheduler>=3.10.4",
    "croniter>=2.0.0",
    "aiofiles>=23.0",
]

[project.optional-dependencies]
channels = [
    "python-telegram-bot>=21.0",
    "discord.py>=2.3.0",
    "slack-bolt>=1.18.0",
]
```

Then run:
```bash
pip install apscheduler croniter aiofiles
```

---

### STEP 1: Slash Command System

**File: `claw/agent/commands.py`**

Create a command registry with decorator-based registration:

```python
from __future__ import annotations
import logging
from dataclasses import dataclass
from typing import Callable, Awaitable
from claw.core.storage import Storage

logger = logging.getLogger(__name__)

@dataclass
class Command:
    name: str          # without leading /, e.g. "reset"
    description: str
    handler: Callable[..., Awaitable[str]]

class CommandRegistry:
    def __init__(self) -> None:
        self._commands: dict[str, Command] = {}

    def register(self, cmd: Command) -> None:
        self._commands[cmd.name] = cmd

    def parse(self, text: str) -> tuple[Command, str] | None:
        """If text starts with /name, return (command, args), else None."""
        text = text.strip()
        if not text.startswith("/"):
            return None
        parts = text[1:].split(None, 1)
        name = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""
        cmd = self._commands.get(name)
        if cmd is None:
            return None
        return cmd, args

    async def execute(self, session_id: str, text: str, storage: Storage) -> str | None:
        """Execute command and return response string; return None if not a command."""
        result = self.parse(text)
        if result is None:
            return None
        cmd, args = result
        try:
            return await cmd.handler(session_id=session_id, args=args, storage=storage)
        except Exception as e:
            logger.warning(f"command /{cmd.name} error: {e}")
            return f"Error: {e}"

_registry = CommandRegistry()

def command(name: str, description: str):
    """Decorator: register command."""
    def decorator(fn):
        _registry.register(Command(name=name, description=description, handler=fn))
        return fn
    return decorator

def get_command_registry() -> CommandRegistry:
    return _registry

# Built-in commands

@command("reset", "Clear current session message history")
async def _cmd_reset(session_id: str, args: str, storage: Storage) -> str:
    await storage.clear_messages(session_id)
    return "✅ Message history cleared."

@command("history", "Show last N messages (default 10)")
async def _cmd_history(session_id: str, args: str, storage: Storage) -> str:
    n = 10
    try:
        n = int(args.strip())
    except (ValueError, AttributeError):
        pass
    msgs = await storage.get_messages(session_id, limit=n)
    if not msgs:
        return "(No history)"
    lines = [f"[{m.role}] {m.content[:200]}" for m in msgs[-n:]]
    return "\n".join(lines)

@command("skills", "List loaded skills")
async def _cmd_skills(session_id: str, args: str, storage: Storage) -> str:
    from claw.skills.loader import load_skills
    from claw.core.config import get_config
    cfg = get_config()
    reg = load_skills(cfg.skills.dir)
    names = [s.manifest.name for s in reg.all()]
    if not names:
        return "(No loaded skills)"
    return "Loaded skills:\n" + "\n".join(f"- {n}" for n in sorted(names))
```

**Integrate into `claw/agent/loop.py`:**

Find the line in `run()` method:
```python
await self._save_message(session_id, "user", user_message)
```

**BEFORE** that line, add:
```python
from claw.agent.commands import get_command_registry
cmd_result = await get_command_registry().execute(session_id, user_message, self.storage)
if cmd_result is not None:
    yield TextChunk(content=cmd_result)
    yield RunComplete(full_content=cmd_result, usage={})
    return
```

---

### STEP 2: Cron Scheduler

**File: `claw/cron/__init__.py`** (empty)

**File: `claw/cron/store.py`**

```python
from __future__ import annotations
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
import aiosqlite
from claw.core.storage import now_iso

@dataclass
class CronJob:
    id: str
    session_id: str
    schedule: str       # cron expression "min hour day month dow"
    prompt: str
    enabled: bool = True
    created_at: str = field(default_factory=now_iso)
    last_run: str | None = None
    next_run: str | None = None

class CronStore:
    def __init__(self, db_path: str):
        self.db_path = db_path

    async def init(self) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS cron_jobs (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    schedule TEXT NOT NULL,
                    prompt TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    last_run TEXT,
                    next_run TEXT
                )
            """)
            await db.commit()

    async def add(self, session_id: str, schedule: str, prompt: str) -> CronJob:
        job = CronJob(
            id=str(uuid.uuid4()),
            session_id=session_id,
            schedule=schedule,
            prompt=prompt,
        )
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO cron_jobs VALUES (?,?,?,?,?,?,?,?)",
                (job.id, job.session_id, job.schedule, job.prompt,
                 1, job.created_at, job.last_run, job.next_run)
            )
            await db.commit()
        return job

    async def list(self) -> list[CronJob]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM cron_jobs WHERE enabled=1") as cur:
                rows = await cur.fetchall()
        return [CronJob(**dict(r)) for r in rows]

    async def delete(self, job_id: str) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM cron_jobs WHERE id=?", (job_id,))
            await db.commit()

    async def update_last_run(self, job_id: str, ts: str, next_run: str) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE cron_jobs SET last_run=?, next_run=? WHERE id=?",
                (ts, next_run, job_id)
            )
            await db.commit()
```

**File: `claw/cron/schedule.py`**

```python
from datetime import datetime, timezone
from croniter import croniter

def next_run_dt(cron_expr: str, after: datetime | None = None) -> datetime:
    """Return next execution time (UTC)."""
    base = after or datetime.now(timezone.utc)
    it = croniter(cron_expr, base)
    return it.get_next(datetime).replace(tzinfo=timezone.utc)
```

**File: `claw/cron/runner.py`**

```python
from __future__ import annotations
import logging
from claw.cron.store import CronJob, CronStore
from claw.core.storage import Storage, SessionRow, now_iso
from claw.llm.router_client import LLMRouterClient
from claw.agent.loop import AgentLoop
from claw.agent.events import TextChunk

logger = logging.getLogger(__name__)

async def run_cron_job(
    job: CronJob,
    store: CronStore,
    storage: Storage,
    llm: LLMRouterClient,
) -> None:
    """Execute a cron job in an isolated cron session."""
    from claw.cron.schedule import next_run_dt

    session = await storage.get_session(job.session_id)
    if session is None:
        session = SessionRow(
            session_id=job.session_id,
            scope="cron",
            channel=None,
            agent_id="default",
            system_prompt=None,
            queue_mode="collect",
            sandbox=False,
            created_at=now_iso(),
            last_active=now_iso(),
            config={},
        )
        await storage.create_session(session)

    loop = AgentLoop(storage=storage, llm=llm)
    full = ""
    try:
        async for event in loop.run(job.session_id, job.prompt):
            if isinstance(event, TextChunk):
                full += event.content
    except Exception as e:
        logger.error(f"cron job {job.id} failed: {e}")

    ts = now_iso()
    next_r = next_run_dt(job.schedule).isoformat()
    await store.update_last_run(job.id, ts, next_r)
    logger.info(f"cron job {job.id} done, next={next_r}")
```

**File: `claw/cron/service.py`**

```python
from __future__ import annotations
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from claw.cron.store import CronStore, CronJob
from claw.cron.runner import run_cron_job
from claw.core.storage import Storage
from claw.llm.router_client import LLMRouterClient

logger = logging.getLogger(__name__)

class CronService:
    def __init__(self, store: CronStore, storage: Storage, llm: LLMRouterClient):
        self.store = store
        self.storage = storage
        self.llm = llm
        self._scheduler = AsyncIOScheduler(timezone="UTC")

    async def start(self) -> None:
        jobs = await self.store.list()
        for job in jobs:
            self._add_to_scheduler(job)
        self._scheduler.start()
        logger.info(f"CronService started with {len(jobs)} jobs")

    async def stop(self) -> None:
        self._scheduler.shutdown(wait=False)

    def _add_to_scheduler(self, job: CronJob) -> None:
        self._scheduler.add_job(
            run_cron_job,
            trigger="cron",
            args=[job, self.store, self.storage, self.llm],
            id=job.id,
            **self._parse_cron(job.schedule),
            replace_existing=True,
        )

    @staticmethod
    def _parse_cron(expr: str) -> dict:
        parts = expr.split()
        keys = ["minute", "hour", "day", "month", "day_of_week"]
        return dict(zip(keys, parts))

    async def add_job(self, session_id: str, schedule: str, prompt: str) -> CronJob:
        job = await self.store.add(session_id, schedule, prompt)
        self._add_to_scheduler(job)
        return job

    async def remove_job(self, job_id: str) -> None:
        await self.store.delete(job_id)
        try:
            self._scheduler.remove_job(job_id)
        except Exception:
            pass

    async def list_jobs(self) -> list[CronJob]:
        return await self.store.list()
```

**File: `claw/tools/cron.py`**

```python
from __future__ import annotations
from claw.tools.registry import tool

_cron_service = None  # Set by main.py via set_cron_service()

def set_cron_service(svc) -> None:
    global _cron_service
    _cron_service = svc

@tool(
    name="cron_add",
    description="Add a scheduled task. schedule is 5-field cron expression (e.g. '0 9 * * 1-5' = Mon-Fri 9am). prompt is the message sent to agent when triggered.",
    parameters={
        "type": "object",
        "properties": {
            "schedule": {"type": "string", "description": "Cron expression (5 fields)"},
            "prompt":   {"type": "string", "description": "Command to execute when triggered"},
        },
        "required": ["schedule", "prompt"],
    },
    requires_main=True,
)
async def cron_add(schedule: str, prompt: str) -> str:
    if _cron_service is None:
        return "Error: CronService not initialized"
    from claw.cron.schedule import next_run_dt
    try:
        next_r = next_run_dt(schedule)
    except Exception as e:
        return f"Error: invalid cron expression: {e}"
    job = await _cron_service.add_job("agent:main", schedule, prompt)
    return f"✅ Schedule created id={job.id}, next run: {next_r.isoformat()}"

@tool(
    name="cron_list",
    description="List all scheduled tasks.",
    parameters={"type": "object", "properties": {}},
    requires_main=True,
)
async def cron_list() -> str:
    if _cron_service is None:
        return "Error: CronService not initialized"
    jobs = await _cron_service.list_jobs()
    if not jobs:
        return "(No scheduled tasks)"
    lines = [f"id={j.id[:8]} schedule={j.schedule} prompt={j.prompt!r} last={j.last_run}" for j in jobs]
    return "\n".join(lines)

@tool(
    name="cron_delete",
    description="Delete scheduled task (by id prefix or full id).",
    parameters={
        "type": "object",
        "properties": {
            "job_id": {"type": "string", "description": "Job ID or first 8 chars"}
        },
        "required": ["job_id"],
    },
    requires_main=True,
)
async def cron_delete(job_id: str) -> str:
    if _cron_service is None:
        return "Error: CronService not initialized"
    jobs = await _cron_service.list_jobs()
    matched = [j for j in jobs if j.id.startswith(job_id)]
    if not matched:
        return f"Error: job {job_id!r} not found"
    for j in matched:
        await _cron_service.remove_job(j.id)
    return f"✅ Deleted {len(matched)} scheduled task(s)."
```

---

### STEP 3: Multi-agent ACP

**File: `claw/agent/multi_agent.py`**

```python
from __future__ import annotations
import asyncio
import logging
import uuid
from claw.core.storage import Storage, SessionRow, now_iso
from claw.llm.router_client import LLMRouterClient
from claw.agent.loop import AgentLoop
from claw.agent.events import TextChunk

logger = logging.getLogger(__name__)

class MultiAgentCoordinator:
    def __init__(self, storage: Storage, llm: LLMRouterClient):
        self.storage = storage
        self.llm = llm

    async def send(self, target_session_id: str, message: str) -> str:
        """Synchronously wait for AgentLoop.run(), concatenate TextChunks."""
        loop = AgentLoop(storage=self.storage, llm=self.llm)
        buf = ""
        async for event in loop.run(target_session_id, message):
            if isinstance(event, TextChunk):
                buf += event.content
        return buf

    async def spawn(self, goal: str, agent_id: str = "default", parent_session_id: str = "agent:main") -> str:
        """Create child session and run asynchronously via asyncio.Task, return child_session_id immediately."""
        child_id = f"agent:child:{uuid.uuid4().hex[:8]}"
        session = SessionRow(
            session_id=child_id,
            scope="child",
            channel=None,
            agent_id=agent_id,
            system_prompt=None,
            queue_mode="collect",
            sandbox=False,
            created_at=now_iso(),
            last_active=now_iso(),
            config={"parent": parent_session_id},
        )
        await self.storage.create_session(session)

        async def _run():
            try:
                loop = AgentLoop(storage=self.storage, llm=self.llm)
                async for _ in loop.run(child_id, goal):
                    pass
            except Exception as e:
                logger.error(f"child agent {child_id} error: {e}")

        asyncio.create_task(_run())
        return child_id

    async def list_sessions(self) -> list[SessionRow]:
        return await self.storage.list_sessions()
```

**File: `claw/tools/sessions_tools.py`**

```python
from __future__ import annotations
from claw.tools.registry import tool

_coordinator = None  # Set by main.py via set_coordinator()

def set_coordinator(c) -> None:
    global _coordinator
    _coordinator = c

@tool(
    name="sessions_send",
    description="Send message to another agent session and wait for full response. target_session_id is the target session.",
    parameters={
        "type": "object",
        "properties": {
            "target_session_id": {"type": "string"},
            "message":           {"type": "string"},
        },
        "required": ["target_session_id", "message"],
    },
    requires_main=False,
)
async def sessions_send(target_session_id: str, message: str) -> str:
    if _coordinator is None:
        return "Error: MultiAgentCoordinator not initialized"
    return await _coordinator.send(target_session_id, message)

@tool(
    name="sessions_spawn",
    description="Create new child agent session to execute goal asynchronously, return child session_id immediately.",
    parameters={
        "type": "object",
        "properties": {
            "goal":     {"type": "string"},
            "agent_id": {"type": "string", "default": "default"},
        },
        "required": ["goal"],
    },
    requires_main=False,
)
async def sessions_spawn(goal: str, agent_id: str = "default") -> str:
    if _coordinator is None:
        return "Error: MultiAgentCoordinator not initialized"
    child_id = await _coordinator.spawn(goal, agent_id)
    return f"spawned session_id={child_id}"

@tool(
    name="sessions_list",
    description="List all active sessions, return JSON.",
    parameters={"type": "object", "properties": {}},
    requires_main=True,
)
async def sessions_list() -> str:
    import json
    if _coordinator is None:
        return "Error: MultiAgentCoordinator not initialized"
    sessions = await _coordinator.list_sessions()
    return json.dumps([{"session_id": s.session_id, "scope": s.scope, "agent_id": s.agent_id} for s in sessions], ensure_ascii=False)
```

---

### STEP 4: Media Layer

**File: `claw/media/__init__.py`** (empty)

**File: `claw/media/mime.py`**

```python
import mimetypes

def guess_mime(data: bytes, filename: str = "") -> str:
    """Guess MIME type. Try filename first, fallback to magic bytes."""
    if filename:
        mime, _ = mimetypes.guess_type(filename)
        if mime:
            return mime
    # Magic bytes fallback
    if data[:4] == b"\x89PNG":
        return "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:4] == b"%PDF":
        return "application/pdf"
    if data[:3] in (b"ID3", b"\xff\xfb", b"\xff\xf3"):
        return "audio/mpeg"
    return "application/octet-stream"
```

**File: `claw/media/store.py`**

```python
from __future__ import annotations
import os
import uuid
import aiofiles

class MediaStore:
    def __init__(self, base_dir: str = "~/.claw/media"):
        self.base_dir = os.path.expanduser(base_dir)

    def _ensure_dir(self) -> None:
        os.makedirs(self.base_dir, exist_ok=True)

    async def save(self, data: bytes, mime_type: str, filename: str = "") -> str:
        self._ensure_dir()
        ext = filename.rsplit(".", 1)[-1] if "." in filename else mime_type.split("/")[-1]
        path = os.path.join(self.base_dir, f"{uuid.uuid4().hex}.{ext}")
        async with aiofiles.open(path, "wb") as f:
            await f.write(data)
        return path

    async def load(self, path: str) -> bytes:
        async with aiofiles.open(path, "rb") as f:
            return await f.read()

    async def delete(self, path: str) -> None:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
```

**File: `claw/media/input.py`**

```python
from __future__ import annotations
import base64
import httpx
from claw.media.mime import guess_mime
from claw.media.store import MediaStore

async def prepare_media_message(
    file_data: bytes,
    mime_type: str,
    store: MediaStore,
    llm_router_url: str,
    api_key: str = "",
) -> str:
    """
    Convert media into agent-understandable content description.
    - Image/PDF: POST to LLM-Router /v1/file/generate_content, return description text
    - Audio: POST to LLM-Router /v1/audio/transcriptions, return transcription
    - Other: Save to MediaStore, return path
    """
    b64 = base64.b64encode(file_data).decode()
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

    if mime_type.startswith("image/") or mime_type == "application/pdf":
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{llm_router_url}/v1/file/generate_content",
                json={"data": b64, "mime_type": mime_type},
                headers=headers,
            )
            resp.raise_for_status()
            return resp.json().get("text", "(Cannot parse media content)")

    if mime_type.startswith("audio/"):
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{llm_router_url}/v1/audio/transcriptions",
                json={"data": b64, "mime_type": mime_type},
                headers=headers,
            )
            resp.raise_for_status()
            return resp.json().get("text", "(Transcription failed)")

    path = await store.save(file_data, mime_type)
    return f"[Media file saved: {path}]"
```

---

### STEP 5: Channel Abstraction

**File: `claw/channels/__init__.py`** (empty)

**File: `claw/channels/base.py`**

```python
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import AsyncIterator

class BaseChannel(ABC):
    @abstractmethod
    async def start(self) -> None: ...

    @abstractmethod
    async def stop(self) -> None: ...

    @abstractmethod
    async def send(self, session_id: str, text: str) -> None: ...

    async def send_stream(self, session_id: str, chunks: AsyncIterator[str]) -> None:
        buf = ""
        async for chunk in chunks:
            buf += chunk
        await self.send(session_id, buf)

    async def send_typing(self, session_id: str) -> None:
        pass

    async def send_ack(self, session_id: str, emoji: str = "✅") -> None:
        pass
```

**File: `claw/channels/policy.py`**

```python
from __future__ import annotations
from dataclasses import dataclass, field

@dataclass
class ChannelPolicy:
    allow_from: list[str] = field(default_factory=list)
    dm_policy: str = "open"   # "open" | "paired" | "disabled"
    command_roles: dict[str, list[str]] = field(default_factory=dict)

    def is_allowed(self, user_id: str) -> bool:
        if not self.allow_from:
            return True
        return user_id in self.allow_from
```

---

### STEP 6: Tests

**File: `tests/test_commands.py`**

```python
import pytest
from claw.agent.commands import CommandRegistry, Command
from claw.core.storage import Storage, SessionRow, MessageRow, now_iso

@pytest.fixture
def reg():
    r = CommandRegistry()
    async def _reset(session_id, args, storage):
        await storage.clear_messages(session_id)
        return "cleared"
    async def _history(session_id, args, storage):
        n = int(args) if args.strip().isdigit() else 10
        msgs = await storage.get_messages(session_id, limit=n)
        return str(len(msgs))
    r.register(Command("reset", "clear", _reset))
    r.register(Command("history", "history", _history))
    return r

def test_command_parse_reset(reg):
    result = reg.parse("/reset")
    assert result is not None
    cmd, args = result
    assert cmd.name == "reset"
    assert args == ""

def test_command_parse_unknown(reg):
    assert reg.parse("hello world") is None
    assert reg.parse("/nonexistent") is None

@pytest.mark.asyncio
async def test_command_reset_clears_history(tmp_path, reg):
    storage = Storage(db_path=str(tmp_path / "claw.db"))
    storage.transcript_dir = str(tmp_path / "t")
    await storage.init()
    await storage.create_session(SessionRow(
        session_id="agent:main", scope="main", channel=None, agent_id="default",
        system_prompt=None, queue_mode="collect", sandbox=False,
        created_at=now_iso(), last_active=now_iso(), config={},
    ))
    await storage.add_message(MessageRow(
        session_id="agent:main", role="user", content="hi",
        tool_call_id=None, tool_name=None, created_at=now_iso()
    ))
    result = await reg.execute("agent:main", "/reset", storage)
    assert result == "cleared"
    msgs = await storage.get_messages("agent:main")
    assert msgs == []

@pytest.mark.asyncio
async def test_command_history(tmp_path, reg):
    storage = Storage(db_path=str(tmp_path / "claw.db"))
    storage.transcript_dir = str(tmp_path / "t")
    await storage.init()
    await storage.create_session(SessionRow(
        session_id="agent:main", scope="main", channel=None, agent_id="default",
        system_prompt=None, queue_mode="collect", sandbox=False,
        created_at=now_iso(), last_active=now_iso(), config={},
    ))
    result = await reg.execute("agent:main", "/history 3", storage)
    assert result is not None
```

**File: `tests/test_cron.py`**

```python
import pytest
from datetime import datetime, timezone
from claw.cron.store import CronStore
from claw.cron.schedule import next_run_dt

@pytest.mark.asyncio
async def test_cron_store_add_list_delete(tmp_path):
    store = CronStore(str(tmp_path / "claw.db"))
    await store.init()
    job = await store.add("agent:main", "0 9 * * 1-5", "daily report")
    assert job.id
    jobs = await store.list()
    assert any(j.id == job.id for j in jobs)
    await store.delete(job.id)
    jobs = await store.list()
    assert not any(j.id == job.id for j in jobs)

def test_cron_next_run():
    dt = next_run_dt("0 9 * * 1-5")
    assert isinstance(dt, datetime)
    assert dt.tzinfo is not None
    assert dt > datetime.now(timezone.utc)

def test_cron_tools_require_main():
    from claw.tools import registry as tool_registry
    defs = tool_registry.get_definitions(session_is_main=False)
    names = [d["function"]["name"] for d in defs]
    assert "cron_add" not in names
```

**File: `tests/test_multi_agent.py`**

```python
import pytest
import asyncio
import json
from claw.agent.multi_agent import MultiAgentCoordinator
from claw.core.storage import Storage, SessionRow, now_iso
from claw.llm.router_client import StreamChunk

class FakeLLM:
    async def stream(self, req):
        yield StreamChunk(content="hello from child")
        yield StreamChunk(usage={"input": 1})

@pytest.mark.asyncio
async def test_sessions_send_returns_response(tmp_path):
    storage = Storage(db_path=str(tmp_path / "claw.db"))
    storage.transcript_dir = str(tmp_path / "t")
    await storage.init()
    await storage.create_session(SessionRow(
        session_id="agent:main", scope="main", channel=None, agent_id="default",
        system_prompt=None, queue_mode="collect", sandbox=False,
        created_at=now_iso(), last_active=now_iso(), config={},
    ))
    coord = MultiAgentCoordinator(storage=storage, llm=FakeLLM())
    result = await coord.send("agent:main", "hello")
    assert "hello from child" in result

@pytest.mark.asyncio
async def test_sessions_spawn_creates_session(tmp_path):
    storage = Storage(db_path=str(tmp_path / "claw.db"))
    storage.transcript_dir = str(tmp_path / "t")
    await storage.init()
    coord = MultiAgentCoordinator(storage=storage, llm=FakeLLM())
    child_id = await coord.spawn("do something")
    await asyncio.sleep(0.05)
    sessions = await coord.list_sessions()
    ids = [s.session_id for s in sessions]
    assert child_id in ids

@pytest.mark.asyncio
async def test_sessions_list(tmp_path):
    storage = Storage(db_path=str(tmp_path / "claw.db"))
    storage.transcript_dir = str(tmp_path / "t")
    await storage.init()
    await storage.create_session(SessionRow(
        session_id="agent:main", scope="main", channel=None, agent_id="default",
        system_prompt=None, queue_mode="collect", sandbox=False,
        created_at=now_iso(), last_active=now_iso(), config={},
    ))
    coord = MultiAgentCoordinator(storage=storage, llm=FakeLLM())
    result = await coord.list_sessions()
    assert any(s.session_id == "agent:main" for s in result)
```

---

## Validation

After all steps:

```bash
python -m pytest tests/ -v
```

**Expected:** All 54 existing tests + ~10 new tests = **~64 tests PASSED**.

---

## Deliverables

Report back:

1. **File tree:**
   ```bash
   ls claw/channels/ claw/cron/ claw/media/ claw/agent/ claw/tools/ | grep -E "(commands|multi_agent|cron|sessions_tools)"
   ```

2. **Test results:**
   ```bash
   python -m pytest tests/ -v | tail -20
   ```

3. **Any failures:** List test names and error messages.

---

## Important Notes

- **DO NOT modify existing passing tests**
- **DO NOT install Telegram/Discord packages yet** (channels optional)
- Use **exact file paths and function signatures** as specified
- Follow Python 3.11+ syntax (`|` union types, `match/case` if needed)
- All async functions must use `async def`
- Keep imports at top of each file

Good luck! 🚀
