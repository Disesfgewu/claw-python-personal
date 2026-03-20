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

    if session_id == "agent:main" or session_id.endswith(":main"):
        return False

    return True


from dataclasses import dataclass, field


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
    seccomp_profile: str = ""

    @classmethod
    def from_blueprint(cls, bp) -> "SandboxPolicy":
        return cls(
            memory_limit_mb=bp.sandbox_memory_mb,
            tmp_size_mb=bp.sandbox_tmp_mb,
            cpus=bp.sandbox_cpus,
        )

    @classmethod
    def from_config(cls) -> "SandboxPolicy":
        from claw.core.config import get_config
        cfg = get_config().sandbox
        return cls(
            enabled=cfg.enabled,
            image=cfg.image,
            workspace_dir=cfg.workspace_dir,
            timeout=cfg.timeout,
        )
