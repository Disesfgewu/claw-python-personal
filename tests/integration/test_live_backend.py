from __future__ import annotations

import os
import pytest

# Integration tests only run if LIVE_BACKEND=1
pytestmark = pytest.mark.skipif(
    os.getenv("LIVE_BACKEND") != "1",
    reason="Integration tests require LIVE_BACKEND=1 env var"
)


@pytest.mark.asyncio
async def test_search_web_real_router():
    """Integration: search_web actually queries LLM-Router MCP endpoint."""
    # TODO: Implement when LLM-Router is running
    pytest.skip("Awaiting live router instance")


@pytest.mark.asyncio
async def test_embedding_real_router():
    """Integration: get_embedding queries Router /v1/embeddings."""
    # TODO: Implement when LLM-Router is running
    pytest.skip("Awaiting live router instance")


@pytest.mark.asyncio
async def test_image_gen_real_router():
    """Integration: image_gen queries Router /v1/images/generations."""
    # TODO: Implement when LLM-Router is running
    pytest.skip("Awaiting live router instance")
