# Phase 3 實作計劃書

> **目標：** Channels 抽象層、Cron 排程、Multi-agent ACP、Slash Commands、Media 基礎處理。
> Telegram / Discord channel adapter 作為首批具體 channel 落地。
>
> **前提：** Phase 2 + 2.5 全部完成，54 tests 通過。
>
> **交付驗收標準：** `python -m pytest tests/ -v` 全數通過（含新增測試）。

---

## 架構現況（Phase 2 完成後）

```
claw/
├── agent/        loop.py, hooks.py, context.py, events.py, prompt_tools.py
├── core/         gateway.py, storage.py, queue.py, auth.py, config.py, pairing.py, protocol.py
├── llm/          router_client.py
├── sandbox/      docker_runner.py, policy.py
├── skills/       base.py, loader.py, registry.py, manifest.py
└── tools/        registry.py, policy.py, bash.py, search.py
```

**Phase 3 新增目錄：**
```
claw/
├── channels/     base.py, policy.py, http_api.py, telegram.py, discord_channel.py
├── cron/         service.py, store.py, runner.py, schedule.py
├── media/        store.py, input.py, mime.py
└── agent/        commands.py（新增）, multi_agent.py（新增）
claw/tools/       sessions_tools.py（新增）, cron.py（新增）
```

---

## P3-1　Channel 抽象層

### `claw/channels/base.py`

```python
from abc import ABC, abstractmethod
from typing import AsyncIterator

class BaseChannel(ABC):
    """所有 channel adapter 的抽象基底。"""

    @abstractmethod
    async def start(self) -> None:
        """啟動 channel（連線、webhook server、polling 等）。"""

    @abstractmethod
    async def stop(self) -> None:
        """關閉 channel。"""

    @abstractmethod
    async def send(self, session_id: str, text: str) -> None:
        """送出純文字回覆。"""

    async def send_stream(
        self, session_id: str, chunks: AsyncIterator[str]
    ) -> None:
        """串流回覆。預設實作：累積後一次 send。子類可覆寫為逐步更新（draft 模式）。"""
        buf = ""
        async for chunk in chunks:
            buf += chunk
        await self.send(session_id, buf)

    async def send_typing(self, session_id: str) -> None:
        """發送「正在輸入」指示（選實作）。"""

    async def send_ack(self, session_id: str, emoji: str = "✅") -> None:
        """發送 ack reaction（選實作）。"""
```

### `claw/channels/policy.py`

```python
@dataclass
class ChannelPolicy:
    allow_from: list[str] = field(default_factory=list)   # user ID 白名單（空 = 允許全部）
    dm_policy: str = "open"   # "open" | "paired" | "disabled"
    command_roles: dict[str, list[str]] = field(default_factory=dict)  # command → [allowed_user_ids]
```

---

## P3-2　Telegram Channel

**檔案：** `claw/channels/telegram.py`
**依賴：** `python-telegram-bot>=21.0`

實作要點：
- `python-telegram-bot` Application + `CommandHandler` + `MessageHandler`
- 私訊 + 群組訊息接收 → `MessageQueue.submit()`
- `send()` 呼叫 `bot.send_message()`
- `send_stream()` 採 draft 模式：初次 `send_message` 拿到 `message_id`，後續串流 chunk 時用 `edit_message_text()` 更新（每 0.5 秒 throttle 一次）
- `send_typing()` 呼叫 `bot.send_chat_action(ChatAction.TYPING)`
- Session ID 規則：私訊 → `agent:main`；群組 → `agent:tg:group:{chat_id}`

---

## P3-3　Discord Channel

**檔案：** `claw/channels/discord_channel.py`
**依賴：** `discord.py>=2.3.0`

實作要點：
- `discord.Client` + `on_message` event
- DM + 伺服器頻道訊息接收 → `MessageQueue.submit()`
- `send()` 呼叫 `channel.send()`
- `send_stream()` 採 chunk 累積後送出（Discord 無原生 edit streaming）
- Session ID 規則：DM → `agent:main`；伺服器頻道 → `agent:dc:guild:{guild_id}:ch:{channel_id}`

---

## P3-4　Slash Command System

**檔案：** `claw/agent/commands.py`

```python
@dataclass
class Command:
    name: str           # e.g. "reset"（不含 /）
    description: str
    handler: Callable   # async def handler(session_id, args, storage) -> str

class CommandRegistry:
    def register(self, cmd: Command) -> None: ...
    def parse(self, text: str) -> tuple[Command, str] | None:
        """若 text 以 /name 開頭則回傳 (command, args)，否則 None。"""
    async def execute(self, session_id: str, text: str, storage: Storage) -> str | None:
        """執行 command，回傳回覆字串；不是 command 則回傳 None。"""

_registry = CommandRegistry()

def command(name: str, description: str):
    """裝飾器：自動注冊 command。"""
```

內建 command：
- `/reset` — 清除 session 歷史訊息（呼叫 `storage.clear_messages(session_id)`）
- `/history [n]` — 顯示最近 n 條訊息（預設 10）
- `/skills` — 列出已載入的 skills
- `/cron list` — 列出排程任務（需要 P3-5）

**AgentLoop 整合：** 在 `loop.py` 的 `run()` 入口處，先呼叫 `command_registry.execute()`；若有命中則直接 yield `TextChunk(content=result)` + `RunComplete`，不走 LLM。

---

## P3-5　Cron Scheduler

### Schema

**`claw/cron/store.py`** — SQLite `cron_jobs` 表

```sql
CREATE TABLE cron_jobs (
    id          TEXT PRIMARY KEY,
    session_id  TEXT NOT NULL,
    schedule    TEXT NOT NULL,   -- cron 表達式，e.g. "0 9 * * 1-5"
    prompt      TEXT NOT NULL,   -- 觸發時送給 agent 的 user message
    enabled     INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL,
    last_run    TEXT,
    next_run    TEXT
);
```

### `claw/cron/schedule.py`

```python
def next_run_dt(cron_expr: str, after: datetime | None = None) -> datetime:
    """解析 cron 表達式，回傳下次執行時間（UTC）。使用 croniter。"""
```

### `claw/cron/runner.py`

```python
async def run_cron_job(job: CronJob, storage: Storage, llm: LLMRouterClient) -> None:
    """
    以 isolated session 執行 cron job：
    1. 若 job.session_id 不存在，自動建立（scope="cron"）
    2. 呼叫 AgentLoop.run(session_id, job.prompt)
    3. 更新 last_run / next_run
    """
```

### `claw/cron/service.py`

```python
class CronService:
    def __init__(self, store: CronStore, storage: Storage, llm: LLMRouterClient): ...
    async def start(self) -> None:
        """啟動 APScheduler，從 store 載入所有 enabled jobs。"""
    async def stop(self) -> None: ...
    async def add_job(self, session_id: str, schedule: str, prompt: str) -> CronJob: ...
    async def remove_job(self, job_id: str) -> None: ...
    async def list_jobs(self) -> list[CronJob]: ...
```

使用 `apscheduler>=3.10.4`（`AsyncIOScheduler`）。

### `claw/tools/cron.py` — 讓 agent 可以管理排程

```python
@tool(name="cron_add", description="新增排程任務。", requires_main=True, ...)
async def cron_add(schedule: str, prompt: str, session_id: str = "agent:main") -> str:
    """schedule 為 5-field cron 表達式（e.g. '0 9 * * 1-5'）。"""

@tool(name="cron_list", description="列出所有排程任務。", requires_main=True, ...)
async def cron_list() -> str: ...

@tool(name="cron_delete", description="刪除排程任務（by id）。", requires_main=True, ...)
async def cron_delete(job_id: str) -> str: ...
```

---

## P3-6　Multi-agent ACP

### `claw/tools/sessions_tools.py`

```python
@tool(name="sessions_send", requires_main=False, ...)
async def sessions_send(target_session_id: str, message: str) -> str:
    """
    送訊息給另一個 agent session，等待完整回應（同步）。
    實作：直接呼叫 AgentLoop.run(target_session_id, message)，
    收集所有 TextChunk 拼接後回傳。
    """

@tool(name="sessions_spawn", requires_main=False, ...)
async def sessions_spawn(goal: str, agent_id: str = "default") -> str:
    """
    建立新的子 agent session，以 background asyncio.Task 執行 goal。
    回傳新 session_id，parent 可用 sessions_send 查詢結果。
    """

@tool(name="sessions_list", requires_main=True, ...)
async def sessions_list() -> str:
    """列出所有 active sessions（回傳 JSON 字串）。"""
```

### `claw/agent/multi_agent.py`

```python
class MultiAgentCoordinator:
    """管理子 agent 的生命週期與通訊。"""
    def __init__(self, storage: Storage, llm: LLMRouterClient): ...
    async def spawn(self, goal: str, agent_id: str, parent_session_id: str) -> str:
        """建立 cron-scope session，以 asyncio.Task 非同步執行，回傳 child_session_id。"""
    async def send(self, target_session_id: str, message: str) -> str:
        """同步等待 AgentLoop.run() 完成，回傳拼接文字。"""
    async def list_sessions(self) -> list[SessionRow]:
        """回傳所有 active sessions。"""
```

---

## P3-7　Media 基礎處理

### `claw/media/mime.py`

常見 MIME type 判斷（使用 `python-magic` 或 `mimetypes` 標準庫）。

### `claw/media/store.py`

```python
class MediaStore:
    def __init__(self, base_dir: str = "~/.claw/media"): ...
    async def save(self, data: bytes, mime_type: str) -> str:
        """儲存媒體檔案，回傳 local path。"""
    async def load(self, path: str) -> bytes: ...
    async def delete(self, path: str) -> None: ...
```

### `claw/media/input.py`

```python
async def prepare_media_message(
    file_data: bytes,
    mime_type: str,
    store: MediaStore,
    llm_router_url: str,
) -> str:
    """
    將媒體轉換為 agent 可理解的描述：
    - 圖片/PDF：轉 base64，POST 到 LLM-Router /v1/file/generate_content
    - 音訊：轉 base64，POST 到 LLM-Router /v1/audio/transcriptions
    - 其他：儲存到 MediaStore，回傳檔案路徑供 bash tool 處理
    """
```

---

## 新增依賴

在 `pyproject.toml` 新增：

```toml
[project.dependencies]
# 現有 + 以下新增：
"apscheduler>=3.10.4",
"croniter>=2.0.0",

[project.optional-dependencies]
channels = [
    "python-telegram-bot>=21.0",
    "discord.py>=2.3.0",
    "slack-bolt>=1.18.0",
]
```

---

## 測試要求

新增測試（`tests/test_commands.py`、`tests/test_cron.py`、`tests/test_multi_agent.py`）：

### test_commands.py
- `test_command_parse_reset` — `/reset` 正確解析
- `test_command_parse_unknown` — 非 command 字串回傳 None
- `test_command_reset_clears_history` — 執行 `/reset` 後 `storage.get_messages()` 回傳空
- `test_command_history` — `/history 3` 回傳最近 3 條

### test_cron.py
- `test_cron_store_add_list_delete(tmp_path)` — CRUD 完整流程
- `test_cron_next_run` — `next_run_dt("0 9 * * 1-5")` 回傳正確 datetime
- `test_cron_tools_require_main` — `cron_add` tool 在 non-main session 被拒

### test_multi_agent.py
- `test_sessions_send_returns_response(tmp_path)` — 用 FakeLLM 驗證 sessions_send 回傳 TextChunk 拼接
- `test_sessions_spawn_creates_session(tmp_path)` — spawn 後 `storage.list_sessions()` 包含新 session
- `test_sessions_list(tmp_path)` — 回傳 JSON 可 parse 且包含 session_id

---

## 實作順序（建議 Codex 依序執行）

1. **P3-4** `claw/agent/commands.py` + `loop.py` 整合 — 無外部依賴，純邏輯
2. **P3-5** `claw/cron/` + `claw/tools/cron.py` + `pyproject.toml` 更新
3. **P3-6** `claw/agent/multi_agent.py` + `claw/tools/sessions_tools.py`
4. **P3-7** `claw/media/` — 無外部依賴（只用 httpx + mimetypes）
5. **P3-1** `claw/channels/base.py` + `claw/channels/policy.py`
6. **P3-2** `claw/channels/telegram.py`（需先 `pip install python-telegram-bot`）
7. **P3-3** `claw/channels/discord_channel.py`（需先 `pip install discord.py`）
8. `claw/main.py` 整合：啟動時初始化 CronService + 載入 channels

---

## 驗收標準

```bash
python -m pytest tests/ -v
# 預期：原 54 tests + 新增 ~12 tests，全數 PASSED
```

`claw/channels/`、`claw/cron/`、`claw/media/` 三個目錄存在且有 `__init__.py`。

`claw/agent/commands.py` + `claw/tools/sessions_tools.py` + `claw/tools/cron.py` 存在。
