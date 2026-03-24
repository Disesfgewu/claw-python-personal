import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
import sys
import types

import claw.channels.telegram as telegram_module
from claw.channels.telegram import TelegramChannel


class FakeResponse:
    def __init__(self, lines):
        self._lines = lines

    def raise_for_status(self):
        return None

    async def aiter_lines(self):
        for line in self._lines:
            yield line


class FakeStream:
    def __init__(self, response):
        self._response = response

    async def __aenter__(self):
        return self._response

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakeClient:
    def __init__(self, lines):
        self._lines = lines
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def stream(self, method, url, json=None, timeout=None):
        self.calls.append({"method": method, "url": url, "json": json})
        return FakeStream(FakeResponse(self._lines))


def _make_update(chat_type: str, chat_id: int, user_id: int, text: str = "hi"):
    return SimpleNamespace(
        message=SimpleNamespace(
            text=text,
            chat=SimpleNamespace(type=chat_type, id=chat_id),
            from_user=SimpleNamespace(id=user_id),
        )
    )


def _install_fake_telegram(monkeypatch, mock_app):
    telegram_mod = types.ModuleType("telegram")
    ext_mod = types.ModuleType("telegram.ext")

    class DummyFilters:
        TEXT = 1
        PHOTO = 2

        class Document:
            ALL = 4

    class DummyMessageHandler:
        def __init__(self, *args, **kwargs):
            pass

    class DummyBuilder:
        def __init__(self, app):
            self._app = app

        def token(self, token):
            return self

        def build(self):
            return self._app

    class DummyApplication:
        @classmethod
        def builder(cls):
            return DummyBuilder(mock_app)

    ext_mod.Application = DummyApplication
    ext_mod.MessageHandler = DummyMessageHandler
    ext_mod.filters = DummyFilters
    telegram_mod.ext = ext_mod

    monkeypatch.setitem(sys.modules, "telegram", telegram_mod)
    monkeypatch.setitem(sys.modules, "telegram.ext", ext_mod)


def test_telegram_private_message_session_id():
    ch = TelegramChannel("token")
    update = _make_update("private", 111, 222)
    assert ch._get_session_id(update) == "agent:tg:user:222"


def test_telegram_group_message_session_id():
    ch = TelegramChannel("token")
    update = _make_update("group", 111, 222)
    assert ch._get_session_id(update) == "agent:tg:group:111"


@pytest.mark.asyncio
async def test_telegram_on_message_posts_to_gateway(monkeypatch):
    class FakePostResponse:
        def raise_for_status(self): pass
        def json(self):
            return {"choices": [{"message": {"content": "hello world"}}]}
    class FakeClient:
        def __init__(self):
            self.calls = []
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def post(self, url, json=None, timeout=None):
            self.calls.append({"url": url, "json": json})
            return FakePostResponse()
    fake_client = FakeClient()
    monkeypatch.setattr(telegram_module.httpx, "AsyncClient", lambda: fake_client)

    ch = TelegramChannel("token", base_url="http://base")
    sent = []

    async def fake_send(chat_id, text):
        sent.append((chat_id, text))

    monkeypatch.setattr(ch, "_send_response", fake_send)

    update = _make_update("private", 999, 123, text="ping")
    await ch.on_message(update, None)

    assert fake_client.calls[0]["url"] == "http://base/v1/chat/completions"
    assert fake_client.calls[0]["json"]["session_id"] == "agent:tg:user:123"
    assert fake_client.calls[0]["json"]["messages"] == [{"role": "user", "content": "ping"}]
    assert fake_client.calls[0]["json"]["stream"] is False
    assert sent == [(999, "hello world")]


@pytest.mark.asyncio
async def test_telegram_send_response_throttle(monkeypatch):
    ch = TelegramChannel("token")
    sent = []
    sleeps = []

    async def fake_send(chat_id, text):
        sent.append((chat_id, text))

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr(ch, "_bot_send_message", fake_send)
    monkeypatch.setattr(telegram_module.asyncio, "sleep", fake_sleep)

    long_text = "a" * 5000
    await ch._send_response(42, long_text)

    assert len(sent) == 2
    assert sent[0][1] == "a" * 4096
    assert sent[1][1] == "a" * (5000 - 4096)
    assert sleeps == [0.5, 0.5]


@pytest.mark.asyncio
async def test_telegram_start_with_polling_enabled(monkeypatch):
    """start() 在 polling=True 且 updater 存在時應調用 start_polling()"""
    mock_updater = AsyncMock()
    mock_app = AsyncMock()
    mock_app.updater = mock_updater
    mock_app.add_handler = MagicMock()

    _install_fake_telegram(monkeypatch, mock_app)

    ch = TelegramChannel("test_token", polling=True)
    await ch.start()

    mock_updater.start_polling.assert_called_once()
