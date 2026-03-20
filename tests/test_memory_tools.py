"""
tests/test_memory_tools.py — memory_save / memory_search 工具測試
"""
import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.mark.asyncio
async def test_memory_tools_not_initialized():
    """MemoryManager 未初始化時應回傳 Error 字串。"""
    from claw.tools import memory_tools
    memory_tools.set_memory_manager(None)

    result = await memory_tools.memory_save("some content", "[]", session_id="agent:main")
    assert "Error" in result

    result2 = await memory_tools.memory_search("query", 5, session_id="agent:main")
    assert "Error" in result2


@pytest.mark.asyncio
async def test_memory_save_calls_manager(tmp_path):
    """memory_save 應呼叫 MemoryManager.save() 並回傳 memory id。"""
    from claw.tools import memory_tools

    mock_mm = MagicMock()
    mock_mm.save = AsyncMock(return_value="abc12345-0000-0000-0000-000000000000")
    memory_tools.set_memory_manager(mock_mm)

    result = await memory_tools.memory_save(
        "test content", '["tag1"]', session_id="agent:main"
    )
    assert "abc12345" in result
    mock_mm.save.assert_called_once()
    call_kwargs = mock_mm.save.call_args
    assert call_kwargs[0][1] == "test content"  # content 是第 2 個位置參數


@pytest.mark.asyncio
async def test_memory_search_returns_results():
    """memory_search 有結果時應回傳格式化字串。"""
    from claw.tools import memory_tools
    from datetime import datetime, timezone

    mock_mm = MagicMock()
    mock_mm.search = AsyncMock(return_value=[
        {
            "id": "id1",
            "content": "important meeting notes",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "score": 0.85,
        }
    ])
    memory_tools.set_memory_manager(mock_mm)

    result = await memory_tools.memory_search("meeting", 5, session_id="agent:main")
    assert "important meeting notes" in result
    assert "0.85" in result


@pytest.mark.asyncio
async def test_memory_search_empty_results():
    """memory_search 無結果時應回傳 No relevant memory。"""
    from claw.tools import memory_tools

    mock_mm = MagicMock()
    mock_mm.search = AsyncMock(return_value=[])
    memory_tools.set_memory_manager(mock_mm)

    result = await memory_tools.memory_search("nothing", 5, session_id="agent:main")
    assert "No relevant" in result
