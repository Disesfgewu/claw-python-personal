from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
import aiosqlite
import json
import os

_data_dir = os.path.expanduser(os.getenv("CLAW_DATA_DIR", "~/.claw"))
DB_PATH = os.path.join(_data_dir, "claw.db")
TRANSCRIPT_DIR = os.path.join(_data_dir, "transcripts")

SCHEMA_SQL = """
-- sessions 表：每個 session 的 metadata
CREATE TABLE IF NOT EXISTS sessions (
    session_id   TEXT PRIMARY KEY,   -- "agent:main", "agent:telegram:group:123"
    scope        TEXT NOT NULL,       -- "main" | "group" | "cron"
    channel      TEXT,                -- "telegram" | "discord" | null
    agent_id     TEXT NOT NULL DEFAULT 'default',
    system_prompt TEXT,
    queue_mode   TEXT NOT NULL DEFAULT 'collect',  -- "collect"|"followup"|"drop"
    sandbox      INTEGER NOT NULL DEFAULT 0,       -- 0=host, 1=docker
    created_at   TEXT NOT NULL,       -- ISO8601
    last_active  TEXT NOT NULL,
    config       TEXT NOT NULL DEFAULT '{}'  -- JSON，channel-specific 設定
);

-- messages 表：context window 用的近期訊息
CREATE TABLE IF NOT EXISTS messages (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id   TEXT NOT NULL REFERENCES sessions(session_id),
    role         TEXT NOT NULL,       -- "user" | "assistant" | "tool"
    content      TEXT NOT NULL,       -- JSON string（支援 multipart content）
    tool_call_id TEXT,                -- tool result 才有
    tool_name    TEXT,                -- tool result 才有
    created_at   TEXT NOT NULL,
    token_count  INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_messages_session
    ON messages(session_id, created_at DESC);
"""


@dataclass
class SessionRow:
    session_id: str
    scope: str                    # "main" | "group" | "cron"
    channel: str | None
    agent_id: str
    system_prompt: str | None
    queue_mode: str               # "collect" | "followup" | "drop"
    sandbox: bool
    created_at: str
    last_active: str
    config: dict = field(default_factory=dict)


@dataclass
class MessageRow:
    session_id: str
    role: str                     # "user" | "assistant" | "tool"
    content: str | list           # str 或 multipart list
    tool_call_id: str | None = None
    tool_name: str | None = None
    created_at: str = ""
    token_count: int = 0


class Storage:
    def __init__(
        self,
        db_path: str = DB_PATH,
        transcript_dir: str = TRANSCRIPT_DIR,
    ):
        self.db_path = os.path.expanduser(db_path)
        self.transcript_dir = os.path.expanduser(transcript_dir)

    async def init(self) -> None:
        """初始化 DB，建立 tables"""
        os.makedirs(self.transcript_dir, exist_ok=True)
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        async with aiosqlite.connect(self.db_path) as db:
            await db.executescript(SCHEMA_SQL)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS egress_pending (
                    id           TEXT PRIMARY KEY,
                    dest         TEXT NOT NULL,
                    method       TEXT NOT NULL,
                    requested_at INTEGER NOT NULL
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS egress_audit_log (
                    id      INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts      INTEGER NOT NULL,
                    dest    TEXT NOT NULL,
                    verdict TEXT NOT NULL,
                    tool    TEXT NOT NULL
                )
            """)
            await db.commit()

    # --- Session ---
    async def get_session(self, session_id: str) -> SessionRow | None:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT * FROM sessions WHERE session_id = ?",
                (session_id,),
            )
            row = await cur.fetchone()
            if not row:
                return None
            return SessionRow(
                session_id=row["session_id"],
                scope=row["scope"],
                channel=row["channel"],
                agent_id=row["agent_id"],
                system_prompt=row["system_prompt"],
                queue_mode=row["queue_mode"],
                sandbox=bool(row["sandbox"]),
                created_at=row["created_at"],
                last_active=row["last_active"],
                config=json.loads(row["config"] or "{}"),
            )

    async def create_session(self, session: SessionRow) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO sessions(
                    session_id, scope, channel, agent_id, system_prompt,
                    queue_mode, sandbox, created_at, last_active, config
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session.session_id,
                    session.scope,
                    session.channel,
                    session.agent_id,
                    session.system_prompt,
                    session.queue_mode,
                    1 if session.sandbox else 0,
                    session.created_at,
                    session.last_active,
                    json.dumps(session.config or {}),
                ),
            )
            await db.commit()

    async def update_last_active(self, session_id: str) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE sessions SET last_active = ? WHERE session_id = ?",
                (now_iso(), session_id),
            )
            await db.commit()

    async def delete_session(self, session_id: str) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "DELETE FROM messages WHERE session_id = ?",
                (session_id,),
            )
            await db.execute(
                "DELETE FROM sessions WHERE session_id = ?",
                (session_id,),
            )
            await db.commit()

    async def list_sessions(self) -> list[SessionRow]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("SELECT * FROM sessions")
            rows = await cur.fetchall()
            result: list[SessionRow] = []
            for row in rows:
                result.append(SessionRow(
                    session_id=row["session_id"],
                    scope=row["scope"],
                    channel=row["channel"],
                    agent_id=row["agent_id"],
                    system_prompt=row["system_prompt"],
                    queue_mode=row["queue_mode"],
                    sandbox=bool(row["sandbox"]),
                    created_at=row["created_at"],
                    last_active=row["last_active"],
                    config=json.loads(row["config"] or "{}"),
                ))
            return result

    # --- Messages ---
    async def add_message(self, msg: MessageRow) -> None:
        content = msg.content if isinstance(msg.content, str) else json.dumps(msg.content)
        created_at = msg.created_at or now_iso()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO messages(
                    session_id, role, content, tool_call_id, tool_name,
                    created_at, token_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    msg.session_id,
                    msg.role,
                    content,
                    msg.tool_call_id,
                    msg.tool_name,
                    created_at,
                    msg.token_count,
                ),
            )
            await db.commit()

    async def get_messages(self, session_id: str, limit: int = 50) -> list[MessageRow]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                """
                SELECT session_id, role, content, tool_call_id, tool_name,
                       created_at, token_count
                FROM messages
                WHERE session_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (session_id, limit),
            )
            rows = await cur.fetchall()
            rows = list(reversed(rows))
            result: list[MessageRow] = []
            for row in rows:
                content = row["content"]
                try:
                    content = json.loads(content)
                except Exception:
                    pass
                result.append(MessageRow(
                    session_id=row["session_id"],
                    role=row["role"],
                    content=content,
                    tool_call_id=row["tool_call_id"],
                    tool_name=row["tool_name"],
                    created_at=row["created_at"],
                    token_count=row["token_count"],
                ))
            return result

    async def clear_messages(self, session_id: str) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "DELETE FROM messages WHERE session_id = ?",
                (session_id,),
            )
            await db.commit()

    # --- Transcript (JSONL) ---
    def append_transcript(self, session_id: str, event: dict) -> None:
        """同步寫入（append-only，不 await）"""
        os.makedirs(self.transcript_dir, exist_ok=True)
        safe_name = session_id.replace(":", "_")
        path = os.path.join(self.transcript_dir, f"{safe_name}.jsonl")
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
