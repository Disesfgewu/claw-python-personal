from __future__ import annotations
from claw.tools.registry import tool

_coordinator = None  # Set by main.py via set_coordinator()


def set_coordinator(c) -> None:
    global _coordinator
    _coordinator = c


@tool(
    name="sessions_send",
    description="Send message to another agent session and wait for full response. target_session_id is the target session.",
    parameters={
        "type": "object",
        "properties": {
            "target_session_id": {"type": "string"},
            "message":           {"type": "string"},
        },
        "required": ["target_session_id", "message"],
    },
    requires_main=False,
)
async def sessions_send(target_session_id: str, message: str) -> str:
    if _coordinator is None:
        return "Error: MultiAgentCoordinator not initialized"
    return await _coordinator.send(target_session_id, message)


@tool(
    name="sessions_spawn",
    description="Create new child agent session to execute goal asynchronously, return child session_id immediately.",
    parameters={
        "type": "object",
        "properties": {
            "goal":     {"type": "string"},
            "agent_id": {"type": "string", "default": "default"},
        },
        "required": ["goal"],
    },
    requires_main=False,
)
async def sessions_spawn(goal: str, agent_id: str = "default") -> str:
    if _coordinator is None:
        return "Error: MultiAgentCoordinator not initialized"
    child_id = await _coordinator.spawn(goal, agent_id)
    return f"spawned session_id={child_id}"


@tool(
    name="sessions_list",
    description="List all active sessions, return JSON.",
    parameters={"type": "object", "properties": {}},
    requires_main=True,
)
async def sessions_list() -> str:
    import json
    if _coordinator is None:
        return "Error: MultiAgentCoordinator not initialized"
    sessions = await _coordinator.list_sessions()
    return json.dumps([{"session_id": s.session_id, "scope": s.scope, "agent_id": s.agent_id} for s in sessions], ensure_ascii=False)
