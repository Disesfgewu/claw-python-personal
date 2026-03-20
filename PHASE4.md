# Phase 4 實作計劃書 — NemoClaw 安全層

> **目標：** 將 NemoClaw 的企業安全設計移植到 claw-python，針對 Jetson Orin Nano Super（JetPack 6.x / kernel 5.15.136-tegra / 8GB unified memory）最佳化。
>
> **定位：** NemoClaw = 圍繞 Agent 的企業安全容器。claw-python 引入其三層設計：Blueprint 完整性驗證、Network Egress 白名單審批、Sandbox 強化隔離。
>
> **前提：** Phase 3 完成，64 tests 通過。
>
> **硬體上下文：**
> - 設備：Jetson Orin Nano Super（Tegra kernel 5.15.136）
> - 記憶體：8GB unified memory，MemAvailable ≈ 1.9GB（runtime 用）
> - LLM：全部交給 LLM-Router，本機零推論 → 記憶體預算充裕
> - Docker：`network_mode="none"` 已啟用（比 NemoClaw 原版更乾淨，繞開 nf_tables panic）
>
> **NemoClaw 原版不適用的部分（本 Phase 跳過）：**
> - k3s / Kubernetes deployment（iptables kernel panic on Tegra）
> - Landlock LSM（kernel 5.15-tegra 未啟用，保留為選用）
> - Nemotron / NIM 本地推論（LLM-Router 已全包）
> - GPU 偵測（統一記憶體架構，nvidia-smi 回傳 N/A）

---

## 現況 vs 目標（差距分析）

| 功能 | 現況 | Phase 4 目標 |
|---|---|---|
| Container 網路隔離 | `network_mode="none"` ✅ | 維持不變 |
| Container 記憶體限制 | `mem_limit=256m`（config） | Blueprint 統一管理，升到 400m |
| Container CPU 限制 | cpu_period/cpu_quota | 改用 `--cpus`（更直觀） |
| Container 檔案系統 | `read_only=False` ❌ | `read_only=True` + tmpfs |
| Container 用戶 | `user="sandbox"`（可能不存在） | `user="nobody"`（標準） |
| Seccomp profile | 無 ❌ | `seccomp_minimal.json` |
| no-new-privileges | 無 ❌ | 啟用 |
| Blueprint 驗證 | 無 ❌ | sha256 完整性 + 記憶體 preflight |
| Egress 白名單 | 無 ❌ | YAML 規則 + DENY/ALLOW/PENDING |
| Egress 稽核日誌 | 無 ❌ | `egress_audit_log` SQLite 表 |
| Egress 審批流 | 無 ❌ | Admin API + 動態白名單更新 |
| Agent 層 Egress 攔截 | 無 ❌ | loop.py tool dispatch 4 行 |

---

## P4-1　Blueprint 完整性驗證層（純新增，零破壞性）

### `config/blueprint.py`

```python
import hashlib
import yaml
from dataclasses import dataclass
from pathlib import Path

@dataclass
class Blueprint:
    name: str
    version: str
    sha256: str = ""
    sandbox_memory_mb: int = 400
    sandbox_tmp_mb: int = 128
    sandbox_cpus: float = 1.5
    egress_policy_path: str = "config/egress_policy.yaml"

    @classmethod
    def resolve(cls, path: Path = Path("config/blueprint.yaml")) -> "Blueprint":
        raw = yaml.safe_load(path.read_text())
        fields = {k: v for k, v in raw.items() if k in cls.__dataclass_fields__}
        return cls(**fields)

    def verify(self, path: Path = Path("config/blueprint.yaml")) -> None:
        """sha256 完整性驗證（sha256="" 表示跳過）。"""
        if not self.sha256:
            return
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != self.sha256:
            raise ValueError(
                f"Blueprint digest mismatch: expected {self.sha256[:12]}... "
                f"got {actual[:12]}... — 檔案可能被篡改"
            )

    def preflight(self) -> dict:
        """Jetson-aware 記憶體 preflight（用 /proc/meminfo 取代 nvidia-smi）。"""
        available_mb = _read_memavailable_mb()
        required_mb = self.sandbox_memory_mb + 200  # runtime overhead
        if available_mb < required_mb:
            raise RuntimeError(
                f"可用記憶體 {available_mb}MB 不足（需要 {required_mb}MB）。"
                "請先 `sudo systemctl stop nvargus-daemon` 釋放記憶體。"
            )
        return {"available_mb": available_mb, "required_mb": required_mb, "ok": True}


def _read_memavailable_mb() -> int:
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) // 1024
    except FileNotFoundError:
        pass
    return 9999  # fallback：非 Linux 環境（CI / macOS 開發機）


def bootstrap(path: Path = Path("config/blueprint.yaml")) -> Blueprint:
    """啟動入口：載入 → 驗證 → preflight。"""
    if not path.exists():
        # blueprint.yaml 不存在時使用預設值（向後相容）
        return Blueprint(name="claw-python", version="0.1.0")
    bp = Blueprint.resolve(path)
    bp.verify(path)
    bp.preflight()
    return bp
```

### `config/blueprint.yaml`

```yaml
name: claw-python
version: "0.4.0"
sha256: ""                          # 首次 deploy 後執行 python scripts/gen_digest.py 填入
sandbox_memory_mb: 400
sandbox_tmp_mb: 128
sandbox_cpus: 1.5
egress_policy_path: config/egress_policy.yaml
```

### `scripts/gen_digest.py`（輔助工具）

```python
#!/usr/bin/env python3
import hashlib, sys
from pathlib import Path

path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("config/blueprint.yaml")
digest = hashlib.sha256(path.read_bytes()).hexdigest()
print(f"sha256: {digest}")
```

---

## P4-2　Egress 白名單 + 稽核系統

### DB Schema 擴充（`claw/core/storage.py`）

在現有 `init()` 方法的 `CREATE TABLE` 段落後新增：

```python
# egress 相關表
await db.executescript("""
    CREATE TABLE IF NOT EXISTS egress_pending (
        id           TEXT PRIMARY KEY,
        dest         TEXT NOT NULL,
        method       TEXT NOT NULL,
        requested_at INTEGER NOT NULL
    );
    CREATE TABLE IF NOT EXISTS egress_audit_log (
        id      INTEGER PRIMARY KEY AUTOINCREMENT,
        ts      INTEGER NOT NULL,
        dest    TEXT NOT NULL,
        verdict TEXT NOT NULL,
        tool    TEXT NOT NULL
    );
""")
```

### `claw/tools/policy.py` 擴充

在現有 `is_main_session()` 下方新增 EgressPolicy（不動現有程式碼）：

```python
from enum import Enum
from dataclasses import dataclass, field
import time, uuid
import aiosqlite
import yaml
from pathlib import Path

class EgressVerdict(str, Enum):
    ALLOW   = "allow"
    DENY    = "deny"
    PENDING = "pending"

@dataclass
class EgressRule:
    dest: str
    methods: list[str] = field(default_factory=lambda: ["GET", "POST"])
    verdict: EgressVerdict = EgressVerdict.ALLOW

@dataclass
class EgressPolicy:
    rules: list[EgressRule] = field(default_factory=list)
    default: EgressVerdict = EgressVerdict.DENY
    db_path: str = "~/.claw/claw.db"

    def check(self, dest: str, method: str = "POST") -> EgressVerdict:
        for rule in self.rules:
            if dest.endswith(rule.dest) and method in rule.methods:
                return rule.verdict
        return self.default

    async def request_approval(self, dest: str, method: str) -> str:
        req_id = str(uuid.uuid4())[:8]
        async with aiosqlite.connect(Path(self.db_path).expanduser()) as db:
            await db.execute(
                "INSERT INTO egress_pending(id,dest,method,requested_at) VALUES(?,?,?,?)",
                (req_id, dest, method, int(time.time()))
            )
            await db.commit()
        return req_id

    async def audit(self, dest: str, verdict: EgressVerdict, tool: str) -> None:
        async with aiosqlite.connect(Path(self.db_path).expanduser()) as db:
            await db.execute(
                "INSERT INTO egress_audit_log(ts,dest,verdict,tool) VALUES(?,?,?,?)",
                (int(time.time()), dest, verdict.value, tool)
            )
            await db.commit()

    def add_rule(self, dest: str, method: str = "POST") -> None:
        """動態新增規則（admin 審批後呼叫）。"""
        for rule in self.rules:
            if rule.dest == dest and method in rule.methods:
                return  # 已存在
        self.rules.append(EgressRule(dest=dest, methods=[method]))

    @classmethod
    def from_yaml(cls, path: Path, db_path: str = "~/.claw/claw.db") -> "EgressPolicy":
        if not path.exists():
            return cls(db_path=db_path)
        raw = yaml.safe_load(path.read_text())
        rules = [
            EgressRule(
                dest=r["dest"],
                methods=r.get("methods", ["GET", "POST"]),
                verdict=EgressVerdict(r.get("verdict", "allow")),
            )
            for r in raw.get("egress_rules", [])
        ]
        default = EgressVerdict(raw.get("default", "deny"))
        return cls(rules=rules, default=default, db_path=db_path)
```

### `config/egress_policy.yaml`

```yaml
default: deny
egress_rules:
  - dest: "llm-router.local"
    methods: [POST]
    verdict: allow
  - dest: "127.0.0.1"            # LLM-Router 本地
    methods: [GET, POST]
    verdict: allow
  - dest: "localhost"
    methods: [GET, POST]
    verdict: allow
  - dest: "duckduckgo.com"       # tools/search.py → DDGS
    methods: [GET, POST]
    verdict: allow
  - dest: "html.duckduckgo.com"
    methods: [GET]
    verdict: allow
  # 其他目標觸發 pending → 等管理員審批
```

---

## P4-3　Agent Loop Egress 攔截（最小 diff）

**`claw/agent/loop.py` 修改：**

在 AgentLoop `__init__` 加入 egress 注入：

```python
def __init__(self, storage: Storage, llm: LLMRouterClient, egress: "EgressPolicy | None" = None):
    self.storage = storage
    self.llm = llm
    self.egress = egress
```

在現有 tool dispatch 邏輯前（`tool_result = await registry.execute(...)` 這行之前）插入：

```python
# ── Egress check ──
if self.egress:
    dest = _infer_egress_dest(tool_name, tool_input)
    if dest:
        from claw.tools.policy import EgressVerdict
        verdict = self.egress.check(dest)
        await self.egress.audit(dest, verdict, tool_name)
        if verdict == EgressVerdict.DENY:
            tool_result = f"[egress denied] {dest} 不在白名單，請聯絡管理員審批。"
            # yield ToolCallResult 後 continue
        elif verdict == EgressVerdict.PENDING:
            req_id = await self.egress.request_approval(dest, "POST")
            tool_result = f"[egress pending #{req_id}] {dest} 等待審批，稍後重試。"
            # yield ToolCallResult 後 continue
# ─────────────────
```

新增推斷函數（module level）：

```python
def _infer_egress_dest(tool_name: str, tool_input: dict) -> str | None:
    mapping = {
        "search":    "duckduckgo.com",
        "web_fetch": tool_input.get("url", "").split("/")[2] if "url" in tool_input else None,
    }
    return mapping.get(tool_name)
```

---

## P4-4　Sandbox 強化（docker_runner.py 擴充）

### `sandbox/seccomp_minimal.json`（新建）

```json
{
  "defaultAction": "SCMP_ACT_ERRNO",
  "syscalls": [
    {
      "names": [
        "read", "write", "open", "openat", "openat2", "close",
        "stat", "fstat", "fstatat", "lstat", "newfstatat",
        "execve", "execveat", "clone", "fork", "vfork",
        "wait4", "waitid", "exit", "exit_group",
        "mmap", "mprotect", "munmap", "brk", "madvise",
        "futex", "set_robust_list", "get_robust_list",
        "getpid", "getppid", "getuid", "getgid",
        "getpgrp", "getsid", "getcwd", "chdir", "fchdir",
        "pipe", "pipe2", "dup", "dup2", "dup3",
        "nanosleep", "clock_gettime", "clock_nanosleep",
        "set_tid_address", "arch_prctl",
        "rt_sigaction", "rt_sigprocmask", "rt_sigreturn", "sigaltstack",
        "kill", "tgkill",
        "readlink", "readlinkat", "access", "faccessat",
        "umask", "getdents", "getdents64",
        "ioctl", "fcntl", "lseek", "pread64", "pwrite64",
        "mkdir", "mkdirat", "rmdir", "unlink", "unlinkat",
        "rename", "renameat", "chmod", "fchmod", "chown",
        "socket", "connect", "sendto", "recvfrom",
        "setsockopt", "getsockopt", "bind", "listen", "accept",
        "select", "poll", "epoll_create", "epoll_create1",
        "epoll_ctl", "epoll_wait", "epoll_pwait",
        "eventfd", "eventfd2", "timerfd_create",
        "prctl", "sysinfo", "uname",
        "mlock", "munlock", "mlockall", "munlockall",
        "fallocate", "ftruncate",
        "copy_file_range", "sendfile",
        "setpgid", "setsid",
        "getrlimit", "setrlimit", "prlimit64",
        "getrandom", "memfd_create"
      ],
      "action": "SCMP_ACT_ALLOW"
    }
  ]
}
```

### `claw/sandbox/policy.py` 擴充

在現有 `needs_sandbox()` 後新增：

```python
from dataclasses import dataclass, field
from pathlib import Path

@dataclass
class SandboxPolicy:
    enabled: bool = True
    memory_limit_mb: int = 400
    cpus: float = 1.5
    tmp_size_mb: int = 128
    workspace_path: str = "~/.claw/workspaces"
    image: str = "claw-sandbox:latest"
    workspace_dir: str = "/workspace"
    timeout: int = 60
    seccomp_profile: str = ""   # 空字串 = 不啟用
    no_new_privs: bool = True
    read_only: bool = True

    @classmethod
    def from_blueprint(cls, bp) -> "SandboxPolicy":
        return cls(
            memory_limit_mb=bp.sandbox_memory_mb,
            tmp_size_mb=bp.sandbox_tmp_mb,
            cpus=bp.sandbox_cpus,
        )
```

### `claw/sandbox/docker_runner.py` 強化

`_create_container()` 方法改為：

```python
def _create_container(self, session_id: str) -> SandboxContainer:
    import os, time
    from pathlib import Path

    cfg = get_config().sandbox
    client = self._get_client()

    workspace = os.path.expanduser(
        f"~/.claw/workspaces/{session_id.replace(':', '_')}"
    )
    os.makedirs(workspace, exist_ok=True)

    # Security options
    security_opt = ["no-new-privileges:true"]
    seccomp_path = Path(__file__).parent / "seccomp_minimal.json"
    if seccomp_path.exists():
        security_opt.append(f"seccomp={seccomp_path}")

    container = client.containers.run(
        image=cfg.image,
        command="/bin/bash",
        detach=True,
        tty=True,
        stdin_open=True,
        working_dir=cfg.workspace_dir,
        volumes={workspace: {"bind": cfg.workspace_dir, "mode": "rw"}},
        mem_limit=f"{cfg.memory_limit_mb}m",
        memswap_limit=f"{cfg.memory_limit_mb}m",   # 禁用 container-level swap
        nano_cpus=int(cfg.cpus * 1e9),              # --cpus 的 SDK 等價
        network_mode="none",                         # Jetson workaround：繞過 nf_tables
        read_only=True,                              # 根目錄唯讀
        tmpfs={
            "/tmp": f"size={cfg.tmp_size_mb}m,exec",
            "/run": "size=8m",
        },
        security_opt=security_opt,
        user="nobody",
        remove=False,
        labels={"claw.session_id": session_id},
    )
    logger.info(f"sandbox created (hardened): {container.short_id} for {session_id}")
    return SandboxContainer(
        session_id=session_id,
        container_id=container.id,
        workspace_path=workspace,
        created_at=time.time(),
    )
```

### `config/default.yaml` sandbox 區塊更新

```yaml
sandbox:
  enabled: true
  image: "claw-sandbox:latest"
  workspace_dir: "/workspace"
  timeout: 60
  memory_limit_mb: 400          # 從 "256m" 字串改為整數（Blueprint 管理）
  tmp_size_mb: 128
  cpus: 1.5
  no_new_privs: true
  read_only: true
```

---

## P4-5　Admin Egress 管理 Endpoints（`core/gateway.py` 新增）

```python
# ── Egress 管理 endpoints ──────────────────────────────────────

from fastapi import BackgroundTasks, HTTPException

@app.get("/admin/egress/pending")
async def egress_list_pending():
    """列出所有 pending 的 egress 請求。"""
    db_path = Path("~/.claw/claw.db").expanduser()
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id, dest, method, requested_at FROM egress_pending ORDER BY requested_at DESC"
        ) as cur:
            rows = await cur.fetchall()
    return [dict(r) for r in rows]

@app.post("/admin/egress/{req_id}/approve")
async def egress_approve(req_id: str, background_tasks: BackgroundTasks):
    """審批 pending 請求，動態加入白名單（不重啟）。"""
    db_path = Path("~/.claw/claw.db").expanduser()
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT dest, method FROM egress_pending WHERE id=?", (req_id,)
        ) as cur:
            row = await cur.fetchone()
        if not row:
            raise HTTPException(404, f"request {req_id} not found")
        dest, method = row["dest"], row["method"]
        await db.execute("DELETE FROM egress_pending WHERE id=?", (req_id,))
        await db.commit()

    # 動態更新記憶體中的 EgressPolicy（不重啟）
    from claw.tools.policy import get_egress_policy
    get_egress_policy().add_rule(dest, method)
    return {"approved": dest, "method": method}

@app.get("/admin/egress/audit")
async def egress_audit_log(limit: int = 100):
    """查看 egress 稽核日誌。"""
    db_path = Path("~/.claw/claw.db").expanduser()
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT ts, dest, verdict, tool FROM egress_audit_log ORDER BY ts DESC LIMIT ?",
            (limit,)
        ) as cur:
            rows = await cur.fetchall()
    return [dict(r) for r in rows]
```

---

## P4-6　`main.py` 整合

```python
from config.blueprint import bootstrap as blueprint_bootstrap
from claw.tools.policy import EgressPolicy
from pathlib import Path

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Blueprint 驗證 + preflight
    bp = blueprint_bootstrap()

    # 2. Storage init（含新表）
    cfg = get_config()
    storage = Storage(...)
    await storage.init()

    # 3. Egress Policy 載入
    egress = EgressPolicy.from_yaml(
        Path(bp.egress_policy_path),
        db_path=cfg.storage.db_path,
    )

    # 4. AgentLoop 注入 egress
    # （在 gateway_module 的 get_agent_loop 中接受 egress 參數）

    yield
    ...
```

---

## 測試要求

### `tests/test_blueprint.py`（新增 4 tests）
- `test_blueprint_load_default` — 無 blueprint.yaml 時回傳預設值
- `test_blueprint_sha256_mismatch` — 篡改後 verify() 拋 ValueError
- `test_blueprint_preflight_ok` — MemAvailable > required → ok
- `test_blueprint_from_yaml` — 正確解析 sandbox_memory_mb

### `tests/test_egress.py`（新增 5 tests）
- `test_egress_allow` — dest 在白名單 → ALLOW
- `test_egress_deny_default` — dest 不在白名單，default=deny → DENY
- `test_egress_add_rule_dynamic` — add_rule() 後 check() → ALLOW
- `test_egress_from_yaml` — 正確解析 egress_policy.yaml
- `test_egress_audit(tmp_path)` — audit() 寫入 DB，可查詢

### `tests/test_sandbox.py` 新增（2 tests）
- `test_seccomp_profile_exists` — seccomp_minimal.json 存在且 JSON 合法
- `test_sandbox_policy_from_blueprint` — SandboxPolicy.from_blueprint() 欄位正確

---

## 驗收標準

```bash
python -m pytest tests/ -v
# 預期：64 + 11 = 75 tests PASSED

# 驗證 sandbox 新欄位存在
python -c "from claw.sandbox.policy import SandboxPolicy; p = SandboxPolicy(); print(p.read_only, p.no_new_privs)"

# 驗證 egress policy 可載入
python -c "from claw.tools.policy import EgressPolicy; from pathlib import Path; e = EgressPolicy.from_yaml(Path('config/egress_policy.yaml')); print(e.default)"
```

---

## 實作順序（最小風險路徑）

| 步驟 | 檔案 | 風險 | 備註 |
|---|---|---|---|
| STEP 1 | `config/blueprint.py` + `blueprint.yaml` | 零 | 純新增 |
| STEP 2 | `scripts/gen_digest.py` | 零 | 輔助工具 |
| STEP 3 | `sandbox/seccomp_minimal.json` | 零 | 靜態檔案 |
| STEP 4 | `core/storage.py` +2 張表 | 低 | migration 一次跑 |
| STEP 5 | `tools/policy.py` + EgressPolicy | 低 | 不動現有程式碼 |
| STEP 6 | `config/egress_policy.yaml` | 零 | 純設定 |
| STEP 7 | `sandbox/policy.py` + SandboxPolicy | 中 | 更新 dataclass |
| STEP 8 | `sandbox/docker_runner.py` + 強化 | 中高 | 先在 RTX 測試 |
| STEP 9 | `agent/loop.py` + egress check | 中 | 最小 4 行 diff |
| STEP 10 | `core/gateway.py` + admin endpoints | 低 | 純新增 |
| STEP 11 | `main.py` 整合 + tests | 中 | 最終接線 |

---

## 後續 Phase 概覽

| Phase | 內容 | 前置條件 |
|---|---|---|
| **5** | Memory/RAG + Context Compaction | Phase 4 完成 |
| **6** | Channel Adapters（Telegram + Slack） | Phase 4 完成 |
| **7** | Observability（structlog + Prometheus + Admin API） | Phase 4 完成 |
| **8** | MCP Bridge + Browser/File Tools + TTS | Phase 5-7 完成 |
