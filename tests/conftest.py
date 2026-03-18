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
