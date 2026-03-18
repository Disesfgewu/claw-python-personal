import pytest

from claw.tools import registry
from claw.tools.bash import bash_tool


@pytest.mark.asyncio
async def test_registry_and_execute():
    saved = dict(registry._registry)
    registry._registry = {}

    @registry.tool(
        name="echo",
        description="echo",
        parameters={"type": "object", "properties": {}},
        requires_main=False,
    )
    async def echo_tool():
        return "ok"

    defs = registry.get_definitions(session_is_main=False)
    assert len(defs) == 1
    assert defs[0]["function"]["name"] == "echo"

    res = await registry.execute("echo", {}, session_is_main=False)
    assert res == "ok"

    res_unknown = await registry.execute("missing", {}, session_is_main=False)
    assert "unknown tool" in res_unknown
    registry._registry = saved


@pytest.mark.asyncio
async def test_registry_requires_main():
    saved = dict(registry._registry)
    registry._registry = {}

    @registry.tool(
        name="main_only",
        description="main only",
        parameters={"type": "object", "properties": {}},
        requires_main=True,
    )
    async def main_only():
        return "ok"

    defs = registry.get_definitions(session_is_main=False)
    assert defs == []

    res = await registry.execute("main_only", {}, session_is_main=False)
    assert "requires main" in res
    registry._registry = saved


@pytest.mark.asyncio
async def test_bash_tool():
    out = await bash_tool("echo hello")
    assert "hello" in out

    out_timeout = await bash_tool("sleep 2", timeout=1)
    assert "timed out" in out_timeout

    out_fail = await bash_tool("false")
    assert "[exit" in out_fail
