import pytest
from types import SimpleNamespace

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
    lines = [
        'data: {"choices":[{"delta":{"content":"hello"}}]}',
        'data: {"choices":[{"delta":{"content":" world"}}]}',
        'data: [DONE]',
    ]
    fake_client = FakeClient(lines)
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
    assert fake_client.calls[0]["json"]["stream"] is True
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
