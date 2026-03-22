"""
Integration tests for live API endpoints.
These tests require LIVE_BACKEND=1 environment variable and a running server.
Skipped by default during unit test runs.
"""
from __future__ import annotations

import os
import pytest

# Integration tests only run if LIVE_BACKEND=1
pytestmark = pytest.mark.skipif(
    os.getenv("LIVE_BACKEND") != "1",
    reason="Integration tests require LIVE_BACKEND=1 env var"
)


@pytest.mark.asyncio
async def test_chat_completions_endpoint():
    """POST /v1/chat/completions returns valid response."""
    # TODO: S6 實作 — 真實 API 測試
    pytest.skip("Awaiting Phase S6 implementation")


@pytest.mark.asyncio
async def test_stock_analysis_live():
    """Real stock analysis via POST /v1/chat/completions."""
    # TODO: S6 實作
    pytest.skip("Awaiting Phase S6 implementation")


@pytest.mark.asyncio
async def test_discord_pushback_live():
    """Real Discord message push (requires Discord token)."""
    # TODO: S6 實作
    pytest.skip("Awaiting Phase S6 implementation")
