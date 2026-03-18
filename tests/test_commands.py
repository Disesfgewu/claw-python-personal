import pytest
from claw.agent.commands import CommandRegistry, Command
from claw.core.storage import Storage, SessionRow, MessageRow, now_iso


@pytest.fixture
def reg():
    r = CommandRegistry()

    async def _reset(session_id, args, storage):
        await storage.clear_messages(session_id)
        return "cleared"

    async def _history(session_id, args, storage):
        n = int(args) if args.strip().isdigit() else 10
        msgs = await storage.get_messages(session_id, limit=n)
        return str(len(msgs))

    r.register(Command("reset", "clear", _reset))
    r.register(Command("history", "history", _history))
    return r


def test_command_parse_reset(reg):
    result = reg.parse("/reset")
    assert result is not None
    cmd, args = result
    assert cmd.name == "reset"
    assert args == ""


def test_command_parse_unknown(reg):
    assert reg.parse("hello world") is None
    assert reg.parse("/nonexistent") is None


@pytest.mark.asyncio
async def test_command_reset_clears_history(tmp_path, reg):
    storage = Storage(db_path=str(tmp_path / "claw.db"))
    storage.transcript_dir = str(tmp_path / "t")
    await storage.init()
    await storage.create_session(SessionRow(
        session_id="agent:main", scope="main", channel=None, agent_id="default",
        system_prompt=None, queue_mode="collect", sandbox=False,
        created_at=now_iso(), last_active=now_iso(), config={},
    ))
    await storage.add_message(MessageRow(
        session_id="agent:main", role="user", content="hi",
        tool_call_id=None, tool_name=None, created_at=now_iso()
    ))
    result = await reg.execute("agent:main", "/reset", storage)
    assert result == "cleared"
    msgs = await storage.get_messages("agent:main")
    assert msgs == []


@pytest.mark.asyncio
async def test_command_history(tmp_path, reg):
    storage = Storage(db_path=str(tmp_path / "claw.db"))
    storage.transcript_dir = str(tmp_path / "t")
    await storage.init()
    await storage.create_session(SessionRow(
        session_id="agent:main", scope="main", channel=None, agent_id="default",
        system_prompt=None, queue_mode="collect", sandbox=False,
        created_at=now_iso(), last_active=now_iso(), config={},
    ))
    result = await reg.execute("agent:main", "/history 3", storage)
    assert result is not None
