import json
import os
import pytest

from claw.core.storage import Storage, SessionRow, MessageRow, now_iso


@pytest.mark.asyncio
async def test_storage_session_and_messages(tmp_path):
    storage = Storage(db_path=str(tmp_path / "claw.db"))
    storage.transcript_dir = str(tmp_path / "transcripts")
    await storage.init()

    session = SessionRow(
        session_id="agent:main",
        scope="main",
        channel=None,
        agent_id="default",
        system_prompt=None,
        queue_mode="collect",
        sandbox=False,
        created_at=now_iso(),
        last_active=now_iso(),
        config={"a": 1},
    )
    await storage.create_session(session)

    got = await storage.get_session("agent:main")
    assert got is not None
    assert got.session_id == "agent:main"
    assert got.config == {"a": 1}

    await storage.add_message(MessageRow(
        session_id="agent:main",
        role="user",
        content="hello",
        created_at=now_iso(),
    ))
    await storage.add_message(MessageRow(
        session_id="agent:main",
        role="assistant",
        content=[{"type": "text", "text": "hi"}],
        created_at=now_iso(),
    ))

    msgs = await storage.get_messages("agent:main", limit=10)
    assert len(msgs) == 2
    assert msgs[0].role == "user"
    assert msgs[1].role == "assistant"
    assert isinstance(msgs[1].content, list)

    storage.append_transcript("agent:main", {"type": "user_message", "content": "x"})
    transcript_path = os.path.join(storage.transcript_dir, "agent_main.jsonl")
    assert os.path.exists(transcript_path)
    with open(transcript_path, "r", encoding="utf-8") as f:
        line = f.readline().strip()
        data = json.loads(line)
        assert data["type"] == "user_message"

    await storage.delete_session("agent:main")
    assert await storage.get_session("agent:main") is None
    assert await storage.get_messages("agent:main") == []
