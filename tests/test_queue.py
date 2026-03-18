import asyncio
import pytest

from claw.core.queue import MessageQueue, QueueMode


@pytest.mark.asyncio
async def test_queue_single_message():
    q = MessageQueue()
    events = []

    async def handler(session_id, user_message):
        events.append((session_id, user_message))

    await q.submit("s1", "hello", handler)
    await asyncio.sleep(0.05)
    assert events == [("s1", "hello")]


@pytest.mark.asyncio
async def test_queue_serial_execution():
    q = MessageQueue()
    events = []
    running = False

    async def handler(session_id, user_message):
        nonlocal running
        assert not running
        running = True
        await asyncio.sleep(0.05)
        events.append(user_message)
        running = False

    await q.submit("s1", "a", handler)
    await q.submit("s1", "b", handler)
    await asyncio.sleep(0.2)
    assert events == ["a", "b"]


@pytest.mark.asyncio
async def test_queue_drop_mode():
    q = MessageQueue()
    started = asyncio.Event()
    resume = asyncio.Event()

    async def handler(session_id, user_message):
        started.set()
        await resume.wait()

    await q.submit("s1", "a", handler, mode=QueueMode.DROP)
    await started.wait()
    queued = await q.submit("s1", "b", handler, mode=QueueMode.DROP)
    assert queued is False
    resume.set()
    await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_queue_collect_mode():
    q = MessageQueue()
    events = []
    started = asyncio.Event()
    resume = asyncio.Event()

    async def handler(session_id, user_message):
        if user_message == "a":
            started.set()
            await resume.wait()
        events.append(user_message)

    await q.submit("s1", "a", handler, mode=QueueMode.COLLECT)
    await started.wait()
    queued = await q.submit("s1", "b", handler, mode=QueueMode.COLLECT)
    assert queued is True
    resume.set()
    await asyncio.sleep(0.1)
    assert events == ["a", "b"]


@pytest.mark.asyncio
async def test_queue_followup_mode():
    q = MessageQueue()
    events = []
    started = asyncio.Event()
    resume = asyncio.Event()

    async def handler(session_id, user_message):
        if user_message == "a":
            started.set()
            await resume.wait()
        events.append(user_message)

    await q.submit("s1", "a", handler, mode=QueueMode.FOLLOWUP)
    await started.wait()
    queued = await q.submit("s1", "b", handler, mode=QueueMode.FOLLOWUP)
    assert queued is True
    resume.set()
    await asyncio.sleep(0.1)
    assert events == ["a", "b"]
