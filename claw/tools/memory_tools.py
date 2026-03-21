from __future__ import annotations
from claw.tools.registry import tool

_memory_manager = None  # Set by main.py via set_memory_manager()


def set_memory_manager(mm) -> None:
    global _memory_manager
    _memory_manager = mm


@tool(
    name="memory_save",
    description="Save information to long-term memory. content is the text to remember, tags is optional JSON array string.",
    parameters={
        "type": "object",
        "properties": {
            "content": {"type": "string"},
            "tags": {
                "type": "string",
                "description": "Optional, JSON array format, e.g. '[\"important\", \"meeting\"]'",
            },
        },
        "required": ["content"],
    },
    requires_main=False,
)
async def memory_save(
    content: str, tags: str = "[]", session_id: str = "agent:main"
) -> str:
    if _memory_manager is None:
        return "Error: MemoryManager not initialized"
    import json
    try:
        tag_list = json.loads(tags)
    except Exception:
        tag_list = []
    metadata = {"tags": tag_list}
    effective_session_id = session_id if session_id else "agent:main"
    memory_id = await _memory_manager.save(effective_session_id, content, metadata)
    return f"✅ Memory saved id={memory_id[:8]}"


@tool(
    name="memory_search",
    description="Search long-term memory. query is the search string, limit is max results (default 5).",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "limit": {"type": "integer", "default": 5},
        },
        "required": ["query"],
    },
    requires_main=False,
)
async def memory_search(
    query: str, limit: int = 5, session_id: str = "agent:main"
) -> str:
    if _memory_manager is None:
        return "Error: MemoryManager not initialized"
    # Child sessions must never search across other sessions.
    # Passing session_id ensures the SQL WHERE clause filters correctly.
    # If session_id is falsy for any reason, default to main to prevent cross-session leakage.
    effective_session_id: str | None = session_id if session_id else "agent:main"
    results = await _memory_manager.search(query, effective_session_id, limit)
    if not results:
        return "(No relevant memory)"
    lines = [
        f"[{r['created_at'][:10]}] (score={r['score']:.2f}) {r['content'][:200]}"
        for r in results
    ]
    return "\n".join(lines)
