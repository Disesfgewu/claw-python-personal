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


def test_sandbox_policy_from_blueprint():
    from claw.sandbox.policy import SandboxPolicy
    from config.blueprint import Blueprint
    bp = Blueprint(sandbox_memory_mb=512, sandbox_tmp_mb=64, sandbox_cpus=2.0)
    policy = SandboxPolicy.from_blueprint(bp)
    assert policy.memory_limit_mb == 512
    assert policy.tmp_size_mb == 64
    assert policy.cpus == 2.0


def test_seccomp_json_valid():
    import json
    from pathlib import Path
    p = Path("claw/sandbox/seccomp_minimal.json")
    assert p.exists()
    data = json.loads(p.read_text())
    assert data["defaultAction"] == "SCMP_ACT_ERRNO"
    assert len(data["syscalls"][0]["names"]) > 20
