# Phase 4 Implementation Prompt — NemoClaw Security Layer
# for Claude Sonnet 4.6

**You are a Python backend engineer implementing Phase 4 of claw-python.**
**This phase ports NemoClaw's enterprise security design to our Jetson Orin Nano Super.**

---

## Hardware Context

- Device: Jetson Orin Nano Super (kernel 5.15.136-tegra, 8GB unified memory)
- Available memory: ~1.9GB for runtime
- Docker: `network_mode="none"` already implemented (bypasses Tegra iptables panic)
- LLM: handled entirely by LLM-Router — no local inference
- **DO NOT** implement: k3s, Landlock, Nemotron, GPU detection via nvidia-smi

## Current State

- 64 tests passing
- `claw/sandbox/docker_runner.py` already has `network_mode="none"` ✅
- Missing: Blueprint, Egress Policy, seccomp, read_only, no-new-privileges

## Goal

Implement three security layers inspired by NemoClaw, Jetson-optimized:
1. **Blueprint** — config integrity verification + memory preflight
2. **Egress Policy** — network whitelist + audit log + admin approval flow
3. **Sandbox Hardening** — seccomp + read_only + no-new-privileges

**DO NOT break existing 64 tests.**

---

## STEP 0: Verify baseline

```bash
python -m pytest tests/ -v --tb=short
# Must show: 64 passed
```

---

## STEP 1: Blueprint System (pure additions, zero risk)

**File: `config/__init__.py`** (empty, create if not exists)

**File: `config/blueprint.py`** (NEW)

```python
from __future__ import annotations
import hashlib
import yaml
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Blueprint:
    name: str = "claw-python"
    version: str = "0.4.0"
    sha256: str = ""
    sandbox_memory_mb: int = 400
    sandbox_tmp_mb: int = 128
    sandbox_cpus: float = 1.5
    egress_policy_path: str = "config/egress_policy.yaml"

    @classmethod
    def resolve(cls, path: Path = Path("config/blueprint.yaml")) -> "Blueprint":
        raw = yaml.safe_load(path.read_text())
        valid = {k: v for k, v in raw.items() if k in cls.__dataclass_fields__}
        return cls(**valid)

    def verify(self, path: Path = Path("config/blueprint.yaml")) -> None:
        """SHA256 integrity check. Empty sha256 = skip (dev mode)."""
        if not self.sha256:
            return
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != self.sha256:
            raise ValueError(
                f"Blueprint digest mismatch — file may be tampered. "
                f"Expected {self.sha256[:12]}... got {actual[:12]}..."
            )

    def preflight(self) -> dict:
        """Jetson-aware memory check using /proc/meminfo (not nvidia-smi)."""
        available_mb = _read_memavailable_mb()
        required_mb = self.sandbox_memory_mb + 200  # runtime overhead
        if available_mb < required_mb:
            raise RuntimeError(
                f"Insufficient memory: {available_mb}MB available, "
                f"{required_mb}MB required. "
                "Try: sudo systemctl stop nvargus-daemon"
            )
        return {"available_mb": available_mb, "required_mb": required_mb, "ok": True}


def _read_memavailable_mb() -> int:
    """Read available memory from /proc/meminfo. Returns 9999 on non-Linux."""
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) // 1024
    except FileNotFoundError:
        pass
    return 9999  # fallback for macOS/CI


def bootstrap(path: Path = Path("config/blueprint.yaml")) -> Blueprint:
    """Load blueprint → verify integrity → run preflight. Safe if file missing."""
    if not path.exists():
        return Blueprint()
    bp = Blueprint.resolve(path)
    bp.verify(path)
    bp.preflight()
    return bp
```

**File: `config/blueprint.yaml`** (NEW)

```yaml
name: claw-python
version: "0.4.0"
sha256: ""
sandbox_memory_mb: 400
sandbox_tmp_mb: 128
sandbox_cpus: 1.5
egress_policy_path: config/egress_policy.yaml
```

**File: `scripts/gen_digest.py`** (NEW)

```python
#!/usr/bin/env python3
"""Generate SHA256 digest for blueprint.yaml to fill in the sha256 field."""
import hashlib, sys
from pathlib import Path

path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("config/blueprint.yaml")
digest = hashlib.sha256(path.read_bytes()).hexdigest()
print(f"sha256: {digest}")
print(f"# Add this to {path}")
```

---

## STEP 2: Egress Policy (append to existing policy.py, do NOT touch is_main_session)

**Append to end of `claw/tools/policy.py`:**

```python
# ── NemoClaw-inspired Egress Policy ───────────────────────────────────────────
from enum import Enum
from dataclasses import dataclass, field
import time
import uuid
import yaml
import aiosqlite
from pathlib import Path


class EgressVerdict(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
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
                (req_id, dest, method, int(time.time())),
            )
            await db.commit()
        return req_id

    async def audit(self, dest: str, verdict: EgressVerdict, tool: str) -> None:
        async with aiosqlite.connect(Path(self.db_path).expanduser()) as db:
            await db.execute(
                "INSERT INTO egress_audit_log(ts,dest,verdict,tool) VALUES(?,?,?,?)",
                (int(time.time()), dest, verdict.value, tool),
            )
            await db.commit()

    def add_rule(self, dest: str, method: str = "POST") -> None:
        """Dynamically add whitelist rule at runtime (no restart needed)."""
        for rule in self.rules:
            if rule.dest == dest and method in rule.methods:
                return
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


# Module-level singleton (set by main.py)
_egress_policy: EgressPolicy | None = None


def get_egress_policy() -> EgressPolicy:
    global _egress_policy
    if _egress_policy is None:
        _egress_policy = EgressPolicy()
    return _egress_policy


def set_egress_policy(policy: EgressPolicy) -> None:
    global _egress_policy
    _egress_policy = policy
```

**New file: `config/egress_policy.yaml`**

```yaml
default: deny
egress_rules:
  - dest: "llm-router.local"
    methods: [POST]
    verdict: allow
  - dest: "127.0.0.1"
    methods: [GET, POST]
    verdict: allow
  - dest: "localhost"
    methods: [GET, POST]
    verdict: allow
  - dest: "duckduckgo.com"
    methods: [GET, POST]
    verdict: allow
  - dest: "html.duckduckgo.com"
    methods: [GET]
    verdict: allow
```

---

## STEP 3: Storage Schema — Add Egress Tables

**Edit `claw/core/storage.py`**, find the `init()` method.
After the last `CREATE TABLE` statement (before `await db.commit()`), add:

```python
# Egress tables (NemoClaw security layer)
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
```

---

## STEP 4: Sandbox seccomp Profile (static file)

**New file: `claw/sandbox/seccomp_minimal.json`**

```json
{
  "defaultAction": "SCMP_ACT_ERRNO",
  "syscalls": [
    {
      "names": [
        "read", "write", "open", "openat", "openat2", "close",
        "stat", "fstat", "fstatat", "lstat", "newfstatat",
        "execve", "execveat",
        "clone", "clone3", "fork", "vfork",
        "wait4", "waitid", "exit", "exit_group",
        "mmap", "mmap2", "mprotect", "munmap", "brk", "madvise",
        "mremap", "msync",
        "futex", "set_robust_list", "get_robust_list",
        "getpid", "getppid", "getuid", "getgid", "geteuid", "getegid",
        "getpgrp", "getpgid", "getsid", "getcwd", "chdir", "fchdir",
        "pipe", "pipe2", "dup", "dup2", "dup3",
        "nanosleep", "clock_gettime", "clock_nanosleep", "gettimeofday",
        "set_tid_address", "arch_prctl",
        "rt_sigaction", "rt_sigprocmask", "rt_sigreturn", "sigaltstack",
        "kill", "tgkill", "tkill",
        "readlink", "readlinkat",
        "access", "faccessat", "faccessat2",
        "umask", "getdents", "getdents64",
        "ioctl", "fcntl", "lseek", "pread64", "pwrite64", "preadv", "pwritev",
        "mkdir", "mkdirat", "rmdir", "unlink", "unlinkat",
        "rename", "renameat", "renameat2",
        "chmod", "fchmod", "chown", "fchown", "lchown",
        "socket", "connect", "sendto", "recvfrom",
        "setsockopt", "getsockopt", "bind", "listen", "accept", "accept4",
        "shutdown", "getsockname", "getpeername",
        "select", "pselect6", "poll", "ppoll",
        "epoll_create", "epoll_create1", "epoll_ctl", "epoll_wait", "epoll_pwait",
        "eventfd", "eventfd2", "timerfd_create", "timerfd_settime", "timerfd_gettime",
        "prctl", "sysinfo", "uname",
        "mlock", "munlock", "mlockall", "munlockall",
        "fallocate", "ftruncate", "truncate",
        "copy_file_range", "sendfile",
        "setpgid", "setsid",
        "getrlimit", "setrlimit", "prlimit64", "getrusage",
        "getrandom", "memfd_create",
        "statx", "statfs", "fstatfs",
        "sendmsg", "recvmsg", "sendmmsg", "recvmmsg",
        "symlink", "symlinkat", "link", "linkat",
        "sync", "fsync", "fdatasync",
        "times", "time", "clock_getres",
        "signalfd", "signalfd4",
        "rt_sigpending", "rt_sigsuspend", "rt_sigtimedwait",
        "restart_syscall"
      ],
      "action": "SCMP_ACT_ALLOW"
    }
  ]
}
```

---

## STEP 5: Sandbox Policy Expansion

**Edit `claw/sandbox/policy.py`**

After the existing `needs_sandbox()` function, append:

```python
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class SandboxPolicy:
    """NemoClaw-inspired sandbox policy dataclass."""
    enabled: bool = True
    memory_limit_mb: int = 400
    cpus: float = 1.5
    tmp_size_mb: int = 128
    workspace_path: str = "~/.claw/workspaces"
    image: str = "claw-sandbox:latest"
    workspace_dir: str = "/workspace"
    timeout: int = 60
    read_only: bool = True
    no_new_privs: bool = True
    seccomp_profile: str = ""   # auto-detected from seccomp_minimal.json

    @classmethod
    def from_blueprint(cls, bp) -> "SandboxPolicy":
        return cls(
            memory_limit_mb=bp.sandbox_memory_mb,
            tmp_size_mb=bp.sandbox_tmp_mb,
            cpus=bp.sandbox_cpus,
        )

    @classmethod
    def from_config(cls) -> "SandboxPolicy":
        """Load from claw config (backward compat)."""
        from claw.core.config import get_config
        cfg = get_config().sandbox
        return cls(
            enabled=cfg.enabled,
            image=cfg.image,
            workspace_dir=cfg.workspace_dir,
            timeout=cfg.timeout,
        )
```

---

## STEP 6: Docker Runner Hardening

**Edit `claw/sandbox/docker_runner.py`**

Replace the `_create_container()` method with the hardened version:

```python
def _create_container(self, session_id: str) -> SandboxContainer:
    import os
    import time
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

    # Memory: use integer MB from config
    # Support both old string format ("256m") and new integer format (400)
    memory_mb = getattr(cfg, "memory_limit_mb", None)
    if memory_mb is None:
        # backward compat: parse from string "256m"
        mem_str = getattr(cfg, "memory_limit", "256m")
        memory_mb = int(mem_str.rstrip("m").rstrip("M"))

    cpus = getattr(cfg, "cpus", 1.5)
    tmp_size_mb = getattr(cfg, "tmp_size_mb", 128)

    container = client.containers.run(
        image=cfg.image,
        command="/bin/bash",
        detach=True,
        tty=True,
        stdin_open=True,
        working_dir=cfg.workspace_dir,
        volumes={workspace: {"bind": cfg.workspace_dir, "mode": "rw"}},
        # Memory: limit + disable container-level swap
        mem_limit=f"{memory_mb}m",
        memswap_limit=f"{memory_mb}m",
        # CPU: use nano_cpus (Docker SDK equivalent of --cpus)
        nano_cpus=int(cpus * 1e9),
        # Network: none — Jetson workaround (bypasses nf_tables/iptables kernel panic)
        network_mode="none",
        # Filesystem hardening
        read_only=True,
        tmpfs={
            "/tmp": f"size={tmp_size_mb}m,exec",
            "/run": "size=8m",
            "/var/tmp": "size=8m",
        },
        # Security hardening
        security_opt=security_opt,
        user="nobody",
        remove=False,
        labels={"claw.session_id": session_id},
    )
    logger.info(
        f"sandbox created (hardened): {container.short_id} "
        f"mem={memory_mb}m cpus={cpus} "
        f"seccomp={'yes' if seccomp_path.exists() else 'no'} "
        f"for {session_id}"
    )
    return SandboxContainer(
        session_id=session_id,
        container_id=container.id,
        workspace_path=workspace,
        created_at=time.time(),
    )
```

---

## STEP 7: Agent Loop Egress Check (minimal 4-line diff)

**Edit `claw/agent/loop.py`**

1. Add `egress` parameter to `AgentLoop.__init__`:

```python
def __init__(self, storage: Storage, llm: LLMRouterClient, egress=None):
    self.storage = storage
    self.llm = llm
    self.egress = egress  # EgressPolicy | None
```

2. Find the tool execution loop (where `tool_result = await registry.execute(...)` is called).
   **Before** that call, insert:

```python
# ── Egress check (NemoClaw security layer) ────────────────────
if self.egress is not None:
    _dest = _infer_egress_dest(tool_name, tool_input)
    if _dest:
        from claw.tools.policy import EgressVerdict
        _verdict = self.egress.check(_dest)
        await self.egress.audit(_dest, _verdict, tool_name)
        if _verdict == EgressVerdict.DENY:
            tool_result = f"[egress denied] {_dest} not whitelisted. Contact admin."
            yield ToolCallResult(tool_call_id=tc_id, tool_name=tool_name, result=tool_result)
            continue
        elif _verdict == EgressVerdict.PENDING:
            _req_id = await self.egress.request_approval(_dest, "POST")
            tool_result = f"[egress pending #{_req_id}] {_dest} awaiting approval."
            yield ToolCallResult(tool_call_id=tc_id, tool_name=tool_name, result=tool_result)
            continue
# ──────────────────────────────────────────────────────────────
```

3. Add module-level helper function (at module level, not inside class):

```python
def _infer_egress_dest(tool_name: str, tool_input: dict) -> str | None:
    """Infer egress destination from tool name/input."""
    if tool_name == "search":
        return "duckduckgo.com"
    if tool_name == "web_fetch":
        url = tool_input.get("url", "")
        if "://" in url:
            return url.split("/")[2]  # extract hostname
    return None
```

**IMPORTANT:** The variable names `tc_id` and `tool_name` and `tool_input` should match whatever names exist in your tool loop. Read the existing loop code carefully before inserting.

---

## STEP 8: Admin Endpoints (append to gateway.py)

**Append to `claw/core/gateway.py`** (after existing routes):

```python
# ── Egress Admin Endpoints (NemoClaw security layer) ────────────────

import aiosqlite as _aiosqlite
from pathlib import Path as _Path
from fastapi import BackgroundTasks, HTTPException


@app.get("/admin/egress/pending")
async def egress_list_pending():
    """List all pending egress approval requests."""
    db_path = _Path("~/.claw/claw.db").expanduser()
    async with _aiosqlite.connect(db_path) as db:
        db.row_factory = _aiosqlite.Row
        async with db.execute(
            "SELECT id, dest, method, requested_at FROM egress_pending ORDER BY requested_at DESC"
        ) as cur:
            rows = await cur.fetchall()
    return [dict(r) for r in rows]


@app.post("/admin/egress/{req_id}/approve")
async def egress_approve(req_id: str, background_tasks: BackgroundTasks):
    """Approve egress request. Dynamically adds to whitelist (no restart needed)."""
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
async def egress_audit_log(limit: int = 100):
    """View egress audit log."""
    db_path = _Path("~/.claw/claw.db").expanduser()
    async with _aiosqlite.connect(db_path) as db:
        db.row_factory = _aiosqlite.Row
        async with db.execute(
            "SELECT ts, dest, verdict, tool FROM egress_audit_log ORDER BY ts DESC LIMIT ?",
            (limit,),
        ) as cur:
            rows = await cur.fetchall()
    return [dict(r) for r in rows]
```

---

## STEP 9: Tests

**New file: `tests/test_blueprint.py`**

```python
import pytest
import hashlib
from pathlib import Path
from config.blueprint import Blueprint, _read_memavailable_mb, bootstrap


def test_blueprint_load_defaults():
    """No blueprint.yaml → returns default values."""
    bp = bootstrap(path=Path("/nonexistent/blueprint.yaml"))
    assert bp.name == "claw-python"
    assert bp.sandbox_memory_mb == 400


def test_blueprint_sha256_mismatch(tmp_path):
    """Tampered file raises ValueError."""
    bp_file = tmp_path / "blueprint.yaml"
    bp_file.write_text("name: claw-python\nversion: '0.4.0'\nsha256: 'abc123'\n")
    bp = Blueprint(name="claw-python", version="0.4.0", sha256="abc123")
    with pytest.raises(ValueError, match="digest mismatch"):
        bp.verify(bp_file)


def test_blueprint_sha256_match(tmp_path):
    """Correct sha256 passes verification."""
    bp_file = tmp_path / "blueprint.yaml"
    content = "name: claw-python\nversion: '0.4.0'\nsha256: ''\n"
    bp_file.write_text(content)
    correct_sha = hashlib.sha256(content.encode()).hexdigest()

    bp = Blueprint(name="claw-python", version="0.4.0", sha256=correct_sha)
    bp.verify(bp_file)  # should not raise


def test_blueprint_preflight_ok(monkeypatch):
    """Sufficient memory → preflight returns ok=True."""
    monkeypatch.setattr("config.blueprint._read_memavailable_mb", lambda: 9999)
    bp = Blueprint(name="x", version="0.1.0", sandbox_memory_mb=400)
    result = bp.preflight()
    assert result["ok"] is True


def test_blueprint_preflight_oom(monkeypatch):
    """Insufficient memory → RuntimeError."""
    monkeypatch.setattr("config.blueprint._read_memavailable_mb", lambda: 100)
    bp = Blueprint(name="x", version="0.1.0", sandbox_memory_mb=400)
    with pytest.raises(RuntimeError, match="memory"):
        bp.preflight()
```

**New file: `tests/test_egress.py`**

```python
import pytest
from claw.tools.policy import EgressPolicy, EgressVerdict, EgressRule


def _make_policy(default="deny") -> EgressPolicy:
    rules = [
        EgressRule(dest="api.example.com", methods=["POST"], verdict=EgressVerdict.ALLOW),
        EgressRule(dest="blocked.com", methods=["GET", "POST"], verdict=EgressVerdict.DENY),
    ]
    return EgressPolicy(rules=rules, default=EgressVerdict(default))


def test_egress_allow():
    p = _make_policy()
    assert p.check("api.example.com", "POST") == EgressVerdict.ALLOW


def test_egress_deny_explicit():
    p = _make_policy()
    assert p.check("blocked.com", "POST") == EgressVerdict.DENY


def test_egress_deny_default():
    p = _make_policy(default="deny")
    assert p.check("unknown.com", "POST") == EgressVerdict.DENY


def test_egress_add_rule_dynamic():
    p = _make_policy()
    p.add_rule("newsite.com", "GET")
    assert p.check("newsite.com", "GET") == EgressVerdict.ALLOW


def test_egress_add_rule_no_duplicate():
    p = _make_policy()
    p.add_rule("api.example.com", "POST")
    # Should not add duplicate
    count = sum(1 for r in p.rules if r.dest == "api.example.com")
    assert count == 1


@pytest.mark.asyncio
async def test_egress_audit_writes_to_db(tmp_path):
    import aiosqlite
    db_path = str(tmp_path / "claw.db")

    # Create table
    async with aiosqlite.connect(db_path) as db:
        await db.execute("""
            CREATE TABLE egress_audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts INTEGER NOT NULL, dest TEXT NOT NULL,
                verdict TEXT NOT NULL, tool TEXT NOT NULL
            )
        """)
        await db.commit()

    p = EgressPolicy(db_path=db_path)
    await p.audit("example.com", EgressVerdict.ALLOW, "search")

    async with aiosqlite.connect(db_path) as db:
        async with db.execute("SELECT dest, verdict, tool FROM egress_audit_log") as cur:
            rows = await cur.fetchall()

    assert len(rows) == 1
    assert rows[0][0] == "example.com"
    assert rows[0][1] == "allow"


def test_egress_from_yaml(tmp_path):
    from pathlib import Path
    policy_file = tmp_path / "egress.yaml"
    policy_file.write_text("""
default: deny
egress_rules:
  - dest: "llm-router.local"
    methods: [POST]
    verdict: allow
""")
    p = EgressPolicy.from_yaml(policy_file)
    assert p.default == EgressVerdict.DENY
    assert p.check("llm-router.local", "POST") == EgressVerdict.ALLOW


def test_seccomp_json_valid():
    """seccomp_minimal.json must exist and be valid JSON."""
    import json
    from pathlib import Path
    seccomp_path = Path("claw/sandbox/seccomp_minimal.json")
    assert seccomp_path.exists(), "seccomp_minimal.json not found"
    data = json.loads(seccomp_path.read_text())
    assert "defaultAction" in data
    assert "syscalls" in data
    assert len(data["syscalls"][0]["names"]) > 10
```

**Add to `tests/test_sandbox.py`** (append new tests, don't modify existing):

```python
def test_sandbox_policy_from_blueprint():
    """SandboxPolicy.from_blueprint() correctly maps blueprint fields."""
    from claw.sandbox.policy import SandboxPolicy
    from config.blueprint import Blueprint
    bp = Blueprint(name="x", version="0.1", sandbox_memory_mb=512, sandbox_tmp_mb=64, sandbox_cpus=2.0)
    policy = SandboxPolicy.from_blueprint(bp)
    assert policy.memory_limit_mb == 512
    assert policy.tmp_size_mb == 64
    assert policy.cpus == 2.0
```

---

## STEP 10: Validate

```bash
python -m pytest tests/ -v
```

**Expected:** 64 existing + 12 new = **~76 tests PASSED**

---

## Deliverables

Report back:

1. **File list:**
   ```
   ls config/ claw/sandbox/seccomp_minimal.json claw/tools/policy.py | head -30
   ```

2. **Test results:**
   ```
   python -m pytest tests/ -v | tail -20
   ```

3. **Egress policy smoke test:**
   ```
   python -c "
   from claw.tools.policy import EgressPolicy, EgressVerdict
   from pathlib import Path
   p = EgressPolicy.from_yaml(Path('config/egress_policy.yaml'))
   print('default:', p.default)
   print('llm-router check:', p.check('llm-router.local', 'POST'))
   print('unknown check:', p.check('evil.com', 'POST'))
   "
   ```

4. **Blueprint smoke test:**
   ```
   python -c "
   from config.blueprint import bootstrap
   bp = bootstrap()
   print('Blueprint loaded:', bp.name, bp.version)
   print('Preflight:', bp.preflight())
   "
   ```

---

## Critical Notes

- **DO NOT** modify `is_main_session()` or `needs_sandbox()` — only append to policy.py
- The egress check in `loop.py` is **optional** — if the loop's tool execution variable names differ, adapt accordingly. Read the actual loop.py code before editing.
- `network_mode="none"` is already in docker_runner.py — DO NOT remove it
- The `_create_container` replacement must keep `network_mode="none"` ✅
- `memswap_limit` must equal `mem_limit` to disable container-level swap
- `nano_cpus=int(cpus * 1e9)` is the Docker SDK way to do `--cpus`
- seccomp_minimal.json must include enough syscalls for bash + Python to work

Good luck! 🚀
