from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
import json
import asyncio
from typing import List, Dict, Any

from claw.core.storage import Storage
from claw.core.queue import MessageQueue, QueueMode
from claw.llm.router_client import LLMRouterClient
from claw.agent.loop import AgentLoop
from claw.agent.events import TextChunk, ToolCallStart, ToolCallResult, RunComplete, RunError
from claw.core.protocol import ConnectFrame, ResponseFrame, EventFrame
from claw.core.auth import ws_auth_middleware

app = FastAPI(title="claw-python gateway")

# --- 依賴注入（由 main.py 設定）---
storage: Storage | None = None
queue: MessageQueue | None = None
llm: LLMRouterClient | None = None
memory = None
egress_policy = None


def _require_dependencies() -> tuple[Storage, MessageQueue, LLMRouterClient]:
    if storage is None or queue is None or llm is None:
        raise RuntimeError("gateway dependencies are not configured")
    assert storage is not None
    assert queue is not None
    assert llm is not None
    return storage, queue, llm


def get_agent_loop() -> AgentLoop:
    storage_impl, _, llm_impl = _require_dependencies()
    import claw.core.gateway as _gw
    mem = getattr(_gw, 'memory', None)
    egress = getattr(_gw, 'egress_policy', None)
    return AgentLoop(storage=storage_impl, llm=llm_impl, memory=mem, egress=egress)


# --- WebSocket 控制平面 ---

@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    storage_impl, queue_impl, llm_impl = _require_dependencies()
    loop = get_agent_loop()

    try:
        # 第一幀必須是 connect frame
        raw = await ws.receive_json()
        if raw.get("type") != "connect":
            await ws.close(code=4001)
            return
        token = raw.get("token", "")
        if not await ws_auth_middleware(ws, token):
            return

        agent_id = raw.get("agent_id", "default")

        # 進入 RPC 迴圈
        async for data in ws.iter_json():
            frame_id = data.get("id", "")
            method = data.get("method", "")
            params = data.get("params", {})

            # health
            if method == "health":
                status = await llm_impl.health_check()
                await ws.send_json(ResponseFrame(id=frame_id, result=status).__dict__)

            # sessions.get
            elif method == "sessions.get":
                session = await storage_impl.get_session(params["session_id"])
                await ws.send_json(ResponseFrame(
                    id=frame_id,
                    result=session.__dict__ if session else None
                ).__dict__)

            # sessions.create
            elif method == "sessions.create":
                from claw.core.storage import SessionRow
                from claw.agent.loop import now_iso
                s = SessionRow(
                    session_id=params["session_id"],
                    scope=params.get("scope", "main"),
                    channel=params.get("channel"),
                    agent_id=agent_id,
                    system_prompt=params.get("system_prompt"),
                    queue_mode=params.get("queue_mode", "collect"),
                    sandbox=params.get("sandbox", False),
                    created_at=now_iso(),
                    last_active=now_iso(),
                    config=params.get("config", {}),
                )
                await storage_impl.create_session(s)
                await ws.send_json(ResponseFrame(id=frame_id, result="ok").__dict__)

            # agent.run（streaming 透過 event push）
            elif method == "agent.run":
                session_id = params["session_id"]
                user_message = params["message"]
                model = params.get("model", "auto")

                async def run_and_push(sid: str, msg: str):
                    async for event in loop.run(sid, msg, model=model):
                        if isinstance(event, TextChunk):
                            await ws.send_json(EventFrame(
                                event="agent.text_chunk",
                                data={"session_id": sid, "content": event.content}
                            ).__dict__)
                        elif isinstance(event, ToolCallStart):
                            await ws.send_json(EventFrame(
                                event="agent.tool_call_start",
                                data={"session_id": sid, "name": event.name}
                            ).__dict__)
                        elif isinstance(event, RunComplete):
                            await ws.send_json(EventFrame(
                                event="agent.run_complete",
                                data={"session_id": sid, "usage": event.usage}
                            ).__dict__)
                        elif isinstance(event, RunError):
                            await ws.send_json(EventFrame(
                                event="agent.run_error",
                                data={"session_id": sid, "error": event.error}
                            ).__dict__)

                await queue_impl.submit(session_id, user_message, run_and_push)
                await ws.send_json(ResponseFrame(id=frame_id, result="queued").__dict__)

            else:
                await ws.send_json(ResponseFrame(
                    id=frame_id, error=f"unknown method: {method}"
                ).__dict__)

    except WebSocketDisconnect:
        pass


# --- HTTP /v1/chat/completions（OpenAI-compatible 入口）---

@app.post("/v1/chat/completions")
async def chat_completions(body: dict):
    """
    最簡版：從 body 取 session_id 和 messages[-1].content 作為 user message。
    串流回應（SSE 格式）。
    """
    session_id = body.get("session_id", "agent:main")
    messages = body.get("messages", [])
    model = body.get("model", "auto")
    stream = body.get("stream", False)

    if not messages:
        return {"error": "messages is empty"}

    user_message = messages[-1].get("content", "")
    storage_impl, _, _ = _require_dependencies()
    loop = get_agent_loop()

    # 確保 session 存在
    session = await storage_impl.get_session(session_id)
    if session is None:
        from claw.core.storage import SessionRow
        from claw.agent.loop import now_iso
        await storage_impl.create_session(SessionRow(
            session_id=session_id,
            scope="main",
            channel=None,
            agent_id="default",
            system_prompt=None,
            queue_mode="collect",
            sandbox=False,
            created_at=now_iso(),
            last_active=now_iso(),
        ))

    if stream:
        async def event_stream():
            async for event in loop.run(session_id, user_message, model=model):
                if isinstance(event, TextChunk):
                    chunk = {
                        "choices": [{"delta": {"content": event.content}}]
                    }
                    yield f"data: {json.dumps(chunk)}\n\n"
                elif isinstance(event, RunComplete):
                    yield "data: [DONE]\n\n"

        return StreamingResponse(event_stream(), media_type="text/event-stream")
    else:
        # 非 streaming：收集所有 text chunk
        full = ""
        async for event in loop.run(session_id, user_message, model=model):
            if isinstance(event, TextChunk):
                full += event.content
        return {
            "choices": [{"message": {"role": "assistant", "content": full}}]
        }


@app.get("/health")
async def health():
    try:
        _, _, llm_impl = _require_dependencies()
        status = await llm_impl.health_check()
        return {"status": "ok", "llm_router": status}
    except Exception as e:
        return {"status": "error", "error": str(e)}


from fastapi.responses import Response as _Response
from claw.core.metrics import get_metrics_output


@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint."""
    content, content_type = get_metrics_output()
    return _Response(content=content, media_type=content_type)


# ── Egress Admin Endpoints ────────────────────────────────────

import aiosqlite as _aiosqlite
from pathlib import Path as _Path
from fastapi import BackgroundTasks, HTTPException, Header
from claw.core.auth import verify_admin_token


def _check_admin_auth(authorization: str | None) -> None:
    """Raise HTTPException 401 if admin token is invalid."""
    token = ""
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:]
    if not verify_admin_token(token):
        raise HTTPException(status_code=401, detail="Invalid or missing admin token")


@app.get("/admin/egress/pending")
async def egress_list_pending(authorization: str | None = Header(default=None)):
    _check_admin_auth(authorization)
    db_path = _Path("~/.claw/claw.db").expanduser()
    async with _aiosqlite.connect(db_path) as db:
        db.row_factory = _aiosqlite.Row
        async with db.execute(
            "SELECT id, dest, method, requested_at FROM egress_pending ORDER BY requested_at DESC"
        ) as cur:
            rows = await cur.fetchall()
    return [dict(r) for r in rows]


@app.post("/admin/egress/{req_id}/approve")
async def egress_approve(req_id: str, background_tasks: BackgroundTasks, authorization: str | None = Header(default=None)):
    _check_admin_auth(authorization)
    db_path = _Path("~/.claw/claw.db").expanduser()
    async with _aiosqlite.connect(db_path) as db:
        db.row_factory = _aiosqlite.Row
        async with db.execute(
            "SELECT dest, method FROM egress_pending WHERE id=?", (req_id,)
        ) as cur:
            row = await cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"Request {req_id!r} not found")
        dest, method = row["dest"], row["method"]
        await db.execute("DELETE FROM egress_pending WHERE id=?", (req_id,))
        await db.commit()
    from claw.tools.policy import get_egress_policy
    get_egress_policy().add_rule(dest, method)
    return {"approved": dest, "method": method}


@app.get("/admin/egress/audit")
async def egress_audit_log(limit: int = 100, authorization: str | None = Header(default=None)):
    _check_admin_auth(authorization)
    db_path = _Path("~/.claw/claw.db").expanduser()
    async with _aiosqlite.connect(db_path) as db:
        db.row_factory = _aiosqlite.Row
        async with db.execute(
            "SELECT ts, dest, verdict, tool FROM egress_audit_log ORDER BY ts DESC LIMIT ?",
            (limit,),
        ) as cur:
            rows = await cur.fetchall()
    return [dict(r) for r in rows]


# ── Session Admin ────────────────────────────────────────────────────────

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


# ── Queue Admin ──────────────────────────────────────────────────────────

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


# ── Skills Admin ─────────────────────────────────────────────────────────

@app.post("/admin/reload-skills")
async def admin_reload_skills(authorization: str | None = Header(default=None)):
    """Hot-reload skills directory without restart."""
    _check_admin_auth(authorization)
    from claw.skills.loader import load_skills
    from claw.core.config import get_config
    cfg = get_config()
    loaded_count = load_skills(cfg.skills.dir)
    # load_skills returns None; return best-effort info
    return {
        "reloaded": loaded_count if isinstance(loaded_count, int) else 0,
        "skills": [],
    }


# ── Status ────────────────────────────────────────────────────────────────

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

