# PHASE 7 — Codex Worker 任務書

**任務派發人**：PM（Claude Code）
**執行人**：Codex Worker
**日期**：2026-03-21
**前置條件**：Phase 7.5 完成（125 tests passing，git clean）

---

## 你的任務範圍

你負責 **P7-1 Structured Logging** 和 **P7-4 Session Reaper**。
Gemini 同時處理 P7-2 Metrics 和 P7-3 Admin API，兩者**無檔案重疊**，可完全並行執行。

---

## STEP 1 — 安裝新依賴

在 `pyproject.toml` 的 `dependencies` 加入：

```toml
"structlog>=24.0",
```

---

## STEP 2 — 建立 `claw/core/logger.py`

新建此檔案，完整實作如下：

```python
from __future__ import annotations

import logging
import os
from contextvars import ContextVar
from typing import Any

import structlog

# Context variables for per-request log context
_session_id: ContextVar[str] = ContextVar("session_id", default="")
_agent_id: ContextVar[str] = ContextVar("agent_id", default="")

# Fields that must be redacted from logs
_REDACT_KEYS = frozenset({
    "token", "api_key", "apikey", "password", "secret",
    "authorization", "auth", "credential", "private_key",
})


def _redact_processor(logger, method, event_dict: dict) -> dict:
    """Redact sensitive fields from log events."""
    for key in list(event_dict.keys()):
        if key.lower() in _REDACT_KEYS:
            event_dict[key] = "***REDACTED***"
    return event_dict


def _add_session_context(logger, method, event_dict: dict) -> dict:
    """Inject session_id and agent_id from context vars."""
    sid = _session_id.get()
    aid = _agent_id.get()
    if sid:
        event_dict["session_id"] = sid
    if aid:
        event_dict["agent_id"] = aid
    return event_dict


def configure_logging(level: str = "INFO", fmt: str = "json") -> None:
    """
    Initialize structlog. Call once at startup in main.py.

    Args:
        level: Log level string (DEBUG/INFO/WARNING/ERROR)
        fmt: "json" for production, "text" for development
    """
    log_level = getattr(logging, level.upper(), logging.INFO)

    shared_processors: list[Any] = [
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        _add_session_context,
        _redact_processor,
        structlog.processors.StackInfoRenderer(),
    ]

    if fmt == "json":
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=shared_processors + [renderer],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    logging.basicConfig(
        format="%(message)s",
        level=log_level,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Get a structlog logger by name."""
    return structlog.get_logger(name)


def set_session_context(session_id: str, agent_id: str = "") -> None:
    """Set session context for current async task (call at start of each request)."""
    _session_id.set(session_id)
    _agent_id.set(agent_id)


def clear_session_context() -> None:
    """Clear session context."""
    _session_id.set("")
    _agent_id.set("")
```

---

## STEP 3 — 整合到 `claw/main.py`

在 `main.py` 的 startup 初始化 structlog。找到 `app = FastAPI(...)` 或 startup 相關位置，加入：

```python
from claw.core.logger import configure_logging

# 在 bootstrap / startup 時呼叫（讀取 config 的 log_level）
configure_logging(
    level=cfg.get("observability", {}).get("log_level", "INFO"),
    fmt=cfg.get("observability", {}).get("log_format", "json"),
)
```

---

## STEP 4 — 整合到 `claw/agent/loop.py`

在 `AgentLoop.run()` 中加入結構化日誌。**只新增日誌，不修改任何現有邏輯。**

在 `loop.py` 頂部 import：
```python
from claw.core.logger import get_logger, set_session_context
_slog = get_logger(__name__)
```

在 `AgentLoop.run()` 方法的開頭（`async def run(...)` 的第一行業務邏輯前）加入：
```python
set_session_context(session_id, agent_id=getattr(self, 'agent_id', 'default'))
_slog.info("agent.run_start", session_id=session_id, model=model)
```

在 tool call 執行前（egress check 之後，`result = await tool_registry.execute(...)` 之前）加入：
```python
_slog.info("tool.call", tool=pc.name, session_id=session_id)
```

在 egress DENY 分支加入：
```python
_slog.warning("egress.denied", dest=_dest, tool=pc.name)
```

---

## STEP 5 — 建立 `claw/core/session_reaper.py`

新建此檔案：

```python
from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta

from claw.core.logger import get_logger

logger = get_logger(__name__)


class SessionReaper:
    """
    Background task: periodically delete expired sessions.
    TTL and interval are configurable.
    """

    def __init__(
        self,
        storage,            # claw.core.storage.Storage
        ttl_hours: int = 24,
        interval_seconds: int = 60,
        docker_runner=None, # optional: claw.sandbox.docker_runner.DockerRunner
    ):
        self.storage = storage
        self.ttl_hours = ttl_hours
        self.interval_seconds = interval_seconds
        self.docker_runner = docker_runner
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        """Start background reaper task."""
        self._task = asyncio.create_task(self._run())
        logger.info("session_reaper.started", ttl_hours=self.ttl_hours)

    def stop(self) -> None:
        """Cancel background task on shutdown."""
        if self._task:
            self._task.cancel()

    async def _run(self) -> None:
        while True:
            try:
                await self._reap()
            except Exception as e:
                logger.warning("session_reaper.error", error=str(e))
            await asyncio.sleep(self.interval_seconds)

    async def _reap(self) -> None:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=self.ttl_hours)
        sessions = await self.storage.list_sessions()
        removed = 0
        for session in sessions:
            # Parse last_active (ISO format)
            try:
                last_active_str = getattr(session, "last_active", None)
                if last_active_str is None:
                    continue
                last_active = datetime.fromisoformat(
                    last_active_str.replace("Z", "+00:00")
                )
                if last_active < cutoff:
                    # Clean up sandbox container first
                    if self.docker_runner:
                        await self.docker_runner.destroy(session.session_id)
                    await self.storage.delete_session(session.session_id)
                    removed += 1
            except Exception as e:
                logger.warning(
                    "session_reaper.skip",
                    session_id=getattr(session, "session_id", "?"),
                    error=str(e),
                )
        if removed:
            logger.info("session_reaper.reaped", count=removed)
```

---

## STEP 6 — 整合 SessionReaper 到 `claw/main.py`

在 main.py 找到 uvicorn 啟動前的初始化區塊，加入 SessionReaper 的啟動與關閉：

```python
from claw.core.session_reaper import SessionReaper

# 在 startup 事件中：
reaper = SessionReaper(
    storage=storage_instance,
    ttl_hours=cfg.get("session", {}).get("ttl_hours", 24),
    interval_seconds=cfg.get("session", {}).get("reaper_interval_seconds", 60),
)
reaper.start()

# 在 shutdown 事件中：
reaper.stop()
```

---

## STEP 7 — 補充測試

### 新建 `tests/test_logger.py`

```python
"""Tests for structured logger (claw.core.logger)."""
import json
import logging
import pytest
from unittest.mock import patch


def test_configure_logging_json():
    """configure_logging() should set up structlog without errors."""
    from claw.core.logger import configure_logging
    configure_logging(level="INFO", fmt="json")  # Should not raise


def test_sensitive_redact():
    """Sensitive keys must not appear in log output."""
    from claw.core.logger import _redact_processor
    event = {
        "event": "test",
        "token": "secret-token-123",
        "api_key": "sk-abc",
        "normal_field": "visible",
    }
    result = _redact_processor(None, None, event)
    assert result["token"] == "***REDACTED***"
    assert result["api_key"] == "***REDACTED***"
    assert result["normal_field"] == "visible"


def test_session_context_propagation():
    """set_session_context() should inject session_id into log events."""
    from claw.core.logger import set_session_context, _add_session_context, clear_session_context
    set_session_context("test-session-id", "test-agent")
    event = {"event": "test"}
    result = _add_session_context(None, None, event)
    assert result["session_id"] == "test-session-id"
    assert result["agent_id"] == "test-agent"
    clear_session_context()


def test_log_level_from_config():
    """configure_logging() should respect the level argument."""
    from claw.core.logger import configure_logging
    configure_logging(level="DEBUG", fmt="text")
    root_logger = logging.getLogger()
    assert root_logger.level <= logging.DEBUG
```

### 新建 `tests/test_session_reaper.py`

```python
"""Tests for SessionReaper (claw.core.session_reaper)."""
import pytest
import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock


@pytest.mark.asyncio
async def test_reaper_removes_expired_sessions():
    """Sessions older than TTL should be deleted."""
    from claw.core.session_reaper import SessionReaper

    old_time = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
    expired_session = MagicMock()
    expired_session.session_id = "expired-session"
    expired_session.last_active = old_time

    storage = MagicMock()
    storage.list_sessions = AsyncMock(return_value=[expired_session])
    storage.delete_session = AsyncMock()

    reaper = SessionReaper(storage=storage, ttl_hours=24)
    await reaper._reap()

    storage.delete_session.assert_called_once_with("expired-session")


@pytest.mark.asyncio
async def test_reaper_skips_active_sessions():
    """Recently active sessions should NOT be deleted."""
    from claw.core.session_reaper import SessionReaper

    recent_time = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    active_session = MagicMock()
    active_session.session_id = "active-session"
    active_session.last_active = recent_time

    storage = MagicMock()
    storage.list_sessions = AsyncMock(return_value=[active_session])
    storage.delete_session = AsyncMock()

    reaper = SessionReaper(storage=storage, ttl_hours=24)
    await reaper._reap()

    storage.delete_session.assert_not_called()
```

---

## 執行驗收

完成所有 STEP 後，執行：

```bash
python -m pytest tests/test_logger.py tests/test_session_reaper.py -v
```

預期：**6 tests PASSED**

然後執行完整測試確認無迴歸：

```bash
python -m pytest --tb=short -q
```

預期：**131+ tests PASSED，0 FAILED**

---

## 注意事項

1. **不要修改** `claw/core/gateway.py`（Gemini 負責）
2. **不要修改** `claw/core/metrics.py`（Gemini 負責，新建）
3. `claw/agent/loop.py` 只新增 log 語句，不修改任何現有邏輯
4. `claw/core/storage.py` 如果沒有 `list_sessions()` 方法，需要新增：
   ```python
   async def list_sessions(self) -> list[SessionRow]:
       async with aiosqlite.connect(self.db_path) as db:
           db.row_factory = aiosqlite.Row
           async with db.execute("SELECT * FROM sessions") as cur:
               rows = await cur.fetchall()
       return [SessionRow(**dict(r)) for r in rows]
   ```
5. `structlog` 必須在 `pyproject.toml` 依賴中宣告

---

**任務派發**：PM Claude Code
**日期**：2026-03-21
**Workers 可並行執行，無衝突**
