from __future__ import annotations


def is_main_session(session_id: str) -> bool:
    return session_id == "agent:main" or session_id.endswith(":main")
