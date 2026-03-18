import pytest

import claw.core.config as config_module
from claw.core.config import ClawConfig, SandboxConfig
from claw.sandbox.policy import needs_sandbox
from claw.tools import registry
import claw.tools.bash  # noqa: F401 - ensure bash tool is registered


def _set_sandbox_enabled(enabled: bool):
    cfg = ClawConfig()
    cfg.sandbox = SandboxConfig(enabled=enabled)
    config_module._config = cfg


def test_needs_sandbox_main():
    _set_sandbox_enabled(True)
    assert needs_sandbox("agent:main") is False
    assert needs_sandbox("agent:foo:main") is False


def test_needs_sandbox_non_main():
    _set_sandbox_enabled(True)
    assert needs_sandbox("agent:telegram:group:123") is True


def test_needs_sandbox_disabled():
    _set_sandbox_enabled(False)
    assert needs_sandbox("agent:main") is False
    assert needs_sandbox("agent:telegram:group:123") is False


@pytest.mark.asyncio
async def test_registry_execute_bash_host(monkeypatch):
    _set_sandbox_enabled(True)

    class FakeRunner:
        def __init__(self):
            self.calls = []

        async def run(self, session_id, command, timeout=None):
            self.calls.append((session_id, command, timeout))
            return "sandboxed"

    fake_runner = FakeRunner()
    monkeypatch.setattr(
        "claw.sandbox.docker_runner.get_runner", lambda: fake_runner
    )

    out = await registry.execute(
        "bash",
        {"command": "echo hello"},
        session_id="agent:main",
    )
    assert "hello" in out
    assert fake_runner.calls == []


@pytest.mark.asyncio
async def test_registry_execute_bash_sandbox(monkeypatch):
    _set_sandbox_enabled(True)

    class FakeRunner:
        def __init__(self):
            self.calls = []

        async def run(self, session_id, command, timeout=None):
            self.calls.append((session_id, command, timeout))
            return "sandboxed"

    fake_runner = FakeRunner()
    monkeypatch.setattr(
        "claw.sandbox.docker_runner.get_runner", lambda: fake_runner
    )

    out = await registry.execute(
        "bash",
        {"command": "echo hello"},
        session_id="agent:telegram:group:123",
    )
    assert out == "sandboxed"
    assert fake_runner.calls == [("agent:telegram:group:123", "echo hello", None)]
