"""
Shared fixtures for the test suite.
"""
import pytest
from claw.tools import registry


@pytest.fixture(autouse=True)
def restore_tool_registry():
    """Save and restore the tool registry around each test."""
    saved = dict(registry._registry)
    yield
    registry._registry = saved


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    import claw.core.gateway as gw
    from claw.core.storage import Storage
    from claw.core.queue import MessageQueue
    from unittest.mock import AsyncMock, MagicMock

    # Set up minimal mock dependencies so the gateway is usable in tests
    mock_storage = MagicMock(spec=Storage)
    mock_storage.db_path = "/tmp/test_claw_mock.db"
    mock_storage.list_sessions = AsyncMock(return_value=[])
    mock_storage.get_session = AsyncMock(return_value=None)
    mock_storage.delete_session = AsyncMock()

    gw.storage = mock_storage
    gw.queue = MessageQueue()
    gw.llm = MagicMock()
    from claw.core.gateway import app
    return TestClient(app)

