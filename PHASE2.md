# Phase 2 實作計劃書

> 目標：讓系統可以安全隔離、可擴充、可設定。
> 完成後：非 main session 的 tool 執行在 Docker 容器內；Skills 可以插拔（SKILL.md 或 Python class）；
> Hook 可以干預 agent pipeline；Config 從 YAML 讀取；Gateway 連線需要認證。

---

## 依賴關係圖

```
P2-5 Config System
  └── P2-1 Docker Sandbox
  └── P2-4 Security / Auth
  └── P2-2 Hook System
        └── P2-3 Skills Loader
              └── （回頭掛上 Agent Loop + Gateway）
```

P2-5 Config 最先做，因為其他所有模組都要讀設定。
P2-1 和 P2-4 互相獨立，可以平行做。
P2-2 Hook 完成後才做 P2-3 Skills（Skills 透過 Hook 注入）。

---

## P2-5　Config System

**對應 TS 參考：**
- `src/infra/config.ts`
- `src/gateway/auth-mode-policy.ts`

**負責的事：**
- 從 `config/default.yaml` 讀取基礎設定
- `.env` 可覆蓋任何 YAML 值
- 提供全域 `get_config()` singleton
- 驗證必要欄位（LLM_ROUTER_URL 等）

---

### 目錄

```
claw/
└── core/
    └── config.py
config/
└── default.yaml
```

---

### default.yaml 格式

```yaml
# config/default.yaml

gateway:
  host: "127.0.0.1"
  port: 18790
  auth_token: ""           # WebSocket 連線需要帶的 token（空 = 不驗證）

llm_router:
  url: "http://127.0.0.1:8000"
  api_key: ""              # 從 .env 覆蓋

agents:
  default:
    system_prompt: null    # null = 用 DEFAULT_SYSTEM_PROMPT
    queue_mode: "collect"  # collect | followup | drop
    sandbox: false         # main agent 預設不 sandbox
    max_tool_rounds: 8
    prompt_tools: true     # 使用 prompt-based tool calling fallback

sandbox:
  enabled: true
  image: "claw-sandbox:latest"
  workspace_dir: "/workspace"
  timeout: 60              # container 最長存活秒數
  memory_limit: "256m"
  cpu_period: 100000
  cpu_quota: 50000         # 50% CPU

skills:
  dir: "skills"            # 相對於專案根目錄
  autoload: true

storage:
  db_path: "~/.claw/claw.db"
  transcript_dir: "~/.claw/transcripts"

logging:
  level: "INFO"            # DEBUG | INFO | WARNING | ERROR
  format: "json"           # json | text
```

---

### config.py 介面設計

```python
# claw/core/config.py
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any
import yaml
from dotenv import load_dotenv

load_dotenv()

# ── Dataclasses ──────────────────────────────────────────────────────────────

@dataclass
class GatewayConfig:
    host: str = "127.0.0.1"
    port: int = 18790
    auth_token: str = ""

@dataclass
class LLMRouterConfig:
    url: str = "http://127.0.0.1:8000"
    api_key: str = ""

@dataclass
class AgentConfig:
    system_prompt: str | None = None
    queue_mode: str = "collect"
    sandbox: bool = False
    max_tool_rounds: int = 8
    prompt_tools: bool = True

@dataclass
class SandboxConfig:
    enabled: bool = True
    image: str = "claw-sandbox:latest"
    workspace_dir: str = "/workspace"
    timeout: int = 60
    memory_limit: str = "256m"
    cpu_period: int = 100000
    cpu_quota: int = 50000

@dataclass
class SkillsConfig:
    dir: str = "skills"
    autoload: bool = True

@dataclass
class StorageConfig:
    db_path: str = "~/.claw/claw.db"
    transcript_dir: str = "~/.claw/transcripts"

@dataclass
class LoggingConfig:
    level: str = "INFO"
    format: str = "text"

@dataclass
class ClawConfig:
    gateway: GatewayConfig = field(default_factory=GatewayConfig)
    llm_router: LLMRouterConfig = field(default_factory=LLMRouterConfig)
    agents: dict[str, AgentConfig] = field(default_factory=lambda: {"default": AgentConfig()})
    sandbox: SandboxConfig = field(default_factory=SandboxConfig)
    skills: SkillsConfig = field(default_factory=SkillsConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)

    def get_agent(self, agent_id: str) -> AgentConfig:
        return self.agents.get(agent_id) or self.agents.get("default") or AgentConfig()


# ── Loader ────────────────────────────────────────────────────────────────────

_config: ClawConfig | None = None

def load_config(path: str = "config/default.yaml") -> ClawConfig:
    """讀取 YAML + env 覆蓋，回傳 ClawConfig"""
    raw: dict[str, Any] = {}
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}

    # env 覆蓋（扁平化 key，例如 LLM_ROUTER_URL → llm_router.url）
    _apply_env_overrides(raw)

    cfg = ClawConfig(
        gateway=GatewayConfig(**raw.get("gateway", {})),
        llm_router=LLMRouterConfig(**raw.get("llm_router", {})),
        sandbox=SandboxConfig(**raw.get("sandbox", {})),
        skills=SkillsConfig(**raw.get("skills", {})),
        storage=StorageConfig(**raw.get("storage", {})),
        logging=LoggingConfig(**raw.get("logging", {})),
    )
    # agents 是 dict，要逐一轉
    agents_raw = raw.get("agents", {"default": {}})
    cfg.agents = {k: AgentConfig(**v) for k, v in agents_raw.items()}

    return cfg


def get_config() -> ClawConfig:
    """全域 singleton，首次呼叫時載入"""
    global _config
    if _config is None:
        _config = load_config()
    return _config


def _apply_env_overrides(raw: dict) -> None:
    """把特定 env vars 覆蓋到 raw dict"""
    overrides = {
        "LLM_ROUTER_URL":     ("llm_router", "url"),
        "LLM_ROUTER_API_KEY": ("llm_router", "api_key"),
        "CLAW_HOST":          ("gateway", "host"),
        "CLAW_PORT":          ("gateway", "port"),
        "CLAW_AUTH_TOKEN":    ("gateway", "auth_token"),
        "CLAW_DATA_DIR":      None,  # 特殊處理
    }
    for env_key, path in overrides.items():
        val = os.getenv(env_key)
        if val is None or path is None:
            continue
        section, key = path
        raw.setdefault(section, {})[key] = val

    data_dir = os.getenv("CLAW_DATA_DIR")
    if data_dir:
        raw.setdefault("storage", {})["db_path"] = os.path.join(data_dir, "claw.db")
        raw.setdefault("storage", {})["transcript_dir"] = os.path.join(data_dir, "transcripts")
```

---

### TODO 清單

- [ ] `default.yaml` 建立（完整格式）
- [ ] 所有 dataclass（`GatewayConfig`、`LLMRouterConfig` 等）
- [ ] `load_config()` — YAML 解析 + env 覆蓋
- [ ] `get_config()` — singleton
- [ ] `_apply_env_overrides()` — env 對應規則
- [ ] `ClawConfig.get_agent(agent_id)` — fallback to default
- [ ] `main.py` 改用 `get_config()` 替代硬寫的 env 讀取
- [ ] 單元測試：`tests/test_config.py`
  - [ ] 預設值正確
  - [ ] YAML 覆蓋正確
  - [ ] env 覆蓋 YAML
  - [ ] 不存在 YAML 時回傳 default

---

## P2-1　Docker Sandbox

**對應 TS 參考：**
- `src/agents/sandbox/`
- `src/node-host/invoke.ts`
- `src/node-host/exec-policy.ts`

**負責的事：**
- 判斷一個 tool 執行是否需要 sandbox（依 session scope）
- 建立/複用 Docker container（per-session）
- 在 container 內執行 bash 指令
- Container 超時或 session 結束後清理
- `bash` tool 自動路由：main session → host，其他 → sandbox

---

### 目錄

```
claw/
└── sandbox/
    ├── __init__.py
    ├── docker_runner.py
    └── policy.py
docker/
└── sandbox.Dockerfile
```

---

### sandbox.Dockerfile

```dockerfile
# docker/sandbox.Dockerfile
FROM python:3.11-slim

# 基本工具
RUN apt-get update && apt-get install -y \
    bash curl wget git jq unzip \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 工作目錄
WORKDIR /workspace

# 非 root 使用者（安全）
RUN useradd -m -u 1000 sandbox
USER sandbox

CMD ["/bin/bash"]
```

---

### sandbox/policy.py

```python
# claw/sandbox/policy.py
from __future__ import annotations

from claw.core.config import get_config

def needs_sandbox(session_id: str) -> bool:
    """
    判斷這個 session 的 tool 執行是否需要 Docker sandbox。

    規則：
    - main session（session_id == "agent:main" 或 ":main" 結尾）→ host 執行
    - 其他所有 session → sandbox
    - 但如果 config 的 sandbox.enabled = false → 全部 host 執行
    """
    cfg = get_config()
    if not cfg.sandbox.enabled:
        return False

    # main session 走 host
    if session_id == "agent:main" or session_id.endswith(":main"):
        return False

    return True
```

---

### sandbox/docker_runner.py

```python
# claw/sandbox/docker_runner.py
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

import docker
import docker.errors

from claw.core.config import get_config

logger = logging.getLogger(__name__)


@dataclass
class SandboxContainer:
    session_id: str
    container_id: str
    workspace_path: str          # host 上的 workspace 目錄（volume mount）
    created_at: float            # time.time()


class DockerRunner:
    """
    Per-session Docker container 管理。
    每個 session 最多一個 container，重複使用到 session 結束。
    """

    def __init__(self):
        self._client: docker.DockerClient | None = None
        self._containers: dict[str, SandboxContainer] = {}   # session_id → container
        self._lock = asyncio.Lock()

    def _get_client(self) -> docker.DockerClient:
        if self._client is None:
            self._client = docker.from_env()
        return self._client

    async def run(
        self,
        session_id: str,
        command: str,
        timeout: int | None = None,
    ) -> str:
        """
        在 session 對應的 sandbox container 內執行 bash 指令。
        Container 不存在時自動建立。
        回傳 stdout + stderr 合併字串。
        """
        cfg = get_config().sandbox
        effective_timeout = timeout or cfg.timeout

        async with self._lock:
            container = await self._ensure_container(session_id)

        # 在 container 內執行指令（在 executor 中 blocking，避免阻塞 event loop）
        loop = asyncio.get_event_loop()
        result = await asyncio.wait_for(
            loop.run_in_executor(None, self._exec_in_container, container, command),
            timeout=effective_timeout + 5,  # 比指令 timeout 多 5 秒緩衝
        )
        return result

    async def destroy(self, session_id: str) -> None:
        """刪除 session 對應的 container"""
        async with self._lock:
            sandbox = self._containers.pop(session_id, None)
        if sandbox:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None, self._remove_container, sandbox.container_id
            )

    async def destroy_all(self) -> None:
        """清理所有 container（shutdown 時呼叫）"""
        async with self._lock:
            ids = list(self._containers.keys())
        for sid in ids:
            await self.destroy(sid)

    # ── private ──────────────────────────────────────────────────────────────

    async def _ensure_container(self, session_id: str) -> SandboxContainer:
        """如果 container 不存在或已停止，重新建立"""
        existing = self._containers.get(session_id)
        if existing:
            # 確認 container 還活著
            try:
                c = self._get_client().containers.get(existing.container_id)
                if c.status == "running":
                    return existing
            except docker.errors.NotFound:
                pass
            # 已停止或消失，移除記錄重新建立
            self._containers.pop(session_id, None)

        container = await asyncio.get_event_loop().run_in_executor(
            None, self._create_container, session_id
        )
        self._containers[session_id] = container
        return container

    def _create_container(self, session_id: str) -> SandboxContainer:
        import os, time
        cfg = get_config().sandbox
        client = self._get_client()

        # workspace 目錄（host side）
        workspace = os.path.expanduser(
            f"~/.claw/workspaces/{session_id.replace(':', '_')}"
        )
        os.makedirs(workspace, exist_ok=True)

        container = client.containers.run(
            image=cfg.image,
            command="/bin/bash",
            detach=True,
            tty=True,
            stdin_open=True,
            working_dir=cfg.workspace_dir,
            volumes={workspace: {"bind": cfg.workspace_dir, "mode": "rw"}},
            mem_limit=cfg.memory_limit,
            cpu_period=cfg.cpu_period,
            cpu_quota=cfg.cpu_quota,
            network_mode="none",       # 網路隔離
            read_only=False,
            remove=False,              # 手動清理
            labels={"claw.session_id": session_id},
        )
        logger.info(f"sandbox created: {container.short_id} for {session_id}")
        return SandboxContainer(
            session_id=session_id,
            container_id=container.id,
            workspace_path=workspace,
            created_at=time.time(),
        )

    def _exec_in_container(self, sandbox: SandboxContainer, command: str) -> str:
        """Blocking：在 container 內執行指令"""
        cfg = get_config().sandbox
        client = self._get_client()
        try:
            container = client.containers.get(sandbox.container_id)
            result = container.exec_run(
                cmd=["bash", "-c", command],
                workdir=cfg.workspace_dir,
                demux=False,
                user="sandbox",
            )
            output = (result.output or b"").decode("utf-8", errors="replace")
            exit_code = result.exit_code
            if exit_code != 0:
                return f"[exit {exit_code}]\n{output}"
            return output
        except docker.errors.NotFound:
            return "Error: container not found"
        except Exception as e:
            return f"Error: {e}"

    def _remove_container(self, container_id: str) -> None:
        try:
            c = self._get_client().containers.get(container_id)
            c.stop(timeout=3)
            c.remove(force=True)
            logger.info(f"sandbox removed: {container_id[:12]}")
        except docker.errors.NotFound:
            pass
        except Exception as e:
            logger.warning(f"sandbox remove error: {e}")


# 全域 runner singleton
_runner: DockerRunner | None = None

def get_runner() -> DockerRunner:
    global _runner
    if _runner is None:
        _runner = DockerRunner()
    return _runner
```

---

### bash tool 更新（加入 sandbox routing）

```python
# claw/tools/bash.py（更新版）
import asyncio
from .registry import tool

@tool(
    name="bash",
    description="執行 bash 指令。main session 在 host 執行；其他 session 在 Docker sandbox 執行。",
    parameters={
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "要執行的 bash 指令"},
            "timeout": {"type": "integer", "description": "逾時秒數，預設 30", "default": 30},
        },
        "required": ["command"],
    },
    requires_main=False,   # sandbox 後開放給所有 session
)
async def bash_tool(command: str, timeout: int = 30) -> str:
    # session_id 由 execute() 時注入（見 registry.py 更新）
    # 這裡直接 host 執行，sandbox routing 在 registry.execute() 層處理
    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        output = stdout.decode("utf-8", errors="replace")
        if proc.returncode != 0:
            return f"[exit {proc.returncode}]\n{output}"
        return output
    except asyncio.TimeoutError:
        return f"Error: command timed out after {timeout}s"
    except Exception as e:
        return f"Error: {e}"
```

---

### registry.py 更新（sandbox routing）

```python
# claw/tools/registry.py — execute() 更新版

async def execute(
    name: str,
    arguments: dict,
    session_id: str = "agent:main",      # ← 新增
    session_is_main: bool = False,
) -> str:
    """
    執行 tool。
    如果 sandbox policy 說這個 session 需要 sandbox，
    且 tool 是 "bash"，則路由到 DockerRunner。
    """
    from claw.sandbox.policy import needs_sandbox

    spec = _registry.get(name)
    if spec is None:
        return f"Error: unknown tool '{name}'"

    # sandbox routing：bash tool 在非 main session 走 Docker
    if name == "bash" and needs_sandbox(session_id):
        from claw.sandbox.docker_runner import get_runner
        command = arguments.get("command", "")
        timeout = arguments.get("timeout", 30)
        return await get_runner().run(session_id, command, timeout=timeout)

    # 原有邏輯（host 執行）
    if spec.requires_main and not session_is_main:
        return f"Error: tool '{name}' requires main session"
    try:
        result = await spec.handler(**arguments)
        return str(result)
    except Exception as e:
        return f"Error: {e}"
```

> 注意：`loop.py` 的 `tool_registry.execute()` 呼叫也要傳入 `session_id`：
> ```python
> result = await tool_registry.execute(
>     tc_name, tc_args,
>     session_id=session_id,       # ← 新增
>     session_is_main=is_main
> )
> ```

---

### TODO 清單

- [ ] `docker/sandbox.Dockerfile` — 建立 sandbox image
- [ ] `docker build -t claw-sandbox:latest -f docker/sandbox.Dockerfile .` — 建立 image
- [ ] `sandbox/policy.py` — `needs_sandbox(session_id)`
- [ ] `sandbox/docker_runner.py`
  - [ ] `DockerRunner.__init__()`
  - [ ] `DockerRunner.run()` — async wrapper
  - [ ] `DockerRunner._ensure_container()` — 存活確認 + 重建
  - [ ] `DockerRunner._create_container()` — volume、資源限制、network=none
  - [ ] `DockerRunner._exec_in_container()` — `container.exec_run()`
  - [ ] `DockerRunner._remove_container()` — stop + remove
  - [ ] `DockerRunner.destroy(session_id)` — 清理單一 session
  - [ ] `DockerRunner.destroy_all()` — shutdown hook
  - [ ] `get_runner()` singleton
- [ ] `tools/registry.py` — `execute()` 加入 `session_id` 參數 + sandbox routing
- [ ] `tools/bash.py` — 移除 `requires_main=True`（sandbox 後全部開放）
- [ ] `agent/loop.py` — `execute()` 呼叫加 `session_id=session_id`
- [ ] `main.py` — lifespan 加入 `runner.destroy_all()` cleanup
- [ ] 單元測試：`tests/test_sandbox.py`
  - [ ] `needs_sandbox("agent:main")` → False
  - [ ] `needs_sandbox("agent:telegram:group:123")` → True
  - [ ] `needs_sandbox(...)` 當 `sandbox.enabled=false` → False
  - [ ] `DockerRunner.run()` mock docker client，確認 exec_run 被呼叫
  - [ ] sandbox routing：非 main session 的 bash 執行走 DockerRunner
- [ ] 整合測試：建立 non-main session，呼叫 bash tool，確認在 container 內執行

---

## P2-2　Hook System

**對應 TS 參考：**
- `src/hooks/hooks.ts`
- `src/hooks/types.ts`
- `src/hooks/loader.ts`

**負責的事：**
- Hook 注冊（skills 或外部程式碼可以 register hook）
- Agent Loop 的 lifecycle 中 fire 對應 hook
- Hook 回傳值可以修改 pipeline 行為（例如修改 system prompt、攔截訊息）

---

### 目錄

```
claw/
└── agent/
    └── hooks.py
```

---

### Hook Event 清單

| Hook 名稱 | 觸發時機 | 輸入 | 可修改回傳 |
|---|---|---|---|
| `before_prompt_build` | 組裝 system prompt 前 | `session_id`, `base_prompt` | 回傳新的 `system_prompt` 字串 |
| `after_user_message` | user 訊息進入後，LLM 呼叫前 | `session_id`, `message` | 回傳修改過的 `message`（或 None 保持原樣） |
| `after_tool_call` | 每個 tool 執行完後 | `session_id`, `tool_name`, `arguments`, `result` | 回傳修改過的 `result`（或 None 保持原樣） |
| `before_send` | LLM 回覆要送出前 | `session_id`, `content` | 回傳修改過的 `content`（或 None 保持原樣） |
| `on_run_complete` | 整個 agent run 結束 | `session_id`, `full_content`, `usage` | 無（純通知） |
| `on_run_error` | agent run 發生錯誤 | `session_id`, `error` | 無（純通知） |
| `on_session_create` | 新 session 被建立 | `session_id`, `scope` | 無 |
| `on_session_delete` | session 被刪除 | `session_id` | 無 |

---

### hooks.py 介面設計

```python
# claw/agent/hooks.py
from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Awaitable

logger = logging.getLogger(__name__)

# Hook handler 型別
# 同步或非同步都支援
HookHandler = Callable[..., Any | Awaitable[Any]]


class HookRegistry:
    """
    全域 hook registry。
    Skills 和外部程式碼可以 register handler。
    AgentLoop 在適當時機 fire。
    """

    def __init__(self):
        self._handlers: dict[str, list[HookHandler]] = {}

    def register(self, event: str, handler: HookHandler) -> None:
        """注冊一個 hook handler"""
        self._handlers.setdefault(event, []).append(handler)

    def unregister(self, event: str, handler: HookHandler) -> None:
        handlers = self._handlers.get(event, [])
        if handler in handlers:
            handlers.remove(handler)

    async def fire(self, event: str, **kwargs) -> Any:
        """
        觸發 event，依序執行所有 handler。

        對於「可修改」的 hook（before_prompt_build 等）：
          - handler 回傳非 None 時，更新對應的值
          - 最後回傳最終值（若沒有 handler 修改，回傳原始值）

        對於「純通知」的 hook（on_run_complete 等）：
          - 忽略回傳值
        """
        handlers = self._handlers.get(event, [])
        if not handlers:
            return kwargs.get(_modifiable_key(event))

        current_value = kwargs.get(_modifiable_key(event))

        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    result = await handler(**kwargs)
                else:
                    result = handler(**kwargs)

                # 可修改的 hook：handler 回傳 non-None 時更新
                if result is not None and _modifiable_key(event):
                    current_value = result
                    # 更新 kwargs 讓下一個 handler 看到更新後的值
                    kwargs[_modifiable_key(event)] = current_value

            except Exception as e:
                logger.warning(f"hook '{event}' handler error: {e}")

        return current_value

    def clear(self) -> None:
        """清除所有 handler（測試用）"""
        self._handlers.clear()


# 哪些 hook 有可修改的回傳值，以及對應的 kwargs key
_MODIFIABLE_HOOKS = {
    "before_prompt_build": "base_prompt",
    "after_user_message":  "message",
    "after_tool_call":     "result",
    "before_send":         "content",
}

def _modifiable_key(event: str) -> str | None:
    return _MODIFIABLE_HOOKS.get(event)


# 全域 singleton
_registry: HookRegistry | None = None

def get_hooks() -> HookRegistry:
    global _registry
    if _registry is None:
        _registry = HookRegistry()
    return _registry
```

---

### AgentLoop 更新（fire hooks）

在 `loop.py` 的對應位置加入 hook 呼叫：

```python
# claw/agent/loop.py — 在適當位置加入

from claw.agent.hooks import get_hooks

# 1. before_prompt_build — 在組裝 system prompt 前
sys_prompt = await get_hooks().fire(
    "before_prompt_build",
    session_id=session_id,
    base_prompt=effective_sys_prompt,
) or effective_sys_prompt

# 2. after_user_message — user 訊息進入後
user_message = await get_hooks().fire(
    "after_user_message",
    session_id=session_id,
    message=user_message,
) or user_message

# 3. after_tool_call — 每個 tool 執行完後
result = await get_hooks().fire(
    "after_tool_call",
    session_id=session_id,
    tool_name=tc_name,
    arguments=tc_args,
    result=result,
) or result

# 4. before_send — 最終回覆送出前
final_content = await get_hooks().fire(
    "before_send",
    session_id=session_id,
    content=full_content,
) or full_content

# 5. on_run_complete — run 結束（純通知，不用接回傳值）
await get_hooks().fire(
    "on_run_complete",
    session_id=session_id,
    full_content=full_content,
    usage=usage,
)

# 6. on_run_error — 發生錯誤
await get_hooks().fire(
    "on_run_error",
    session_id=session_id,
    error=str(e),
)
```

---

### Hook 使用範例（之後 Skill 會這樣掛）

```python
from claw.agent.hooks import get_hooks

# 在 system prompt 後面附加 skill 的 prompt
async def my_skill_prompt(session_id: str, base_prompt: str) -> str:
    return base_prompt + "\n\nYou are also an expert Python programmer."

get_hooks().register("before_prompt_build", my_skill_prompt)

# 把 tool 結果寫進 log
async def log_tool_call(session_id, tool_name, arguments, result):
    print(f"[TOOL] {tool_name}({arguments}) → {result[:100]}")
    return None  # 不修改結果

get_hooks().register("after_tool_call", log_tool_call)
```

---

### TODO 清單

- [ ] `agent/hooks.py`
  - [ ] `HookRegistry.__init__()`
  - [ ] `HookRegistry.register()`
  - [ ] `HookRegistry.unregister()`
  - [ ] `HookRegistry.fire()` — 依序執行 + 可修改值傳遞
  - [ ] 同步 handler 支援（`asyncio.iscoroutinefunction` 判斷）
  - [ ] Handler 錯誤不能讓整個 fire() 崩掉（try/except + warning log）
  - [ ] `_MODIFIABLE_HOOKS` 對應表
  - [ ] `get_hooks()` singleton
  - [ ] `HookRegistry.clear()` 測試用
- [ ] `agent/loop.py` — 加入 6 個 hook fire 點
- [ ] 單元測試：`tests/test_hooks.py`
  - [ ] register + fire 正確呼叫 handler
  - [ ] 可修改 hook：handler 回傳值被採用
  - [ ] 可修改 hook：handler 回傳 None 保持原值
  - [ ] 多個 handler 串聯（第一個修改，第二個繼續修改）
  - [ ] Handler 拋錯不影響其他 handler
  - [ ] 同步 handler 正常執行
  - [ ] 無 handler 時 fire() 回傳原始值

---

## P2-3　Skills Loader

**對應 TS 參考：**
- `src/plugins/loader.ts`
- `src/plugins/discovery.ts`
- `src/plugins/manifest.ts`
- `src/plugin-sdk/core.ts`
- `src/agents/skills/`

**負責的事：**
- 從 `skills/` 目錄掃描並載入 skill
- Skill 可以是 Python class（程式碼型）或 SKILL.md（純 prompt 型）
- Skill 可以注冊 tools 和 hooks
- Gating 檢查：missing binary 或 env var 時跳過 skill

### Skills 架構決策（OpenClaw 相容）

claw-python 的 Skills 採用與 OpenClaw 相同的 **SKILL.md 為主** 架構：

- Skills 目錄（`skills/<name>/SKILL.md`）存放 **宣告式** 的 skill 定義
- SKILL.md frontmatter 使用 `metadata.openclaw.*` 格式（與 OpenClaw 52 個 skill 相容）
- Python built-in tools（如 `search_web`, `bash`）放在 `claw/tools/` 目錄，不在 skills 目錄
- SKILL.md 的 body 內容透過 `before_prompt_build` hook 注入 system prompt

**SKILL.md frontmatter 格式（OpenClaw 相容）：**
```yaml
---
name: <skill-name>
description: <one-line description>
homepage: ""
metadata:
  openclaw:
    emoji: <emoji>
    requires:
      anyBins: []   # 至少有一個即可
      allBins: []   # 全部都要有
    install: ""     # 安裝指令（供文件用，不自動執行）
---
```

---

### 目錄

```
claw/
└── skills/
    ├── __init__.py
    ├── base.py
    ├── manifest.py
    ├── loader.py
    └── registry.py
skills/                    ← 使用者的 skill 放這裡
└── example/
    ├── SKILL.md
    └── __init__.py        （可選）
```

---

### SKILL.md 格式

```markdown
---
name: example
description: 這是一個範例 skill
version: "1.0"
requires:
  bins: []              # 需要的可執行檔（如 ["ffmpeg", "git"]）
  env: []               # 需要的 env var（如 ["OPENAI_API_KEY"]）
  python: []            # 需要的 Python 套件（如 ["requests"]）
hooks:
  before_prompt_build: true   # 這個 skill 有 before_prompt_build hook
---

你是一個範例助理。在回答時請保持簡潔。

## 特殊規則

- 每次回答都要以「好的」開頭
- 不要使用列表
```

SKILL.md 的 frontmatter 以下的內容（去掉 `---` 之後）= 注入 system prompt 的文字。

---

### skills/base.py

```python
# claw/skills/base.py
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable, Awaitable


@dataclass
class SkillRequirements:
    bins: list[str] = field(default_factory=list)
    env: list[str] = field(default_factory=list)
    python: list[str] = field(default_factory=list)


@dataclass
class SkillManifest:
    name: str
    description: str = ""
    version: str = "1.0"
    requires: SkillRequirements = field(default_factory=SkillRequirements)


class AbstractSkill(ABC):
    """
    Python class-based skill 的基底類別。
    繼承這個 class，覆寫需要的方法。
    """

    @property
    @abstractmethod
    def manifest(self) -> SkillManifest:
        """回傳 skill 的 metadata"""
        ...

    @property
    def system_prompt(self) -> str | None:
        """注入 system prompt 的文字；None = 不注入"""
        return None

    @property
    def tools(self) -> list:
        """
        這個 skill 提供的 tools。
        每個元素是一個 async function，已用 @tool 裝飾。
        回傳空 list = 不提供 tools。
        """
        return []

    def register_hooks(self) -> None:
        """
        在這裡呼叫 get_hooks().register(...)。
        Loader 載入 skill 時會呼叫這個方法。
        """
        pass

    def on_load(self) -> None:
        """Skill 被載入時呼叫"""
        pass

    def on_unload(self) -> None:
        """Skill 被卸載時呼叫"""
        pass
```

---

### skills/manifest.py

```python
# claw/skills/manifest.py
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
import yaml

from claw.skills.base import SkillManifest, SkillRequirements

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)", re.DOTALL)


@dataclass
class ParsedSkillMd:
    manifest: SkillManifest
    prompt: str


def parse_skill_md(content: str) -> ParsedSkillMd:
    """解析 SKILL.md 的 frontmatter + prompt body"""
    match = _FRONTMATTER_RE.match(content)
    if not match:
        # 沒有 frontmatter：整個內容當 prompt，name 設為 "unnamed"
        return ParsedSkillMd(
            manifest=SkillManifest(name="unnamed"),
            prompt=content.strip(),
        )

    frontmatter_raw, body = match.group(1), match.group(2)
    try:
        meta: dict[str, Any] = yaml.safe_load(frontmatter_raw) or {}
    except yaml.YAMLError:
        meta = {}

    requires_raw = meta.get("requires", {})
    requires = SkillRequirements(
        bins=requires_raw.get("bins", []),
        env=requires_raw.get("env", []),
        python=requires_raw.get("python", []),
    )

    manifest = SkillManifest(
        name=meta.get("name", "unnamed"),
        description=meta.get("description", ""),
        version=str(meta.get("version", "1.0")),
        requires=requires,
    )

    return ParsedSkillMd(manifest=manifest, prompt=body.strip())
```

---

### skills/loader.py

```python
# claw/skills/loader.py
from __future__ import annotations

import importlib.util
import logging
import os
import shutil

from claw.skills.base import AbstractSkill, SkillRequirements
from claw.skills.manifest import parse_skill_md
from claw.skills.registry import SkillRegistry

logger = logging.getLogger(__name__)


def check_requirements(req: SkillRequirements) -> list[str]:
    """
    檢查 skill 的依賴是否滿足。
    回傳 missing items 的 list，空 list = 全部滿足。
    """
    missing = []
    for b in req.bins:
        if shutil.which(b) is None:
            missing.append(f"bin:{b}")
    for e in req.env:
        if not os.getenv(e):
            missing.append(f"env:{e}")
    for p in req.python:
        try:
            importlib.import_module(p)
        except ImportError:
            missing.append(f"python:{p}")
    return missing


def load_skills(skills_dir: str) -> SkillRegistry:
    """
    掃描 skills_dir，載入所有 skill。
    回傳已初始化的 SkillRegistry。
    """
    registry = SkillRegistry()

    if not os.path.isdir(skills_dir):
        logger.debug(f"skills dir not found: {skills_dir}")
        return registry

    for entry in sorted(os.listdir(skills_dir)):
        skill_path = os.path.join(skills_dir, entry)

        # 掃描子目錄
        if os.path.isdir(skill_path):
            # 優先 Python class（__init__.py 內有繼承 AbstractSkill 的 class）
            init_py = os.path.join(skill_path, "__init__.py")
            skill_md = os.path.join(skill_path, "SKILL.md")

            if os.path.exists(init_py):
                _load_python_skill(init_py, entry, registry)
            elif os.path.exists(skill_md):
                _load_md_skill(skill_md, entry, registry)

        # 單一 SKILL.md 在 skills/ 根目錄
        elif entry.endswith(".md"):
            _load_md_skill(skill_path, entry[:-3], registry)

    logger.info(f"loaded {len(registry.all())} skills from {skills_dir}")
    return registry


def _load_python_skill(path: str, name: str, registry: SkillRegistry) -> None:
    """載入 Python class-based skill"""
    try:
        spec = importlib.util.spec_from_file_location(f"skills.{name}", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # 找到繼承 AbstractSkill 的 class
        skill_cls = None
        for attr_name in dir(module):
            obj = getattr(module, attr_name)
            if (isinstance(obj, type)
                    and issubclass(obj, AbstractSkill)
                    and obj is not AbstractSkill):
                skill_cls = obj
                break

        if skill_cls is None:
            logger.warning(f"skill {name}: no AbstractSkill subclass found in {path}")
            return

        skill = skill_cls()

        # Gating 檢查
        missing = check_requirements(skill.manifest.requires)
        if missing:
            logger.info(f"skill '{skill.manifest.name}' skipped (missing: {missing})")
            return

        registry.register(skill)
        skill.on_load()
        skill.register_hooks()
        logger.info(f"skill loaded: {skill.manifest.name} (python)")

    except Exception as e:
        logger.warning(f"skill {name}: load error: {e}")


def _load_md_skill(path: str, name: str, registry: SkillRegistry) -> None:
    """載入 SKILL.md prompt-only skill"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()

        parsed = parse_skill_md(content)

        # Gating 檢查
        missing = check_requirements(parsed.manifest.requires)
        if missing:
            logger.info(f"skill '{parsed.manifest.name}' skipped (missing: {missing})")
            return

        # Prompt-only skill 包成 PromptSkill
        skill = _PromptSkill(parsed.manifest, parsed.prompt)
        registry.register(skill)

        # 把 prompt 注入 hook
        if parsed.prompt:
            from claw.agent.hooks import get_hooks
            _register_prompt_hook(parsed.manifest.name, parsed.prompt)

        logger.info(f"skill loaded: {parsed.manifest.name} (md)")

    except Exception as e:
        logger.warning(f"skill {name}: md load error: {e}")


def _register_prompt_hook(skill_name: str, prompt: str) -> None:
    """把 skill 的 prompt 注冊到 before_prompt_build hook"""
    from claw.agent.hooks import get_hooks

    async def inject_prompt(session_id: str, base_prompt: str) -> str:
        separator = "\n\n---\n\n"
        return base_prompt + separator + f"# Skill: {skill_name}\n\n{prompt}"

    get_hooks().register("before_prompt_build", inject_prompt)


class _PromptSkill(AbstractSkill):
    """SKILL.md 載入後包裝成這個 class"""
    def __init__(self, mf, prompt: str):
        self._manifest = mf
        self._prompt = prompt

    @property
    def manifest(self):
        return self._manifest

    @property
    def system_prompt(self) -> str:
        return self._prompt
```

---

### skills/registry.py

```python
# claw/skills/registry.py
from __future__ import annotations

from claw.skills.base import AbstractSkill


class SkillRegistry:
    def __init__(self):
        self._skills: dict[str, AbstractSkill] = {}

    def register(self, skill: AbstractSkill) -> None:
        name = skill.manifest.name
        self._skills[name] = skill
        # 注冊 skill 的 tools
        for tool_fn in skill.tools:
            pass  # tools 已透過 @tool 裝飾器自動注冊到 tool_registry

    def get(self, name: str) -> AbstractSkill | None:
        return self._skills.get(name)

    def all(self) -> list[AbstractSkill]:
        return list(self._skills.values())

    def unload(self, name: str) -> None:
        skill = self._skills.pop(name, None)
        if skill:
            skill.on_unload()
```

---

### Skill 範例

```python
# skills/search/__init__.py
from claw.skills.base import AbstractSkill, SkillManifest, SkillRequirements
from claw.tools.registry import tool
from claw.agent.hooks import get_hooks


@tool(
    name="search_web",
    description="用 DDGS 搜尋網路，回傳前 5 個結果",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜尋關鍵字"},
        },
        "required": ["query"],
    },
)
async def search_web_tool(query: str) -> str:
    import httpx, os
    from claw.core.config import get_config
    cfg = get_config()
    # 透過 LLM-Router 的 DDGS endpoint
    resp = await httpx.AsyncClient().post(
        f"{cfg.llm_router.url}/v1/search",
        json={"query": query, "max_results": 5},
        headers={"Authorization": f"Bearer {cfg.llm_router.api_key}"},
        timeout=15.0,
    )
    data = resp.json()
    results = data.get("results", [])
    return "\n\n".join(
        f"[{i+1}] {r.get('title')}\n{r.get('href')}\n{r.get('body','')}"
        for i, r in enumerate(results)
    )


class SearchSkill(AbstractSkill):
    @property
    def manifest(self) -> SkillManifest:
        return SkillManifest(
            name="search",
            description="網路搜尋 skill（透過 LLM-Router DDGS）",
        )

    @property
    def system_prompt(self) -> str:
        return (
            "You can search the web using the search_web tool. "
            "Always cite your sources when using search results."
        )

    @property
    def tools(self) -> list:
        return [search_web_tool]
```

---

### TODO 清單

- [ ] `skills/base.py` — `AbstractSkill`, `SkillManifest`, `SkillRequirements`
- [ ] `skills/manifest.py`
  - [ ] `_FRONTMATTER_RE` regex
  - [ ] `parse_skill_md()` — frontmatter + body 分離
  - [ ] 無 frontmatter 的 fallback 處理
- [ ] `skills/loader.py`
  - [ ] `check_requirements()` — bins / env / python 檢查
  - [ ] `load_skills()` — 掃描目錄
  - [ ] `_load_python_skill()` — importlib 動態載入
  - [ ] `_load_md_skill()` — 解析 SKILL.md
  - [ ] `_register_prompt_hook()` — 注冊 before_prompt_build hook
  - [ ] `_PromptSkill` wrapper class
- [ ] `skills/registry.py` — `SkillRegistry`
- [ ] `main.py` — 啟動時 `load_skills(cfg.skills.dir)`
- [ ] `skills/` 目錄建立 + `.gitkeep`
- [ ] 內建 skill：`skills/search/__init__.py`
- [ ] 單元測試：`tests/test_skills.py`
  - [ ] `parse_skill_md()` — 有/無 frontmatter
  - [ ] `check_requirements()` — bin 存在/不存在
  - [ ] `load_skills()` — 掃描 tmp 目錄，正確載入 md + python skill
  - [ ] Gating：missing bin → skill 被跳過
  - [ ] Prompt hook 注冊後 `fire("before_prompt_build")` 有效果
  - [ ] Python skill tools 被注冊到 tool registry

---

## P2-4　Security / Auth

**對應 TS 參考：**
- `src/gateway/auth.ts`
- `src/gateway/auth-mode-policy.ts`
- `src/pairing/pairing-challenge.ts`
- `src/security/dm-policy-shared.ts`

**負責的事：**
- Gateway WebSocket 連線認證（token 驗證）
- 白名單（allowFrom）：哪些 user/peer 可以傳訊息
- DM Pairing：未知使用者需要先配對
- `core/auth.py` 集中管理認證邏輯

---

### 目錄

```
claw/
└── core/
    ├── auth.py
    └── pairing.py
```

---

### core/auth.py

```python
# claw/core/auth.py
from __future__ import annotations

import hashlib
import hmac
import logging
from fastapi import WebSocket

from claw.core.config import get_config

logger = logging.getLogger(__name__)


def verify_gateway_token(token: str) -> bool:
    """
    驗證 WebSocket 連線的 auth token。
    config.gateway.auth_token 為空 → 不驗證（開發模式）。
    """
    expected = get_config().gateway.auth_token
    if not expected:
        return True   # 無設定 = 開放
    if not token:
        return False
    # constant-time compare 防 timing attack
    return hmac.compare_digest(expected.encode(), token.encode())


async def ws_auth_middleware(ws: WebSocket, token: str) -> bool:
    """
    WebSocket 連線認證。
    失敗時關閉連線，回傳 False。
    """
    if not verify_gateway_token(token):
        logger.warning(f"ws auth failed from {ws.client}")
        await ws.close(code=4003)
        return False
    return True
```

---

### core/pairing.py

```python
# claw/core/pairing.py
from __future__ import annotations

import random
import time
from dataclasses import dataclass

# 配對碼有效期（秒）
PAIRING_CODE_TTL = 300   # 5 分鐘

@dataclass
class PairingEntry:
    code: str
    created_at: float
    peer_id: str | None = None   # 已配對的 peer

_pending: dict[str, PairingEntry] = {}   # session_id → PairingEntry
_paired: set[str] = set()                # 已配對的 peer_id

def generate_code(session_id: str) -> str:
    """產生一個 6 位數配對碼，並暫存"""
    code = str(random.randint(100000, 999999))
    _pending[session_id] = PairingEntry(code=code, created_at=time.time())
    return code

def verify_code(session_id: str, code: str, peer_id: str) -> bool:
    """驗證配對碼，成功後把 peer_id 加入已配對集合"""
    entry = _pending.get(session_id)
    if not entry:
        return False
    if time.time() - entry.created_at > PAIRING_CODE_TTL:
        _pending.pop(session_id, None)
        return False
    if entry.code != code:
        return False
    _paired.add(peer_id)
    _pending.pop(session_id, None)
    return True

def is_paired(peer_id: str) -> bool:
    return peer_id in _paired

def unpair(peer_id: str) -> None:
    _paired.discard(peer_id)
```

---

### Gateway 更新（加入 auth）

```python
# claw/core/gateway.py — ws_endpoint 更新
from claw.core.auth import ws_auth_middleware

@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()

    # 第一幀：connect + auth
    raw = await ws.receive_json()
    if raw.get("type") != "connect":
        await ws.close(code=4001)
        return

    token = raw.get("token", "")
    if not await ws_auth_middleware(ws, token):
        return   # ws_auth_middleware 已關閉連線

    # ... 其餘不變
```

---

### TODO 清單

- [ ] `core/auth.py`
  - [ ] `verify_gateway_token()` — hmac.compare_digest
  - [ ] `ws_auth_middleware()` — close(4003) on fail
- [ ] `core/pairing.py`
  - [ ] `generate_code()` — 6 位數 + TTL 暫存
  - [ ] `verify_code()` — TTL 檢查 + code 比對 + 加入 paired set
  - [ ] `is_paired(peer_id)`
  - [ ] `unpair(peer_id)`
- [ ] `core/gateway.py` — connect frame 加入 token 驗證
- [ ] 單元測試：`tests/test_auth.py`
  - [ ] 空 token config → 全部通過
  - [ ] 正確 token → 通過
  - [ ] 錯誤 token → 失敗
  - [ ] pairing code 生成 + 驗證成功
  - [ ] pairing code 過期 → 失敗
  - [ ] 錯誤 code → 失敗

---

## Phase 2 完整 TODO（彙整）

```
[ ] P2-5  config/default.yaml
[ ] P2-5  claw/core/config.py
[ ] P2-5  tests/test_config.py
[ ] P2-5  claw/main.py 改用 get_config()

[ ] P2-1  docker/sandbox.Dockerfile
[ ] P2-1  docker build -t claw-sandbox:latest
[ ] P2-1  claw/sandbox/__init__.py
[ ] P2-1  claw/sandbox/policy.py
[ ] P2-1  claw/sandbox/docker_runner.py
[ ] P2-1  claw/tools/registry.py（加 session_id + sandbox routing）
[ ] P2-1  claw/tools/bash.py（移除 requires_main）
[ ] P2-1  claw/agent/loop.py（execute() 加 session_id）
[ ] P2-1  claw/main.py（lifespan 加 destroy_all）
[ ] P2-1  tests/test_sandbox.py

[ ] P2-2  claw/agent/hooks.py
[ ] P2-2  claw/agent/loop.py（加入 6 個 hook fire 點）
[ ] P2-2  tests/test_hooks.py

[ ] P2-3  claw/skills/__init__.py
[ ] P2-3  claw/skills/base.py
[ ] P2-3  claw/skills/manifest.py
[ ] P2-3  claw/skills/loader.py
[ ] P2-3  claw/skills/registry.py
[ ] P2-3  skills/.gitkeep
[ ] P2-3  skills/search/__init__.py（範例 skill）
[ ] P2-3  claw/main.py（啟動時 load_skills）
[ ] P2-3  tests/test_skills.py

[ ] P2-4  claw/core/auth.py
[ ] P2-4  claw/core/pairing.py
[ ] P2-4  claw/core/gateway.py（connect frame auth）
[ ] P2-4  tests/test_auth.py

[ ] end-to-end 測試：
    [ ] non-main session 的 bash tool 在 container 內執行
    [ ] SKILL.md skill 的 prompt 注入 system prompt 有效
    [ ] before_prompt_build hook 修改 prompt 有效
    [ ] auth token 設定後 WebSocket 需要帶 token
```

---

## 新增的依賴

```toml
# pyproject.toml 新增
dependencies = [
    # Phase 2 新增
    "docker>=7.0.0",           # sandbox Docker client
    "pyyaml>=6.0",             # config YAML（Phase 1 已有）
    "watchdog>=4.0.0",         # skills hot reload（可選）
]
```

安裝：
```bash
pip install docker watchdog
```

確認 Docker daemon 在跑：
```bash
docker info
```

建立 sandbox image：
```bash
docker build -t claw-sandbox:latest -f docker/sandbox.Dockerfile .
```

---

## 注意事項

1. **P2-5 Config 一定最先做** — 其他所有模組的初始化都依賴它。`main.py` 要先改用 `get_config()`。

2. **Docker client 是 blocking** — `docker-py` 所有操作都是 sync，要包在 `loop.run_in_executor(None, ...)` 裡，否則會 block asyncio event loop。

3. **sandbox image 要先 build** — `docker_runner.py` 的測試前需要 `claw-sandbox:latest` image 存在。整合測試需要 Docker daemon 在跑。

4. **Skills loader 的 import** — 用 `importlib.util.spec_from_file_location` 動態載入，skill 的 `@tool` 裝飾器在 import 時就會執行，tool 會自動注冊到 `tool_registry._registry`。

5. **Hook 的 error isolation** — 任何一個 hook handler 崩掉都不能影響 agent pipeline。`fire()` 的 try/except 是必要的。

6. **Gateway auth 的 backward compatibility** — `auth_token` 空字串 = 不驗證，這樣 Phase 1 的測試不需要改動。
