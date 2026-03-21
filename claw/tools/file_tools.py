from __future__ import annotations

import os
from pathlib import Path

from claw.tools.registry import tool


def _resolve_workspace(session_id: str) -> Path:
    """Return the workspace path for a session."""
    safe_id = session_id.replace(":", "_")
    return Path(os.path.expanduser(f"~/.claw/workspaces/{safe_id}"))


def _safe_path(workspace: Path, rel_path: str) -> Path | None:
    """Resolve rel_path within workspace, return None if outside workspace."""
    if os.path.isabs(rel_path):
        return None
    resolved = (workspace / rel_path).resolve()
    try:
        resolved.relative_to(workspace.resolve())
        return resolved
    except ValueError:
        return None


@tool(
    name="file_read",
    description="Read a file from the session workspace. path must be relative to workspace root.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Relative file path within workspace"},
            "max_lines": {"type": "integer", "default": 200, "description": "Maximum lines to return"},
        },
        "required": ["path"],
    },
    requires_main=False,
)
async def file_read(path: str, max_lines: int = 200, session_id: str = "agent:main") -> str:
    workspace = _resolve_workspace(session_id)
    safe = _safe_path(workspace, path)
    if safe is None:
        return "Error: path traversal or absolute path not allowed"
    if not safe.exists():
        return f"Error: file not found: {path}"
    if not safe.is_file():
        return f"Error: not a file: {path}"
    try:
        lines = safe.read_text(encoding="utf-8", errors="replace").splitlines()
        if len(lines) > max_lines:
            truncated = lines[:max_lines]
            return "\n".join(truncated) + f"\n[truncated — {len(lines)} total lines]"
        return "\n".join(lines)
    except Exception as e:
        return f"Error reading file: {e}"


@tool(
    name="file_write",
    description="Write content to a file in the session workspace. Creates parent directories as needed. path must be relative.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Relative file path within workspace"},
            "content": {"type": "string", "description": "File content to write"},
            "append": {"type": "boolean", "default": False, "description": "Append instead of overwrite"},
        },
        "required": ["path", "content"],
    },
    requires_main=False,
)
async def file_write(path: str, content: str, append: bool = False, session_id: str = "agent:main") -> str:
    workspace = _resolve_workspace(session_id)
    safe = _safe_path(workspace, path)
    if safe is None:
        return "Error: path traversal or absolute path not allowed"
    try:
        safe.parent.mkdir(parents=True, exist_ok=True)
        if not append:
            safe.write_text(content, encoding="utf-8")
        else:
            with open(safe, "a", encoding="utf-8") as f:
                f.write(content)
        return f"Written {len(content)} chars to {path}"
    except Exception as e:
        return f"Error writing file: {e}"


@tool(
    name="file_list",
    description="List files in a directory within the session workspace.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "default": ".", "description": "Relative directory path (default: workspace root)"},
        },
    },
    requires_main=False,
)
async def file_list(path: str = ".", session_id: str = "agent:main") -> str:
    workspace = _resolve_workspace(session_id)
    safe = _safe_path(workspace, path)
    if safe is None:
        return "Error: path traversal or absolute path not allowed"
    if not safe.exists():
        return f"Error: directory not found: {path}"
    if not safe.is_dir():
        return f"Error: not a directory: {path}"
    try:
        entries = sorted(safe.iterdir(), key=lambda p: (p.is_file(), p.name))
        lines = []
        for entry in entries:
            kind = "FILE" if entry.is_file() else "DIR "
            size = entry.stat().st_size if entry.is_file() else "-"
            lines.append(f"{kind}  {entry.name}  ({size} bytes)")
        return "\n".join(lines) if lines else "(empty directory)"
    except Exception as e:
        return f"Error listing directory: {e}"


@tool(
    name="file_delete",
    description="Delete a file from the session workspace. Cannot delete directories.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Relative file path within workspace"},
        },
        "required": ["path"],
    },
    requires_main=False,
)
async def file_delete(path: str, session_id: str = "agent:main") -> str:
    workspace = _resolve_workspace(session_id)
    safe = _safe_path(workspace, path)
    if safe is None:
        return "Error: path traversal or absolute path not allowed"
    if not safe.exists():
        return f"Error: file not found: {path}"
    if safe.is_dir():
        return "Error: cannot delete directories"
    try:
        safe.unlink()
        return f"Deleted {path}"
    except Exception as e:
        return f"Error deleting file: {e}"
