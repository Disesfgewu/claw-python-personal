from __future__ import annotations
import logging
from dataclasses import dataclass
from typing import Callable, Awaitable
from claw.core.storage import Storage

logger = logging.getLogger(__name__)


@dataclass
class Command:
    name: str          # without leading /, e.g. "reset"
    description: str
    handler: Callable[..., Awaitable[str]]


class CommandRegistry:
    def __init__(self) -> None:
        self._commands: dict[str, Command] = {}

    def register(self, cmd: Command) -> None:
        self._commands[cmd.name] = cmd

    def parse(self, text: str) -> tuple[Command, str] | None:
        """If text starts with /name, return (command, args), else None."""
        text = text.strip()
        if not text.startswith("/"):
            return None
        parts = text[1:].split(None, 1)
        name = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""
        cmd = self._commands.get(name)
        if cmd is None:
            return None
        return cmd, args

    async def execute(self, session_id: str, text: str, storage: Storage) -> str | None:
        """Execute command and return response string; return None if not a command."""
        result = self.parse(text)
        if result is None:
            return None
        cmd, args = result
        try:
            return await cmd.handler(session_id=session_id, args=args, storage=storage)
        except Exception as e:
            logger.warning(f"command /{cmd.name} error: {e}")
            return f"Error: {e}"


_registry = CommandRegistry()


def command(name: str, description: str):
    """Decorator: register command."""
    def decorator(fn):
        _registry.register(Command(name=name, description=description, handler=fn))
        return fn
    return decorator


def get_command_registry() -> CommandRegistry:
    return _registry


# Built-in commands

@command("reset", "Clear current session message history")
async def _cmd_reset(session_id: str, args: str, storage: Storage) -> str:
    await storage.clear_messages(session_id)
    return "✅ Message history cleared."


@command("history", "Show last N messages (default 10)")
async def _cmd_history(session_id: str, args: str, storage: Storage) -> str:
    n = 10
    try:
        n = int(args.strip())
    except (ValueError, AttributeError):
        pass
    msgs = await storage.get_messages(session_id, limit=n)
    if not msgs:
        return "(No history)"
    lines = [f"[{m.role}] {m.content[:200]}" for m in msgs[-n:]]
    return "\n".join(lines)


@command("skills", "List loaded skills")
async def _cmd_skills(session_id: str, args: str, storage: Storage) -> str:
    from claw.skills.loader import load_skills
    from claw.core.config import get_config
    cfg = get_config()
    reg = load_skills(cfg.skills.dir)
    names = [s.manifest.name for s in reg.all()]
    if not names:
        return "(No loaded skills)"
    return "Loaded skills:\n" + "\n".join(f"- {n}" for n in sorted(names))
