from __future__ import annotations

import pytest
from pathlib import Path
from unittest.mock import patch

from claw.tools.file_tools import file_read, file_write, file_list, file_delete


def _workspace_for(tmp_path: Path, session_id: str) -> Path:
    """Return patched workspace path."""
    safe_id = session_id.replace(":", "_")
    ws = tmp_path / ".claw" / "workspaces" / safe_id
    ws.mkdir(parents=True, exist_ok=True)
    return ws


@pytest.mark.asyncio
async def test_file_write_and_read(tmp_path):
    """Write a file, read it back, verify content."""
    session_id = "agent:main"
    ws = _workspace_for(tmp_path, session_id)

    with patch("claw.tools.file_tools._resolve_workspace", return_value=ws):
        write_result = await file_write("hello.txt", "Hello, claw!", session_id=session_id)
        read_result = await file_read("hello.txt", session_id=session_id)

    assert "Hello, claw!" in read_result
    assert "Error" not in write_result


@pytest.mark.asyncio
async def test_file_list(tmp_path):
    """Write 2 files, list directory, verify both appear."""
    session_id = "agent:main"
    ws = _workspace_for(tmp_path, session_id)

    with patch("claw.tools.file_tools._resolve_workspace", return_value=ws):
        await file_write("alpha.txt", "aaa", session_id=session_id)
        await file_write("beta.txt", "bbb", session_id=session_id)
        listing = await file_list(".", session_id=session_id)

    assert "alpha.txt" in listing
    assert "beta.txt" in listing


@pytest.mark.asyncio
async def test_file_delete(tmp_path):
    """Write then delete, verify file is gone."""
    session_id = "agent:main"
    ws = _workspace_for(tmp_path, session_id)

    with patch("claw.tools.file_tools._resolve_workspace", return_value=ws):
        await file_write("to_delete.txt", "bye", session_id=session_id)
        delete_result = await file_delete("to_delete.txt", session_id=session_id)
        read_result = await file_read("to_delete.txt", session_id=session_id)

    assert "Error" not in delete_result
    assert "not found" in read_result


@pytest.mark.asyncio
async def test_file_path_traversal_blocked(tmp_path):
    """Attempt ../secret path traversal, verify error."""
    session_id = "agent:main"
    ws = _workspace_for(tmp_path, session_id)

    with patch("claw.tools.file_tools._resolve_workspace", return_value=ws):
        result = await file_read("../secret", session_id=session_id)

    assert "Error" in result
    assert "traversal" in result.lower() or "not allowed" in result.lower()


@pytest.mark.asyncio
async def test_file_absolute_path_blocked(tmp_path):
    """Attempt /etc/passwd absolute path, verify error."""
    session_id = "agent:main"
    ws = _workspace_for(tmp_path, session_id)

    with patch("claw.tools.file_tools._resolve_workspace", return_value=ws):
        result = await file_read("/etc/passwd", session_id=session_id)

    assert "Error" in result
    assert "not allowed" in result.lower()
