"""Tests for SessionReaper (claw.core.session_reaper)."""
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock


@pytest.mark.asyncio
async def test_reaper_removes_expired_sessions():
    """Sessions older than TTL should be deleted."""
    from claw.core.session_reaper import SessionReaper

    old_time = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
    expired_session = MagicMock()
    expired_session.session_id = "expired-session"
    expired_session.last_active = old_time

    storage = MagicMock()
    storage.list_sessions = AsyncMock(return_value=[expired_session])
    storage.delete_session = AsyncMock()

    reaper = SessionReaper(storage=storage, ttl_hours=24)
    await reaper._reap()

    storage.delete_session.assert_called_once_with("expired-session")


@pytest.mark.asyncio
async def test_reaper_skips_active_sessions():
    """Recently active sessions should NOT be deleted."""
    from claw.core.session_reaper import SessionReaper

    recent_time = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    active_session = MagicMock()
    active_session.session_id = "active-session"
    active_session.last_active = recent_time

    storage = MagicMock()
    storage.list_sessions = AsyncMock(return_value=[active_session])
    storage.delete_session = AsyncMock()

    reaper = SessionReaper(storage=storage, ttl_hours=24)
    await reaper._reap()

    storage.delete_session.assert_not_called()
