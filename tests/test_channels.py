import pytest
import asyncio
from types import SimpleNamespace
from claw.channels.telegram import TelegramChannel

@pytest.mark.asyncio
async def test_telegram_error_handling_timeout():
    """on_message 在 timeout 時應發送友好錯誤訊息"""
    ch = TelegramChannel("token")

    async def mock_call_gateway(*args, **kwargs):
        raise asyncio.TimeoutError("Gateway timeout")

    ch._call_gateway = mock_call_gateway

    sent_messages = []

    async def mock_send_response(chat_id, text):
        sent_messages.append((chat_id, text))

    ch._send_response = mock_send_response

    # 模擬 on_message 呼叫
    update = SimpleNamespace(message=SimpleNamespace(
        text="test",
        chat=SimpleNamespace(id=123, type="private"),
        from_user=SimpleNamespace(id=456)
    ))

    await ch.on_message(update, None)

    # 驗證發送了錯誤訊息
    assert len(sent_messages) == 1
    assert sent_messages[0][0] == 123
    assert "timeout" in sent_messages[0][1].lower()
