import pytest
from datetime import datetime, timezone
from claw.cron.store import CronStore
from claw.cron.schedule import next_run_dt


@pytest.mark.asyncio
async def test_cron_store_add_list_delete(tmp_path):
    store = CronStore(str(tmp_path / "claw.db"))
    await store.init()
    job = await store.add("agent:main", "0 9 * * 1-5", "daily report")
    assert job.id
    jobs = await store.list()
    assert any(j.id == job.id for j in jobs)
    await store.delete(job.id)
    jobs = await store.list()
    assert not any(j.id == job.id for j in jobs)


def test_cron_next_run():
    dt = next_run_dt("0 9 * * 1-5")
    assert isinstance(dt, datetime)
    assert dt.tzinfo is not None
    assert dt > datetime.now(timezone.utc)


def test_cron_tools_require_main():
    import claw.tools.cron  # noqa: F401 — triggers @tool decorator registration
    from claw.tools import registry as tool_registry
    defs = tool_registry.get_definitions(session_is_main=False)
    names = [d["function"]["name"] for d in defs]
    assert "cron_add" not in names

