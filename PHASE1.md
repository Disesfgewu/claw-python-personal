# Phase 1 實作計劃書

> 目標：從零建出一個可以 end-to-end 跑起來的最小系統。
> 完成後你可以用 HTTP POST 發一則訊息，agent 呼叫 LLM-Router，執行 tool，把回覆串流回來。

---

## 依賴關係圖

```
P1-1 Storage
  └── P1-2 LLM-Router Client
        └── P1-3 Tool Registry
              └── P1-4 Agent Loop
                    └── P1-5 Queue
                          └── P1-6 Gateway
                                └── P1-7 HTTP Channel（end-to-end 測試）
```

每一層都依賴上面那層，所以按順序實作。

---

## P1-1　Storage

**對應 TS 參考：**
- `src/sessions/session-id.ts`
- `src/sessions/transcript-events.ts`
- `src/channels/session-meta.ts`

**負責的事：**
- Session 的 metadata 存取（SQLite）
- 訊息歷史的讀寫（SQLite messages 表）
- 完整 transcript 的 append（JSONL）

---

### 目錄

```
claw/
└── core/
    └── storage.py
```

---

### SQLite Schema

```sql
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
```

---

### JSONL Transcript 格式

每個 session 有一個 `.jsonl` 檔案，每行一個事件，append-only，不修改：

```
~/.claw/transcripts/<session_id>.jsonl
```

每行格式：

```json
{"ts": "2026-03-18T10:00:00Z", "type": "user_message", "content": "幫我查今天天氣"}
{"ts": "2026-03-18T10:00:01Z", "type": "assistant_start", "model": "auto"}
{"ts": "2026-03-18T10:00:01Z", "type": "tool_call", "name": "search_web", "args": {"query": "台灣天氣"}}
{"ts": "2026-03-18T10:00:02Z", "type": "tool_result", "name": "search_web", "result": "..."}
{"ts": "2026-03-18T10:00:03Z", "type": "assistant_message", "content": "今天台北..."}
{"ts": "2026-03-18T10:00:03Z", "type": "run_complete", "usage": {"input": 120, "output": 80}}
```

`type` 完整清單：

| type | 說明 |
|---|---|
| `user_message` | 使用者傳入訊息 |
| `assistant_start` | LLM 開始生成 |
| `tool_call` | Agent 呼叫 tool |
| `tool_result` | Tool 執行結果 |
| `assistant_message` | LLM 最終回覆 |
| `run_complete` | 一次 agent run 結束（含 usage） |
| `run_error` | Agent run 發生錯誤 |
| `session_reset` | Session 被重置 |

---

### storage.py 介面設計

```python
# claw/core/storage.py
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
import aiosqlite
import json
import os

DB_PATH = os.path.expanduser("~/.claw/claw.db")
TRANSCRIPT_DIR = os.path.expanduser("~/.claw/transcripts")

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
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self.transcript_dir = TRANSCRIPT_DIR

    async def init(self) -> None:
        """初始化 DB，建立 tables"""
        os.makedirs(self.transcript_dir, exist_ok=True)
        async with aiosqlite.connect(self.db_path) as db:
            await db.executescript(SCHEMA_SQL)
            await db.commit()

    # --- Session ---
    async def get_session(self, session_id: str) -> SessionRow | None: ...
    async def create_session(self, session: SessionRow) -> None: ...
    async def update_last_active(self, session_id: str) -> None: ...
    async def delete_session(self, session_id: str) -> None: ...
    async def list_sessions(self) -> list[SessionRow]: ...

    # --- Messages ---
    async def add_message(self, msg: MessageRow) -> None: ...
    async def get_messages(
        self, session_id: str, limit: int = 50
    ) -> list[MessageRow]: ...
    async def clear_messages(self, session_id: str) -> None: ...

    # --- Transcript (JSONL) ---
    def append_transcript(self, session_id: str, event: dict) -> None:
        """同步寫入（append-only，不 await）"""
        path = os.path.join(self.transcript_dir, f"{session_id}.jsonl")
        # session_id 可能含有 ":" 字符，需轉義成合法 filename
        safe_name = session_id.replace(":", "_")
        path = os.path.join(self.transcript_dir, f"{safe_name}.jsonl")
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
```

---

### TODO 清單

- [ ] 建立 `~/.claw/` 目錄結構（`init()` 呼叫時自動建立）
- [ ] `SCHEMA_SQL` 常數（完整 CREATE TABLE 語句）
- [ ] `Storage.init()` — 建表
- [ ] `Storage.get_session()` — SELECT by session_id
- [ ] `Storage.create_session()` — INSERT
- [ ] `Storage.update_last_active()` — UPDATE last_active
- [ ] `Storage.delete_session()` — DELETE + 相關 messages
- [ ] `Storage.list_sessions()` — SELECT ALL
- [ ] `Storage.add_message()` — INSERT message
- [ ] `Storage.get_messages()` — SELECT 近 N 筆，按 created_at ASC
- [ ] `Storage.clear_messages()` — DELETE WHERE session_id
- [ ] `Storage.append_transcript()` — JSONL append
- [ ] session_id 的 filename 轉義（`:` → `_`）
- [ ] 單元測試：`tests/test_storage.py`
  - [ ] create + get session
  - [ ] add + get messages（順序正確）
  - [ ] transcript append（檔案存在，每行合法 JSON）
  - [ ] delete session 連帶刪除 messages

---

## P1-2　LLM-Router Client

**對應 TS 參考：** 無直接對應（OpenClaw 直接用 SDK，這邊改成 HTTP client）

**負責的事：**
- 封裝所有對 LLM-Router 的 HTTP 呼叫
- Streaming SSE 解析
- Health check

---

### 目錄

```
claw/
└── llm/
    └── router_client.py
```

---

### LLM-Router API 呼叫清單

| 方法 | Endpoint | 說明 |
|---|---|---|
| `complete()` | `POST /v1/chat/completions` | 一般對話（非 streaming） |
| `stream()` | `POST /v1/chat/completions` + `stream: true` | Streaming 對話 |
| `direct_query()` | `POST /v1/direct_query` | 指定 provider + model |
| `health_check()` | `GET /admin/status` | 健康檢查 + quota 查詢 |

---

### router_client.py 介面設計

```python
# claw/llm/router_client.py
from dataclasses import dataclass, field
from typing import AsyncIterator
import httpx
import json

@dataclass
class ChatMessage:
    role: str       # "system" | "user" | "assistant" | "tool"
    content: str | list
    tool_call_id: str | None = None
    tool_calls: list | None = None    # assistant 呼叫 tool 時

@dataclass
class ToolDefinition:
    name: str
    description: str
    parameters: dict              # JSON Schema

@dataclass
class CompletionRequest:
    messages: list[ChatMessage]
    model: str = "auto"           # "auto" | "TextOnlyLow" | "TextOnlyHigh"
    temperature: float = 0.7
    max_tokens: int = 4096
    tools: list[ToolDefinition] | None = None
    tool_choice: str = "auto"     # "auto" | "none" | "required"
    system: str | None = None     # 若有，插入 messages[0] 作為 system role

@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict               # 已解析的 JSON

@dataclass
class CompletionResponse:
    content: str
    model: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str = "stop"
    usage: dict = field(default_factory=dict)

@dataclass
class StreamChunk:
    content: str = ""
    tool_call_delta: dict | None = None  # partial tool call
    finish_reason: str | None = None
    usage: dict | None = None            # 最後一個 chunk 才有

class LLMRouterClient:
    def __init__(self, base_url: str = "http://127.0.0.1:8000", api_key: str = ""):
        self.base_url = base_url.rstrip("/")
        headers = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers=headers,
            timeout=httpx.Timeout(connect=5.0, read=120.0, write=10.0, pool=5.0)
        )

    async def complete(self, req: CompletionRequest) -> CompletionResponse:
        """單次完整回應（不 streaming）"""
        payload = self._build_payload(req, stream=False)
        resp = await self._client.post("/v1/chat/completions", json=payload)
        resp.raise_for_status()
        return self._parse_response(resp.json())

    async def stream(self, req: CompletionRequest) -> AsyncIterator[StreamChunk]:
        """串流回應，yield StreamChunk"""
        payload = self._build_payload(req, stream=True)
        async with self._client.stream(
            "POST", "/v1/chat/completions", json=payload
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data = line[6:].strip()
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    continue
                yield self._parse_stream_chunk(chunk)

    async def direct_query(
        self,
        prompt: str,
        model_name: str,
        provider: str,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> str:
        """指定 provider + model，繞過自動路由"""
        resp = await self._client.post("/v1/direct_query", json={
            "model_name": model_name,
            "provider": provider,
            "prompt": prompt,
            "temperature": temperature,
            "max_tokens": max_tokens,
        })
        resp.raise_for_status()
        data = resp.json()
        return data.get("content", "")

    async def health_check(self) -> dict:
        """回傳 quota 狀態；連不上則 raise"""
        resp = await self._client.get("/admin/status", timeout=5.0)
        resp.raise_for_status()
        return resp.json()

    async def close(self) -> None:
        await self._client.aclose()

    # --- private ---

    def _build_payload(self, req: CompletionRequest, stream: bool) -> dict:
        messages = []
        if req.system:
            messages.append({"role": "system", "content": req.system})
        for m in req.messages:
            msg: dict = {"role": m.role, "content": m.content}
            if m.tool_call_id:
                msg["tool_call_id"] = m.tool_call_id
            if m.tool_calls:
                msg["tool_calls"] = m.tool_calls
            messages.append(msg)

        payload: dict = {
            "model": req.model,
            "messages": messages,
            "temperature": req.temperature,
            "max_tokens": req.max_tokens,
            "stream": stream,
        }
        if req.tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters,
                    }
                }
                for t in req.tools
            ]
            payload["tool_choice"] = req.tool_choice
        return payload

    def _parse_response(self, data: dict) -> CompletionResponse:
        choice = data["choices"][0]
        msg = choice["message"]
        tool_calls = []
        for tc in msg.get("tool_calls") or []:
            tool_calls.append(ToolCall(
                id=tc["id"],
                name=tc["function"]["name"],
                arguments=json.loads(tc["function"]["arguments"]),
            ))
        return CompletionResponse(
            content=msg.get("content") or "",
            model=data.get("model", ""),
            tool_calls=tool_calls,
            finish_reason=choice.get("finish_reason", "stop"),
            usage=data.get("usage", {}),
        )

    def _parse_stream_chunk(self, data: dict) -> StreamChunk:
        choice = data["choices"][0]
        delta = choice.get("delta", {})
        return StreamChunk(
            content=delta.get("content") or "",
            tool_call_delta=delta.get("tool_calls"),
            finish_reason=choice.get("finish_reason"),
            usage=data.get("usage"),
        )
```

---

### TODO 清單

- [ ] `LLMRouterClient.__init__()` — httpx.AsyncClient 初始化
- [ ] `LLMRouterClient.complete()` — POST + parse response
- [ ] `LLMRouterClient.stream()` — SSE 解析（`data: ` 前綴、`[DONE]` 終止）
- [ ] `LLMRouterClient.direct_query()` — 指定 model
- [ ] `LLMRouterClient.health_check()` — GET /admin/status
- [ ] `LLMRouterClient.close()` — 釋放 httpx client
- [ ] `_build_payload()` — system prompt 注入 + tools 格式轉換
- [ ] `_parse_response()` — tool_calls JSON 解析
- [ ] `_parse_stream_chunk()` — delta 解析 + tool_call_delta 累積
- [ ] streaming 時 tool_call arguments 是分段來的，需要累積組裝完整 JSON
- [ ] 錯誤處理：`HTTPStatusError` 包裝成 `LLMRouterError`
- [ ] 單元測試：`tests/test_router_client.py`（用 `respx` mock httpx）
  - [ ] complete() 正常回應
  - [ ] stream() SSE 解析正確
  - [ ] stream() tool_call delta 組裝正確
  - [ ] health_check() 連線失敗時 raise

---

## P1-3　Tool Registry

**對應 TS 參考：**
- `src/agents/tool-catalog.ts`
- `src/agents/tool-policy.ts`
- `src/agents/bash-tools.ts`
- `src/node-host/invoke.ts`

**負責的事：**
- Tool 的定義（OpenAI function-calling schema）
- Tool 的執行（呼叫對應 Python 函數）
- Policy 判斷（main session = host，其他 = Phase 2 補 Docker）

---

### 目錄

```
claw/
└── tools/
    ├── registry.py
    ├── policy.py
    └── bash.py
```

---

### tool 定義方式

```python
# claw/tools/registry.py
from dataclasses import dataclass
from typing import Callable, Awaitable, Any
import functools

@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict          # JSON Schema（type: object, properties: {...}）
    handler: Callable[..., Awaitable[str]]   # async 函數
    requires_main: bool = False  # True = 只能在 main session 執行

# 全域 registry
_registry: dict[str, ToolSpec] = {}

def tool(
    name: str,
    description: str,
    parameters: dict,
    requires_main: bool = False,
):
    """裝飾器，把一個 async 函數注冊為 tool"""
    def decorator(fn: Callable) -> Callable:
        _registry[name] = ToolSpec(
            name=name,
            description=description,
            parameters=parameters,
            handler=fn,
            requires_main=requires_main,
        )
        return fn
    return decorator

def get_definitions(session_is_main: bool = False) -> list[dict]:
    """回傳 LLM-Router 可用的 tool definitions（OpenAI schema）"""
    specs = []
    for spec in _registry.values():
        if spec.requires_main and not session_is_main:
            continue    # 非 main session 看不到這個 tool
        specs.append({
            "type": "function",
            "function": {
                "name": spec.name,
                "description": spec.description,
                "parameters": spec.parameters,
            }
        })
    return specs

async def execute(name: str, arguments: dict, session_is_main: bool = False) -> str:
    """執行 tool，回傳結果字串"""
    spec = _registry.get(name)
    if spec is None:
        return f"Error: unknown tool '{name}'"
    if spec.requires_main and not session_is_main:
        return f"Error: tool '{name}' requires main session"
    try:
        result = await spec.handler(**arguments)
        return str(result)
    except Exception as e:
        return f"Error: {e}"
```

---

### bash tool

```python
# claw/tools/bash.py
import asyncio
from .registry import tool

@tool(
    name="bash",
    description="在 host 上執行 bash 指令，回傳 stdout + stderr",
    parameters={
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "要執行的 bash 指令"
            },
            "timeout": {
                "type": "integer",
                "description": "逾時秒數，預設 30",
                "default": 30
            }
        },
        "required": ["command"]
    },
    requires_main=True,   # Phase 2 前只能在 main session 用
)
async def bash_tool(command: str, timeout: int = 30) -> str:
    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        output = stdout.decode("utf-8", errors="replace")
        exit_code = proc.returncode
        if exit_code != 0:
            return f"[exit {exit_code}]\n{output}"
        return output
    except asyncio.TimeoutError:
        return f"Error: command timed out after {timeout}s"
    except Exception as e:
        return f"Error: {e}"
```

---

### TODO 清單

- [ ] `ToolSpec` dataclass
- [ ] `_registry` 全域 dict
- [ ] `tool()` 裝飾器（register）
- [ ] `get_definitions()` — 依 session 過濾 + 轉成 OpenAI schema
- [ ] `execute()` — dispatch + requires_main 檢查 + 錯誤包裝
- [ ] `bash.py` — bash tool 實作
  - [ ] asyncio.create_subprocess_shell
  - [ ] timeout 處理
  - [ ] exit code 非 0 時標記
  - [ ] stdout + stderr 合併輸出
- [ ] policy.py — `is_main_session(session_id: str) -> bool`（判斷 scope）
- [ ] 單元測試：`tests/test_tools.py`
  - [ ] register + get_definitions（main / non-main 過濾正確）
  - [ ] execute 正常回傳
  - [ ] execute 未知 tool 回傳 error string
  - [ ] bash tool：正常指令、timeout、非零 exit code

---

## P1-4　Agent Loop

**對應 TS 參考：**
- `src/agents/pi-embedded-runner.ts`
- `src/agents/pi-embedded-subscribe.ts`
- `src/auto-reply/reply.ts`
- `src/auto-reply/chunk.ts`
- `src/auto-reply/dispatch.ts`

**負責的事：**
- 接收一則訊息，跑完整個 agent 執行迴圈
- 串流輸出 Event（text chunk、tool call、run complete）
- 把結果寫回 Storage

---

### 目錄

```
claw/
└── agent/
    ├── loop.py
    ├── events.py
    └── context.py
```

---

### Event 定義

```python
# claw/agent/events.py
from dataclasses import dataclass, field
from typing import Literal

@dataclass
class TextChunk:
    type: Literal["text_chunk"] = "text_chunk"
    content: str = ""

@dataclass
class ToolCallStart:
    type: Literal["tool_call_start"] = "tool_call_start"
    tool_call_id: str = ""
    name: str = ""
    arguments: dict = field(default_factory=dict)

@dataclass
class ToolCallResult:
    type: Literal["tool_call_result"] = "tool_call_result"
    tool_call_id: str = ""
    name: str = ""
    result: str = ""

@dataclass
class RunComplete:
    type: Literal["run_complete"] = "run_complete"
    full_content: str = ""
    usage: dict = field(default_factory=dict)

@dataclass
class RunError:
    type: Literal["run_error"] = "run_error"
    error: str = ""

# Union type（讓 caller 做 isinstance 判斷）
Event = TextChunk | ToolCallStart | ToolCallResult | RunComplete | RunError
```

---

### Context 組裝

```python
# claw/agent/context.py
from claw.core.storage import Storage, MessageRow
from claw.llm.router_client import ChatMessage

DEFAULT_SYSTEM_PROMPT = """\
You are a helpful assistant. Answer concisely and accurately.
When you need to search the web or run commands, use the available tools.
"""

MAX_CONTEXT_MESSAGES = 40    # 最多帶入 40 則歷史訊息
MAX_CONTEXT_TOKENS = 8000    # 保守估計，避免超過 context window

async def build_context(
    storage: Storage,
    session_id: str,
    new_user_message: str,
    system_prompt: str | None = None,
) -> list[ChatMessage]:
    """
    組裝送給 LLM 的 messages list。
    順序：system → 歷史訊息（最近 N 筆）→ 新的 user message
    """
    history = await storage.get_messages(session_id, limit=MAX_CONTEXT_MESSAGES)

    messages: list[ChatMessage] = []

    # 歷史訊息
    for row in history:
        content = row.content
        if isinstance(content, str):
            try:
                import json
                content = json.loads(content)
            except Exception:
                pass  # 保持原始 string
        msg = ChatMessage(role=row.role, content=content)
        if row.tool_call_id:
            msg.tool_call_id = row.tool_call_id
        messages.append(msg)

    # 新 user message
    messages.append(ChatMessage(role="user", content=new_user_message))
    return messages
```

---

### Agent Loop

```python
# claw/agent/loop.py
from typing import AsyncIterator
import json
from datetime import datetime, timezone

from claw.core.storage import Storage, MessageRow
from claw.llm.router_client import LLMRouterClient, CompletionRequest, StreamChunk
from claw.tools import registry as tool_registry
from claw.tools.policy import is_main_session
from claw.agent.events import (
    Event, TextChunk, ToolCallStart, ToolCallResult, RunComplete, RunError
)
from claw.agent.context import build_context, DEFAULT_SYSTEM_PROMPT

MAX_TOOL_ROUNDS = 8   # 最多幾輪 tool call，防止無限迴圈

class AgentLoop:
    def __init__(self, storage: Storage, llm: LLMRouterClient):
        self.storage = storage
        self.llm = llm

    async def run(
        self,
        session_id: str,
        user_message: str,
        system_prompt: str | None = None,
        model: str = "auto",
    ) -> AsyncIterator[Event]:
        """
        執行一次 agent run，yield Events。
        caller 用 async for 收 events，即時串流輸出。
        """
        session = await self.storage.get_session(session_id)
        if session is None:
            yield RunError(error=f"session not found: {session_id}")
            return

        is_main = is_main_session(session_id)
        sys_prompt = system_prompt or session.system_prompt or DEFAULT_SYSTEM_PROMPT

        # 把 user message 存入 storage
        await self._save_message(session_id, "user", user_message)
        self.storage.append_transcript(session_id, {
            "ts": now_iso(), "type": "user_message", "content": user_message
        })

        messages = await build_context(self.storage, session_id, user_message, sys_prompt)
        tool_defs = tool_registry.get_definitions(session_is_main=is_main)

        full_content = ""
        usage = {}

        try:
            for round_num in range(MAX_TOOL_ROUNDS + 1):
                req = CompletionRequest(
                    messages=messages,
                    model=model,
                    tools=None if not tool_defs else ...,  # 見下方 _make_request
                    system=sys_prompt if round_num == 0 else None,
                )
                req = self._make_request(messages, sys_prompt, tool_defs, model, round_num)

                # --- streaming ---
                content_buffer = ""
                tool_call_buffers: dict[int, dict] = {}   # index → partial tool call

                self.storage.append_transcript(session_id, {
                    "ts": now_iso(), "type": "assistant_start", "model": model
                })

                async for chunk in self.llm.stream(req):
                    # 文字 chunk
                    if chunk.content:
                        content_buffer += chunk.content
                        yield TextChunk(content=chunk.content)

                    # tool call delta（分段累積）
                    if chunk.tool_call_delta:
                        for tc_delta in chunk.tool_call_delta:
                            idx = tc_delta.get("index", 0)
                            if idx not in tool_call_buffers:
                                tool_call_buffers[idx] = {
                                    "id": "", "name": "", "arguments": ""
                                }
                            buf = tool_call_buffers[idx]
                            fn = tc_delta.get("function", {})
                            buf["id"] = tc_delta.get("id") or buf["id"]
                            buf["name"] = fn.get("name") or buf["name"]
                            buf["arguments"] += fn.get("arguments") or ""

                    if chunk.usage:
                        usage = chunk.usage

                # --- 處理 tool calls ---
                if not tool_call_buffers:
                    # 沒有 tool call，這一輪結束
                    full_content += content_buffer
                    await self._save_message(session_id, "assistant", content_buffer)
                    self.storage.append_transcript(session_id, {
                        "ts": now_iso(), "type": "assistant_message",
                        "content": content_buffer
                    })
                    break

                # 把 assistant message（含 tool_calls）加入 messages
                tool_calls_payload = []
                for idx, buf in sorted(tool_call_buffers.items()):
                    tool_calls_payload.append({
                        "id": buf["id"],
                        "type": "function",
                        "function": {
                            "name": buf["name"],
                            "arguments": buf["arguments"],
                        }
                    })
                from claw.llm.router_client import ChatMessage
                messages.append(ChatMessage(
                    role="assistant",
                    content=content_buffer or "",
                    tool_calls=tool_calls_payload,
                ))

                # 執行每個 tool call
                for buf in tool_call_buffers.values():
                    tc_id = buf["id"]
                    tc_name = buf["name"]
                    try:
                        tc_args = json.loads(buf["arguments"])
                    except json.JSONDecodeError:
                        tc_args = {}

                    self.storage.append_transcript(session_id, {
                        "ts": now_iso(), "type": "tool_call",
                        "name": tc_name, "args": tc_args
                    })
                    yield ToolCallStart(
                        tool_call_id=tc_id, name=tc_name, arguments=tc_args
                    )

                    result = await tool_registry.execute(
                        tc_name, tc_args, session_is_main=is_main
                    )

                    self.storage.append_transcript(session_id, {
                        "ts": now_iso(), "type": "tool_result",
                        "name": tc_name, "result": result[:500]  # truncate for transcript
                    })
                    yield ToolCallResult(
                        tool_call_id=tc_id, name=tc_name, result=result
                    )

                    # tool result 加入 messages，下一輪繼續
                    messages.append(ChatMessage(
                        role="tool",
                        content=result,
                        tool_call_id=tc_id,
                    ))
                    await self._save_message(
                        session_id, "tool", result,
                        tool_call_id=tc_id, tool_name=tc_name
                    )

            await self.storage.update_last_active(session_id)
            self.storage.append_transcript(session_id, {
                "ts": now_iso(), "type": "run_complete", "usage": usage
            })
            yield RunComplete(full_content=full_content, usage=usage)

        except Exception as e:
            self.storage.append_transcript(session_id, {
                "ts": now_iso(), "type": "run_error", "error": str(e)
            })
            yield RunError(error=str(e))

    def _make_request(
        self,
        messages,
        system_prompt: str,
        tool_defs: list,
        model: str,
        round_num: int,
    ) -> CompletionRequest:
        from claw.llm.router_client import CompletionRequest, ToolDefinition
        tools = None
        if tool_defs:
            tools = [
                ToolDefinition(
                    name=t["function"]["name"],
                    description=t["function"]["description"],
                    parameters=t["function"]["parameters"],
                )
                for t in tool_defs
            ]
        return CompletionRequest(
            messages=messages,
            model=model,
            tools=tools,
            system=system_prompt if round_num == 0 else None,
        )

    async def _save_message(
        self,
        session_id: str,
        role: str,
        content,
        tool_call_id: str | None = None,
        tool_name: str | None = None,
    ) -> None:
        import json as _json
        content_str = content if isinstance(content, str) else _json.dumps(content)
        await self.storage.add_message(MessageRow(
            session_id=session_id,
            role=role,
            content=content_str,
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            created_at=now_iso(),
        ))

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
```

---

### TODO 清單

- [ ] `events.py` — 5 個 Event dataclass
- [ ] `context.py` — `build_context()`（history 組裝 + 新訊息）
- [ ] `loop.py` — `AgentLoop.__init__()`
- [ ] `AgentLoop.run()` — 主迴圈骨架
  - [ ] session 取得 + is_main 判斷
  - [ ] user message 存入 storage + transcript
  - [ ] context 組裝
  - [ ] streaming 呼叫 LLM-Router
  - [ ] text chunk yield
  - [ ] tool_call_delta 累積（partial JSON arguments）
  - [ ] tool call 執行（`tool_registry.execute()`）
  - [ ] tool result 存入 messages + storage
  - [ ] 下一輪繼續（messages 更新）
  - [ ] 無 tool call 時退出迴圈
  - [ ] MAX_TOOL_ROUNDS 保護
  - [ ] RunComplete yield（含 usage）
  - [ ] RunError yield（Exception 捕獲）
- [ ] 單元測試：`tests/test_agent_loop.py`（用 mock LLM + mock Storage）
  - [ ] 純文字回覆（無 tool call）
  - [ ] 一次 tool call + 繼續生成
  - [ ] 多輪 tool call
  - [ ] MAX_TOOL_ROUNDS 到上限後停止
  - [ ] LLM 拋錯時 yield RunError

---

## P1-5　Queue

**對應 TS 參考：**
- `src/process/lanes.ts`
- `src/process/command-queue.ts`
- `src/channels/inbound-debounce-policy.ts`

**負責的事：**
- 確保同一個 session 不會同時跑兩個 agent run
- 控制訊息堆積時的行為（collect / followup / drop）

---

### 目錄

```
claw/
└── core/
    └── queue.py
```

---

### Queue 設計

```python
# claw/core/queue.py
import asyncio
from dataclasses import dataclass
from typing import Callable, Awaitable, Any
from enum import Enum

class QueueMode(str, Enum):
    COLLECT   = "collect"   # 等目前 run 結束，把累積的訊息一起處理
    FOLLOWUP  = "followup"  # 等目前 run 結束，立即啟動下一個 run
    DROP      = "drop"      # 丟棄（busy 時不接受新訊息）

@dataclass
class QueuedMessage:
    session_id: str
    user_message: str
    # 未來可加：附件、metadata

class SessionLane:
    """單一 session 的訊息 lane"""

    def __init__(self, session_id: str, mode: QueueMode = QueueMode.COLLECT):
        self.session_id = session_id
        self.mode = mode
        self._queue: asyncio.Queue[QueuedMessage] = asyncio.Queue()
        self._running = False

    @property
    def is_busy(self) -> bool:
        return self._running

    async def enqueue(self, msg: QueuedMessage) -> bool:
        """
        回傳 True = 成功入隊，False = 被 drop
        """
        if self._running:
            if self.mode == QueueMode.DROP:
                return False
            # COLLECT / FOLLOWUP：都放入 queue，等待處理
        await self._queue.put(msg)
        return True

    async def run_loop(
        self,
        handler: Callable[[str, str], Awaitable[Any]]
    ) -> None:
        """
        持續從 queue 取訊息執行 handler（agent loop）。
        handler signature: async def handler(session_id, user_message)
        """
        while True:
            msg = await self._queue.get()
            self._running = True
            try:
                await handler(msg.session_id, msg.user_message)
            finally:
                self._running = False
                self._queue.task_done()


class MessageQueue:
    """全域 queue，管理所有 session lanes"""

    def __init__(self):
        self._lanes: dict[str, SessionLane] = {}
        self._tasks: dict[str, asyncio.Task] = {}

    def get_or_create_lane(
        self, session_id: str, mode: QueueMode = QueueMode.COLLECT
    ) -> SessionLane:
        if session_id not in self._lanes:
            self._lanes[session_id] = SessionLane(session_id, mode)
        return self._lanes[session_id]

    async def submit(
        self,
        session_id: str,
        user_message: str,
        handler: Callable[[str, str], Awaitable[Any]],
        mode: QueueMode = QueueMode.COLLECT,
    ) -> bool:
        """
        提交一則訊息到 session lane。
        如果 lane 的 run_loop 還沒啟動，自動啟動。
        回傳 True = 成功入隊
        """
        lane = self.get_or_create_lane(session_id, mode)
        queued = await lane.enqueue(QueuedMessage(session_id, user_message))
        if not queued:
            return False
        # 確保 run_loop task 存在
        if session_id not in self._tasks or self._tasks[session_id].done():
            self._tasks[session_id] = asyncio.create_task(
                lane.run_loop(handler)
            )
        return True

    def remove_lane(self, session_id: str) -> None:
        if session_id in self._tasks:
            self._tasks[session_id].cancel()
            del self._tasks[session_id]
        self._lanes.pop(session_id, None)
```

---

### TODO 清單

- [ ] `QueueMode` Enum
- [ ] `QueuedMessage` dataclass
- [ ] `SessionLane.__init__()`
- [ ] `SessionLane.enqueue()` — DROP / COLLECT / FOLLOWUP 判斷
- [ ] `SessionLane.run_loop()` — 持續取 + 執行 handler
- [ ] `MessageQueue.get_or_create_lane()`
- [ ] `MessageQueue.submit()` — enqueue + 自動啟動 run_loop task
- [ ] `MessageQueue.remove_lane()` — 取消 task + 清理
- [ ] 單元測試：`tests/test_queue.py`
  - [ ] 單一訊息正常執行
  - [ ] 兩則訊息串行執行（不並行）
  - [ ] DROP mode：busy 時第二則被丟棄
  - [ ] COLLECT mode：busy 時第二則排隊，run 結束後執行
  - [ ] FOLLOWUP mode：同 COLLECT 行為

---

## P1-6　Gateway

**對應 TS 參考：**
- `src/gateway/server.ts`
- `src/gateway/server.impl.ts`
- `src/gateway/server-chat.ts`
- `src/gateway/protocol/`

**負責的事：**
- 啟動 FastAPI server
- WebSocket 控制平面（RPC）
- HTTP `/v1/chat/completions` 入口
- 把訊息丟入 Queue → Agent Loop → 串流回應

---

### 目錄

```
claw/
└── core/
    ├── gateway.py
    └── protocol.py
```

---

### Protocol 格式

```python
# claw/core/protocol.py
from dataclasses import dataclass, field
from typing import Any, Literal

# --- WebSocket frames ---

@dataclass
class ConnectFrame:
    """第一幀，必須"""
    type: Literal["connect"] = "connect"
    agent_id: str = "default"
    token: str = ""           # Phase 2 補認證；Phase 1 先不驗

@dataclass
class RequestFrame:
    """Client → Server RPC 呼叫"""
    type: Literal["req"] = "req"
    id: str = ""              # 用來對應 response
    method: str = ""          # e.g. "sessions.get", "agent.run"
    params: dict = field(default_factory=dict)

@dataclass
class ResponseFrame:
    """Server → Client RPC 回應"""
    type: Literal["res"] = "res"
    id: str = ""
    result: Any = None
    error: str | None = None

@dataclass
class EventFrame:
    """Server → Client 單向 push"""
    type: Literal["event"] = "event"
    event: str = ""           # e.g. "agent.text_chunk", "agent.run_complete"
    data: dict = field(default_factory=dict)

# --- RPC methods（P1 最小集合）---
# sessions.get         → 取得 session metadata
# sessions.create      → 建立 session
# sessions.delete      → 刪除 session
# agent.run            → 執行 agent run（streaming 透過 events push）
# agent.abort          → 中止進行中的 run（Phase 2）
# health               → health check
```

---

### Gateway

```python
# claw/core/gateway.py
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
import json
import asyncio

from claw.core.storage import Storage
from claw.core.queue import MessageQueue, QueueMode
from claw.llm.router_client import LLMRouterClient
from claw.agent.loop import AgentLoop
from claw.agent.events import TextChunk, ToolCallStart, ToolCallResult, RunComplete, RunError
from claw.core.protocol import ConnectFrame, ResponseFrame, EventFrame

app = FastAPI(title="claw-python gateway")

# --- 依賴注入（由 main.py 設定）---
storage: Storage = None
queue: MessageQueue = None
llm: LLMRouterClient = None

def get_agent_loop() -> AgentLoop:
    return AgentLoop(storage=storage, llm=llm)

# --- WebSocket 控制平面 ---

@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    loop = get_agent_loop()

    try:
        # 第一幀必須是 connect frame
        raw = await ws.receive_json()
        if raw.get("type") != "connect":
            await ws.close(code=4001)
            return

        agent_id = raw.get("agent_id", "default")

        # 進入 RPC 迴圈
        async for data in ws.iter_json():
            frame_id = data.get("id", "")
            method = data.get("method", "")
            params = data.get("params", {})

            # health
            if method == "health":
                status = await llm.health_check()
                await ws.send_json(ResponseFrame(id=frame_id, result=status).__dict__)

            # sessions.get
            elif method == "sessions.get":
                session = await storage.get_session(params["session_id"])
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
                await storage.create_session(s)
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

                await queue.submit(session_id, user_message, run_and_push)
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
    loop = get_agent_loop()

    # 確保 session 存在
    session = await storage.get_session(session_id)
    if session is None:
        from claw.core.storage import SessionRow
        from claw.agent.loop import now_iso
        await storage.create_session(SessionRow(
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
        status = await llm.health_check()
        return {"status": "ok", "llm_router": status}
    except Exception as e:
        return {"status": "error", "error": str(e)}
```

---

### TODO 清單

- [ ] `protocol.py` — 4 個 frame dataclass
- [ ] `gateway.py` — FastAPI app 建立
- [ ] WebSocket `/ws` endpoint
  - [ ] connect frame 驗證（第一幀）
  - [ ] `health` RPC method
  - [ ] `sessions.get` RPC method
  - [ ] `sessions.create` RPC method
  - [ ] `agent.run` RPC method → queue.submit → event push
  - [ ] WebSocketDisconnect 處理
- [ ] `POST /v1/chat/completions`
  - [ ] session 自動建立（不存在時）
  - [ ] streaming SSE 回應
  - [ ] 非 streaming 一次性回應
- [ ] `GET /health`
- [ ] `main.py` — 依賴注入 + uvicorn 啟動
- [ ] 單元測試：`tests/test_gateway.py`（用 httpx.AsyncClient + FastAPI TestClient）
  - [ ] `/health` 正常回應
  - [ ] `POST /v1/chat/completions` 非 streaming
  - [ ] `POST /v1/chat/completions` streaming SSE 格式正確

---

## P1-7　HTTP Channel（End-to-end 測試）

HTTP Channel 是 Phase 1 的最小可用驗證。你可以用 `curl` 直接打 Gateway 的 `/v1/chat/completions`，就等於是在用 HTTP Channel。

```bash
# 測試整個 pipeline
curl -X POST http://127.0.0.1:18789/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "agent:main",
    "messages": [{"role": "user", "content": "現在幾點？用 bash 查一下"}],
    "model": "auto",
    "stream": true
  }'
```

預期行為：
1. Gateway 收到請求
2. 建立 / 取得 `agent:main` session
3. 訊息丟入 Queue lane
4. Agent Loop 執行：呼叫 LLM-Router → LLM 呼叫 bash tool → 執行 `date` → 繼續生成
5. 串流 SSE 回傳 text chunks
6. 最後 `data: [DONE]`

---

## 啟動與目錄初始化

### main.py

```python
# claw/main.py
import asyncio
import uvicorn
from claw.core.storage import Storage
from claw.core.queue import MessageQueue
from claw.llm.router_client import LLMRouterClient
import claw.core.gateway as gateway_module
import claw.tools.bash  # 觸發 bash tool 的注冊

async def startup():
    import os
    from dotenv import load_dotenv
    load_dotenv()

    storage = Storage()
    await storage.init()

    llm = LLMRouterClient(
        base_url=os.getenv("LLM_ROUTER_URL", "http://127.0.0.1:8000"),
        api_key=os.getenv("LLM_ROUTER_API_KEY", ""),
    )

    # 注入到 gateway 模組
    gateway_module.storage = storage
    gateway_module.queue = MessageQueue()
    gateway_module.llm = llm

if __name__ == "__main__":
    asyncio.run(startup())
    uvicorn.run(
        "claw.core.gateway:app",
        host="127.0.0.1",
        port=18789,
        reload=False,
    )
```

### 目錄結構（Phase 1 完成後）

```
~/.claw/
├── claw.db                     # SQLite
└── transcripts/
    ├── agent_main.jsonl
    └── agent_telegram_group_123.jsonl
```

---

## Phase 1 完整 TODO（彙整）

### 依序實作

```
[ ] P1-1  claw/core/storage.py
[ ] P1-1  tests/test_storage.py

[ ] P1-2  claw/llm/router_client.py
[ ] P1-2  tests/test_router_client.py

[ ] P1-3  claw/tools/registry.py
[ ] P1-3  claw/tools/policy.py
[ ] P1-3  claw/tools/bash.py
[ ] P1-3  tests/test_tools.py

[ ] P1-4  claw/agent/events.py
[ ] P1-4  claw/agent/context.py
[ ] P1-4  claw/agent/loop.py
[ ] P1-4  tests/test_agent_loop.py

[ ] P1-5  claw/core/queue.py
[ ] P1-5  tests/test_queue.py

[ ] P1-6  claw/core/protocol.py
[ ] P1-6  claw/core/gateway.py
[ ] P1-6  claw/main.py
[ ] P1-6  tests/test_gateway.py

[ ] P1-7  end-to-end curl 測試通過
```

### 每完成一個模組應驗證

1. 單元測試全過
2. `mypy claw/` 無 type error（可選，但建議）
3. `python -c "from claw.xxx import Xxx"` 可以 import

---

## pyproject.toml（Phase 1 最小）

```toml
[project]
name = "claw-python"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.110.0",
    "uvicorn[standard]>=0.27.0",
    "httpx>=0.27.0",
    "pydantic>=2.6.0",
    "pyyaml>=6.0",
    "python-dotenv>=1.0.0",
    "aiosqlite>=0.20.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "respx>=0.21.0",        # mock httpx
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
```

---

## .env.example（Phase 1）

```env
# LLM-Router 的 URL
LLM_ROUTER_URL=http://127.0.0.1:8000

# LLM-Router API Key（claw-python 向 LLM-Router 認證用）
# API key 是交給 LLM-Router 的，LLM-Router 自己管 OpenAI / Gemini 等的 key
# claw-python 這邊不持有任何 LLM 廠商的 key
LLM_ROUTER_API_KEY=

# Gateway 啟動設定
CLAW_HOST=127.0.0.1
CLAW_PORT=18789

# 資料目錄（預設 ~/.claw）
CLAW_DATA_DIR=~/.claw
```

---

## 注意事項

1. **tool call arguments 是分段 streaming 來的** — LLM-Router 的 SSE 中，`tool_calls[].function.arguments` 是 JSON 字串的 partial chunk，需要累積後才能 `json.loads()`。這是 P1-4 最容易出錯的地方。

2. **session_id 裡有冒號** — 存 JSONL 檔名時要把 `:` 換成 `_`（已在 storage.py 中處理）。

3. **LLM-Router 的 streaming 格式** — 確認 LLM-Router 回的 SSE 是標準 OpenAI 格式（`data: {...}\n\n`），如果有差異要在 `router_client.py` 的 `_parse_stream_chunk()` 調整。

4. **Queue 的 run_loop task 洩漏** — `asyncio.create_task()` 建立的 task 如果沒有被 await 或 cancel，會在背景繼續跑。`MessageQueue.remove_lane()` 確保清理。

5. **並發安全** — SQLite 在 asyncio 中用 `aiosqlite`，不要直接用 `sqlite3`（blocking）。
