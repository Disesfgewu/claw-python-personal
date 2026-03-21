# PHASE 7 — Gemini Worker 任務書

**任務派發人**：PM（Claude Code）
**執行人**：Gemini Worker
**日期**：2026-03-21
**前置條件**：Phase 7.5 完成（125 tests passing，git clean）

---

## 你的任務範圍

你負責 **P7-2 Prometheus Metrics** 和 **P7-3 Admin API 完整版**。
Codex 同時處理 P7-1 Logging 和 P7-4 Session Reaper，兩者**無檔案重疊**，可完全並行執行。

---

## STEP 1 — 安裝新依賴

在 `pyproject.toml` 的 `dependencies` 加入：

```toml
"prometheus-client>=0.20.0",
```

---

## STEP 2 — 建立 `claw/core/metrics.py`

新建此檔案，定義所有 Prometheus 指標：

```python
from __future__ import annotations

from prometheus_client import (
    Counter,
    Histogram,
    Gauge,
    CollectorRegistry,
    generate_latest,
    CONTENT_TYPE_LATEST,
)

# Use a dedicated registry (not the default global)
# to avoid conflicts in tests
REGISTRY = CollectorRegistry()

# ── Counters ────────────────────────────────────────────────────────────

agent_runs_total = Counter(
    "claw_agent_runs_total",
    "Total agent run requests",
    ["session_id", "model"],
    registry=REGISTRY,
)

tokens_used_total = Counter(
    "claw_tokens_used_total",
    "Total LLM tokens consumed",
    ["type"],  # prompt / completion
    registry=REGISTRY,
)

tool_calls_total = Counter(
    "claw_tool_calls_total",
    "Total tool calls executed",
    ["tool_name", "verdict"],  # verdict: success / error / egress_denied
    registry=REGISTRY,
)

egress_decisions_total = Counter(
    "claw_egress_decisions_total",
    "Egress policy decisions",
    ["verdict"],  # allow / deny / pending
    registry=REGISTRY,
)

llm_errors_total = Counter(
    "claw_llm_errors_total",
    "Total LLM router errors",
    ["error_type"],
    registry=REGISTRY,
)

# ── Histograms ───────────────────────────────────────────────────────────

agent_run_duration_seconds = Histogram(
    "claw_agent_run_duration_seconds",
    "Agent run duration in seconds",
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0],
    registry=REGISTRY,
)

# ── Gauges ───────────────────────────────────────────────────────────────

queue_depth = Gauge(
    "claw_queue_depth",
    "Current number of items in message queue",
    registry=REGISTRY,
)

active_sessions = Gauge(
    "claw_active_sessions",
    "Number of active sessions",
    registry=REGISTRY,
)

sandbox_containers = Gauge(
    "claw_sandbox_containers",
    "Number of active sandbox containers",
    registry=REGISTRY,
)


# ── Helper functions ──────────────────────────────────────────────────────

def record_agent_run(session_id: str, model: str) -> None:
    agent_runs_total.labels(session_id=session_id, model=model).inc()


def record_tool_call(tool_name: str, verdict: str = "success") -> None:
    tool_calls_total.labels(tool_name=tool_name, verdict=verdict).inc()


def record_egress_decision(verdict: str) -> None:
    egress_decisions_total.labels(verdict=verdict).inc()


def record_tokens(prompt_tokens: int, completion_tokens: int) -> None:
    if prompt_tokens:
        tokens_used_total.labels(type="prompt").inc(prompt_tokens)
    if completion_tokens:
        tokens_used_total.labels(type="completion").inc(completion_tokens)


def get_metrics_output() -> tuple[bytes, str]:
    """Return (content, content_type) for /metrics endpoint."""
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST
```

---

## STEP 3 — 整合指標到 `claw/agent/loop.py`

**只新增計數呼叫，不修改任何現有邏輯。**

在 `loop.py` 頂部 import：
```python
from claw.core import metrics as _metrics
```

在 `AgentLoop.run()` 開頭加入：
```python
_metrics.record_agent_run(session_id=session_id, model=model or "auto")
```

在 tool call 執行後（`call_results.append(result)` 之前）加入：
```python
_verdict = "egress_denied" if result.startswith("[egress denied]") else "success"
_metrics.record_tool_call(tool_name=pc.name, verdict=_verdict)
```

在 egress 決策後加入：
```python
# 在 egress check 的各個 verdict 分支加入：
_metrics.record_egress_decision(verdict=_verdict.value)  # _verdict 是 EgressVerdict enum
```

---

## STEP 4 — 新增 `/metrics` Endpoint 到 `claw/core/gateway.py`

在 `gateway.py` 的 `/health` endpoint 之後加入：

```python
from fastapi.responses import Response as _Response
from claw.core.metrics import get_metrics_output


@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint."""
    content, content_type = get_metrics_output()
    return _Response(content=content, media_type=content_type)
```

---

## STEP 5 — Admin Token 認證（修改 `claw/core/auth.py`）

在 `auth.py` 新增 admin token 驗證函數：

```python
import hmac
import os


def verify_admin_token(token: str) -> bool:
    """
    Verify admin API token.
    Token is read from CLAW_ADMIN_TOKEN environment variable.
    Returns False (deny all) if env var is not set.
    """
    expected = os.environ.get("CLAW_ADMIN_TOKEN", "")
    if not expected:
        return False
    return hmac.compare_digest(token, expected)
```

---

## STEP 6 — Admin API 完整版（修改 `claw/core/gateway.py`）

在現有 `/admin/egress/*` endpoints 之後，新增以下 endpoints。
**所有 /admin/* 都需要 Authorization header 驗證。**

```python
from fastapi import Header
from claw.core.auth import verify_admin_token


def _check_admin_auth(authorization: str | None) -> None:
    """Raise HTTPException 401 if admin token is invalid."""
    token = ""
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:]
    if not verify_admin_token(token):
        raise HTTPException(status_code=401, detail="Invalid or missing admin token")


# ── Session Admin ──────────────────────────────────────────────────────

@app.get("/admin/sessions")
async def admin_list_sessions(authorization: str | None = Header(default=None)):
    """List all sessions with metadata."""
    _check_admin_auth(authorization)
    assert storage is not None
    sessions = await storage.list_sessions()
    return [
        {
            "session_id": s.session_id,
            "scope": s.scope,
            "channel": s.channel,
            "agent_id": s.agent_id,
            "last_active": s.last_active,
            "created_at": s.created_at,
        }
        for s in sessions
    ]


@app.delete("/admin/sessions/{session_id}")
async def admin_delete_session(
    session_id: str,
    authorization: str | None = Header(default=None),
):
    """Force-terminate and delete a session."""
    _check_admin_auth(authorization)
    assert storage is not None
    session = await storage.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id!r} not found")
    await storage.delete_session(session_id)
    return {"deleted": session_id}


# ── Queue Admin ────────────────────────────────────────────────────────

@app.get("/admin/queue")
async def admin_queue_status(authorization: str | None = Header(default=None)):
    """Get message queue status."""
    _check_admin_auth(authorization)
    assert queue is not None
    depth = queue.depth() if hasattr(queue, "depth") else 0
    return {
        "depth": depth,
        "status": "ok",
    }


# ── Skills Admin ───────────────────────────────────────────────────────

@app.post("/admin/reload-skills")
async def admin_reload_skills(authorization: str | None = Header(default=None)):
    """Hot-reload skills directory without restart."""
    _check_admin_auth(authorization)
    from claw.skills.loader import SkillsLoader
    loader = SkillsLoader()
    skills = loader.load_all()
    return {
        "reloaded": len(skills),
        "skills": [s.name for s in skills],
    }


# ── Status ─────────────────────────────────────────────────────────────

@app.get("/admin/status")
async def admin_status(authorization: str | None = Header(default=None)):
    """Overall system status."""
    _check_admin_auth(authorization)
    assert storage is not None
    assert queue is not None
    sessions = await storage.list_sessions()
    depth = queue.depth() if hasattr(queue, "depth") else 0
    return {
        "status": "ok",
        "sessions_count": len(sessions),
        "queue_depth": depth,
    }
```

---

## STEP 7 — 更新 `claw/core/queue.py`

如果 `MessageQueue` 沒有 `depth()` 方法，新增：

```python
def depth(self) -> int:
    """Return current queue depth."""
    return len(self._queue) if hasattr(self, '_queue') else 0
```

---

## STEP 8 — 補充測試

### 新建 `tests/test_metrics.py`

```python
"""Tests for Prometheus metrics (claw.core.metrics)."""
import pytest


def test_metrics_module_imports():
    """All metric objects should be importable."""
    from claw.core.metrics import (
        agent_runs_total,
        tokens_used_total,
        tool_calls_total,
        egress_decisions_total,
        agent_run_duration_seconds,
        queue_depth,
        active_sessions,
        sandbox_containers,
        llm_errors_total,
    )
    assert agent_runs_total is not None
    assert tokens_used_total is not None


def test_metrics_endpoint_returns_prometheus_format(client):
    """GET /metrics should return 200 with Prometheus text format."""
    response = client.get("/metrics")
    assert response.status_code == 200
    # Prometheus text format starts with # HELP or metric lines
    content = response.text
    assert "claw_" in content or response.headers["content-type"].startswith("text/plain")


def test_record_agent_run_increments_counter():
    """record_agent_run() should increment the counter."""
    from claw.core.metrics import agent_runs_total, record_agent_run, REGISTRY
    before = agent_runs_total.labels(session_id="test-sess", model="test")._value.get()
    record_agent_run(session_id="test-sess", model="test")
    after = agent_runs_total.labels(session_id="test-sess", model="test")._value.get()
    assert after == before + 1
```

### 新建 `tests/test_admin_api.py`

```python
"""Tests for Admin API endpoints (claw.core.gateway)."""
import pytest
import os


def test_admin_requires_token(client):
    """Admin endpoints must return 401 without valid token."""
    response = client.get("/admin/sessions")
    assert response.status_code == 401


def test_admin_list_sessions_with_token(client, monkeypatch):
    """GET /admin/sessions should return session list with valid token."""
    monkeypatch.setenv("CLAW_ADMIN_TOKEN", "test-admin-token")
    response = client.get(
        "/admin/sessions",
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_admin_reload_skills_with_token(client, monkeypatch):
    """POST /admin/reload-skills should return reloaded count."""
    monkeypatch.setenv("CLAW_ADMIN_TOKEN", "test-admin-token")
    response = client.post(
        "/admin/reload-skills",
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "reloaded" in data
```

> **注意**：測試使用的 `client` fixture 應來自 `tests/conftest.py`，確認該 fixture 已存在。如不存在，加入：
> ```python
> @pytest.fixture
> def client():
>     from fastapi.testclient import TestClient
>     from claw.core.gateway import app
>     return TestClient(app)
> ```

---

## 執行驗收

完成所有 STEP 後，執行：

```bash
python -m pytest tests/test_metrics.py tests/test_admin_api.py -v
```

預期：**6 tests PASSED**（3 + 3）

然後執行完整測試確認無迴歸：

```bash
python -m pytest --tb=short -q
```

預期：**131+ tests PASSED，0 FAILED**

---

## 注意事項

1. **不要修改** `claw/core/logger.py`（Codex 新建）
2. **不要修改** `claw/core/session_reaper.py`（Codex 新建）
3. `claw/core/storage.py` 如果沒有 `list_sessions()` 方法，請**告知 PM**，不要自行重複實作（Codex 可能同時在加）
4. `verify_admin_token` 使用 `hmac.compare_digest` 防止 timing attack，**不要用 `==` 比較**
5. 所有 `/admin/*` endpoints 必須驗證 token，包括 egress 相關的舊 endpoints（`/admin/egress/*`）也應補上驗證
6. 既有的 `/admin/egress/pending`, `/admin/egress/{id}/approve`, `/admin/egress/audit` 也要加上 `_check_admin_auth(authorization)` — 這三個 endpoint 已存在，只需加一行驗證

---

## 既有 Egress Admin Endpoints 補強

找到 `gateway.py` 中這三個 endpoints，各自加上認證：

```python
@app.get("/admin/egress/pending")
async def egress_list_pending(authorization: str | None = Header(default=None)):
    _check_admin_auth(authorization)
    # ... 現有程式碼不變

@app.post("/admin/egress/{req_id}/approve")
async def egress_approve(req_id: str, background_tasks: BackgroundTasks, authorization: str | None = Header(default=None)):
    _check_admin_auth(authorization)
    # ... 現有程式碼不變

@app.get("/admin/egress/audit")
async def egress_audit_log(limit: int = 100, authorization: str | None = Header(default=None)):
    _check_admin_auth(authorization)
    # ... 現有程式碼不變
```

---

**任務派發**：PM Claude Code
**日期**：2026-03-21
**Workers 可並行執行，無衝突**
