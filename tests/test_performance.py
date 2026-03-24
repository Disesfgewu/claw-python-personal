"""Performance benchmarks for critical paths."""
from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class DummyStore:
    def __init__(self):
        self.search_cache = {}
        self.cache_ttl_seconds = 300

    def _get_cached_results(self, cache_key: str):
        entry = self.search_cache.get(cache_key)
        if not entry:
            return None
        return entry[1]

    def _set_cached_results(self, cache_key: str, results):
        self.search_cache[cache_key] = (time.time(), results)

    async def vector_search(self, query_emb, session_id, limit):
        return []

    async def fts_search(self, query, session_id, limit):
        return []


@pytest.mark.asyncio
async def test_memory_search_performance():
    """Memory search should complete in < 100ms."""
    from claw.memory.manager import MemoryManager

    mock_llm = MagicMock()
    mock_llm.get_embedding = AsyncMock(return_value=[0.0] * 768)
    store = DummyStore()
    mgr = MemoryManager(store=store, llm=mock_llm)

    start = time.time()
    for _ in range(100):
        await mgr.search("test")
    elapsed = time.time() - start

    assert elapsed < 0.1, f"Memory search too slow: {elapsed:.3f}s"


@pytest.mark.asyncio
async def test_stock_fetch_performance():
    """Stock fetch with cache should complete in < 500ms."""
    from claw.tools import stock_tools
    from claw.tools.stock_tools import stock_fetch_data_sync

    stock_tools._stock_data_cache.clear()

    with patch("claw.tools.stock_tools._stock_fetch_impl") as mock_fetch:
        mock_fetch.return_value = {"ohlcv": []}

        start = time.time()
        result = stock_fetch_data_sync("2330", use_cache=True)
        elapsed = time.time() - start

        assert elapsed < 0.5, f"Stock fetch too slow: {elapsed:.3f}s"
        assert result.get("ohlcv") == []


@pytest.mark.asyncio
async def test_tool_dispatch_performance():
    """Tool dispatch should complete in < 50ms."""
    from claw.tools.registry import get_tools

    start = time.time()
    tools = get_tools()
    elapsed = time.time() - start

    assert elapsed < 0.05, f"Tool lookup too slow: {elapsed:.3f}s"
    assert len(tools) >= 28, f"Expected 28+ tools, got {len(tools)}"
