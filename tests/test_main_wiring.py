from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_web_fetch_tool_registered():
    """web_fetch tool is registered after importing claw.tools.web_fetch."""
    import claw.tools.web_fetch  # noqa: F401
    from claw.tools.registry import get_tools
    tools = get_tools()
    assert any(t.name == "web_fetch" for t in tools), "web_fetch not registered"


@pytest.mark.asyncio
async def test_research_tools_registered():
    """research_start, experiment_record, research_status are registered."""
    import claw.tools.research_tools  # noqa: F401
    from claw.tools.registry import get_tools
    tools = get_tools()
    names = {t.name for t in tools}
    assert "research_start" in names
    assert "experiment_record" in names
    assert "research_status" in names


@pytest.mark.asyncio
async def test_file_tools_registered():
    """file_read, file_write, file_list, file_delete are registered."""
    import claw.tools.file_tools  # noqa: F401
    from claw.tools.registry import get_tools
    tools = get_tools()
    names = {t.name for t in tools}
    assert "file_read" in names
    assert "file_write" in names
    assert "file_list" in names
    assert "file_delete" in names
