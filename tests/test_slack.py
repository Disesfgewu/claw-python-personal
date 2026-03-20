import pytest

import claw.channels.slack as slack_module
from claw.channels.slack import SlackChannel


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


def test_slack_dm_session_id():
    ch = SlackChannel("xoxb", "xapp")
    event = {"channel": "D123", "user": "U1"}
    assert ch._get_session_id(event) == "agent:slack:dm:U1"


def test_slack_channel_mention_session_id():
    ch = SlackChannel("xoxb", "xapp")
    event = {"channel": "C123", "user": "U1"}
    assert ch._get_session_id(event) == "agent:slack:channel:C123"


@pytest.mark.asyncio
async def test_slack_on_mention_posts_to_gateway(monkeypatch):
    lines = [
        'data: {"choices":[{"delta":{"content":"hi"}}]}',
        'data: {"choices":[{"delta":{"content":" there"}}]}',
        'data: [DONE]',
    ]
    fake_client = FakeClient(lines)
    monkeypatch.setattr(slack_module.httpx, "AsyncClient", lambda: fake_client)

    ch = SlackChannel("xoxb", "xapp", base_url="http://base")
    sent = []

    async def fake_send(channel, text, thread_ts=None):
        sent.append((channel, text, thread_ts))

    monkeypatch.setattr(ch, "_send_response", fake_send)

    event = {"channel": "C111", "user": "U222", "text": "ping"}
    await ch._on_app_mention(event)

    assert fake_client.calls[0]["url"] == "http://base/v1/chat/completions"
    assert fake_client.calls[0]["json"]["session_id"] == "agent:slack:channel:C111"
    assert fake_client.calls[0]["json"]["messages"] == [{"role": "user", "content": "ping"}]
    assert fake_client.calls[0]["json"]["stream"] is True
    assert sent == [("C111", "hi there", None)]


@pytest.mark.asyncio
async def test_slack_thread_reply():
    ch = SlackChannel("xoxb", "xapp")
    calls = []

    async def fake_send(channel, text, thread_ts=None):
        calls.append((channel, text, thread_ts))

    ch._client_send_message = fake_send
    await ch._send_response("C1", "hello", thread_ts="123.45")

    assert calls == [("C1", "hello", "123.45")]
