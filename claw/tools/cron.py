from __future__ import annotations
from claw.tools.registry import tool

_cron_service = None  # Set by main.py via set_cron_service()


def set_cron_service(svc) -> None:
    global _cron_service
    _cron_service = svc


@tool(
    name="cron_add",
    description="Add a scheduled task. schedule is 5-field cron expression (e.g. '0 9 * * 1-5' = Mon-Fri 9am). prompt is the message sent to agent when triggered.",
    parameters={
        "type": "object",
        "properties": {
            "schedule": {"type": "string", "description": "Cron expression (5 fields)"},
            "prompt":   {"type": "string", "description": "Command to execute when triggered"},
        },
        "required": ["schedule", "prompt"],
    },
    requires_main=True,
)
async def cron_add(schedule: str, prompt: str) -> str:
    if _cron_service is None:
        return "Error: CronService not initialized"
    from claw.cron.schedule import next_run_dt
    try:
        next_r = next_run_dt(schedule)
    except Exception as e:
        return f"Error: invalid cron expression: {e}"
    job = await _cron_service.add_job("agent:main", schedule, prompt)
    return f"✅ Schedule created id={job.id}, next run: {next_r.isoformat()}"


@tool(
    name="cron_list",
    description="List all scheduled tasks.",
    parameters={"type": "object", "properties": {}},
    requires_main=True,
)
async def cron_list() -> str:
    if _cron_service is None:
        return "Error: CronService not initialized"
    jobs = await _cron_service.list_jobs()
    if not jobs:
        return "(No scheduled tasks)"
    lines = [f"id={j.id[:8]} schedule={j.schedule} prompt={j.prompt!r} last={j.last_run}" for j in jobs]
    return "\n".join(lines)


@tool(
    name="cron_delete",
    description="Delete scheduled task (by id prefix or full id).",
    parameters={
        "type": "object",
        "properties": {
            "job_id": {"type": "string", "description": "Job ID or first 8 chars"}
        },
        "required": ["job_id"],
    },
    requires_main=True,
)
async def cron_delete(job_id: str) -> str:
    if _cron_service is None:
        return "Error: CronService not initialized"
    jobs = await _cron_service.list_jobs()
    matched = [j for j in jobs if j.id.startswith(job_id)]
    if not matched:
        return f"Error: job {job_id!r} not found"
    for j in matched:
        await _cron_service.remove_job(j.id)
    return f"✅ Deleted {len(matched)} scheduled task(s)."
