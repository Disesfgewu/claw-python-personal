import pytest
from claw.agent.context import ContextBuilder


def test_count_tokens():
    ctx = ContextBuilder()
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Hello, how are you?"},
    ]
    count = ctx.count_tokens(messages)
    # Should be > 0 when tiktoken is available; 0 if fallback
    assert count >= 0


def test_count_tokens_nonzero_when_tiktoken_available():
    ctx = ContextBuilder()
    if ctx.encoder is None:
        pytest.skip("tiktoken not available")
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Hello, how are you?"},
    ]
    count = ctx.count_tokens(messages)
    assert count > 0


def test_head_tail_compaction():
    ctx = ContextBuilder(max_tokens=50)
    if ctx.encoder is None:
        pytest.skip("tiktoken not available")

    messages = [{"role": "system", "content": "sys"}]
    # Each message has ~250 tokens (250 'a's), 30 of them → well above 50 tokens
    messages += [{"role": "user", "content": "a" * 250} for _ in range(30)]

    compacted = ctx.compact_if_needed(messages)
    # Should have been compacted: system + 20 tail
    assert len(compacted) < len(messages)
    assert compacted[0]["role"] == "system"


def test_no_compaction_when_under_limit():
    ctx = ContextBuilder(max_tokens=100_000)
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Hello."},
    ]
    result = ctx.compact_if_needed(messages)
    assert result == messages


import json
from claw.core.storage import Storage, SessionRow, MessageRow
from claw.agent.context import build_context
from claw.core.storage import now_iso


@pytest.mark.asyncio
async def test_build_context_applies_compaction(tmp_path):
    """訊息過多時，build_context 應觸發 ContextBuilder 壓縮。"""
    storage = Storage(str(tmp_path / "claw.db"))
    await storage.init()
    await storage.create_session(SessionRow(
        session_id="s1", scope="main", channel=None, agent_id="default",
        system_prompt=None, queue_mode="collect", sandbox=False,
        created_at=now_iso(), last_active=now_iso(),
    ))
    # 插入 45 則每則 300 字的訊息（遠超 50 token 限制）
    for i in range(45):
        await storage.add_message(MessageRow(
            session_id="s1",
            role="user" if i % 2 == 0 else "assistant",
            content="a" * 300,
            created_at=now_iso(),
        ))

    # max_tokens=50 強制觸發壓縮
    builder = ContextBuilder(max_tokens=50)
    if builder.encoder is None:
        pytest.skip("tiktoken not available")

    msgs = await build_context(storage, "s1", "new question", context_builder=builder)
    # 壓縮後不超過 system(0) + 20 tail + 1 new user = 21
    assert len(msgs) <= 22
    # 最後一則必定是新的 user message
    assert msgs[-1].role == "user"
    assert msgs[-1].content == "new question"
