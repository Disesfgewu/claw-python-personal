import pytest
from unittest.mock import MagicMock

telegram = pytest.importorskip("telegram", reason="python-telegram-bot not installed")

from claw.channels.telegram import TelegramChannel


def test_resolve_session_id_private():
    ch = TelegramChannel("fake_token", None, None, "http://fake", "")

    update = MagicMock()
    update.effective_chat.type = "private"
    update.effective_chat.id = 123

    session_id = ch._resolve_session_id(update)
    assert session_id == "agent:main"
    assert ch._session_to_chat["agent:main"] == 123


def test_resolve_session_id_group():
    ch = TelegramChannel("fake_token", None, None, "http://fake", "")

    update = MagicMock()
    update.effective_chat.type = "group"
    update.effective_chat.id = 456

    session_id = ch._resolve_session_id(update)
    assert session_id == "agent:tg:group:456"
    assert ch._session_to_chat["agent:tg:group:456"] == 456
