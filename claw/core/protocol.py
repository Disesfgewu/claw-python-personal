from dataclasses import dataclass, field
from typing import Any, Literal


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
