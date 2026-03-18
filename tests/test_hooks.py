import pytest

from claw.agent.hooks import HookRegistry


@pytest.mark.asyncio
async def test_register_and_fire():
    reg = HookRegistry()
    seen = []

    def handler(**kwargs):
        seen.append(kwargs["value"])

    reg.register("event", handler)
    await reg.fire("event", value=123)
    assert seen == [123]


@pytest.mark.asyncio
async def test_modifiable_hook_returns_value():
    reg = HookRegistry()

    def handler(**kwargs):
        return "new"

    reg.register("before_send", handler)
    out = await reg.fire("before_send", content="orig")
    assert out == "new"


@pytest.mark.asyncio
async def test_modifiable_hook_none_keeps_original():
    reg = HookRegistry()

    def handler(**kwargs):
        return None

    reg.register("before_send", handler)
    out = await reg.fire("before_send", content="orig")
    assert out == "orig"


@pytest.mark.asyncio
async def test_multiple_handlers_chain():
    reg = HookRegistry()
    seen = []

    def h1(**kwargs):
        return "a"

    def h2(**kwargs):
        seen.append(kwargs["content"])
        return "b"

    reg.register("before_send", h1)
    reg.register("before_send", h2)
    out = await reg.fire("before_send", content="orig")
    assert seen == ["a"]
    assert out == "b"


@pytest.mark.asyncio
async def test_handler_error_does_not_break():
    reg = HookRegistry()
    seen = []

    def bad(**kwargs):
        raise RuntimeError("boom")

    def ok(**kwargs):
        seen.append("ok")
        return "safe"

    reg.register("before_send", bad)
    reg.register("before_send", ok)
    out = await reg.fire("before_send", content="orig")
    assert seen == ["ok"]
    assert out == "safe"


@pytest.mark.asyncio
async def test_async_handler():
    reg = HookRegistry()

    async def h(**kwargs):
        return "async"

    reg.register("before_send", h)
    out = await reg.fire("before_send", content="orig")
    assert out == "async"


@pytest.mark.asyncio
async def test_no_handlers_returns_original():
    reg = HookRegistry()
    out = await reg.fire("before_send", content="orig")
    assert out == "orig"
