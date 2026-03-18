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
