from __future__ import annotations

import json
from claw.tools.registry import tool

# Set by main.py via set_research_loop()
_loop = None


def set_research_loop_ref(loop) -> None:
    global _loop
    _loop = loop


@tool(
    name="research_start",
    description=(
        "Start an autonomous research loop on a complex question. "
        "The agent will decompose the question, run experiments iteratively, "
        "and stop when success criteria are met or max experiments reached."
    ),
    parameters={
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "The complex research question or task to investigate",
            },
            "criteria": {
                "type": "string",
                "description": "Optional: explicit success criteria string (A-layer). "
                               "If provided, loop stops when LLM confirms this is satisfied.",
            },
            "eval_cmd": {
                "type": "string",
                "description": "Optional: bash command to run after each experiment (C-layer). "
                               "Exit code 0 = success, or stdout float (lower=better).",
            },
            "max_experiments": {
                "type": "integer",
                "default": 20,
                "description": "Maximum number of experiments before stopping (default: 20)",
            },
        },
        "required": ["question"],
    },
    requires_main=True,
)
async def research_start(
    question: str,
    criteria: str = "",
    eval_cmd: str = "",
    max_experiments: int = 20,
    session_id: str = "agent:main",
) -> str:
    from claw.research.loop import get_research_loop
    loop = get_research_loop()
    if loop is None:
        return "Error: ResearchLoop not initialized. Call set_research_loop() in main.py."

    task_id = await loop.ledger.create_task(
        question=question,
        criteria=criteria or None,
        eval_cmd=eval_cmd or None,
        max_experiments=max_experiments,
    )
    return (
        f"Research task started.\n"
        f"task_id: {task_id}\n"
        f"question: {question}\n"
        f"criteria: {criteria or '(none — LLM self-evaluation)'}\n"
        f"eval_cmd: {eval_cmd or '(none)'}\n"
        f"max_experiments: {max_experiments}\n"
        f"Use research_status(task_id='{task_id}') to monitor progress."
    )


@tool(
    name="experiment_record",
    description="Record the result of a research experiment within an active research loop.",
    parameters={
        "type": "object",
        "properties": {
            "task_id": {"type": "string", "description": "The research task ID"},
            "hypothesis": {"type": "string", "description": "The hypothesis that was tested"},
            "approach": {"type": "string", "description": "The approach/method used"},
            "output": {"type": "string", "description": "The experiment output/findings"},
            "status": {
                "type": "string",
                "enum": ["keep", "discard", "crash"],
                "description": "keep=useful finding, discard=not useful, crash=execution failed",
            },
            "reasoning": {"type": "string", "description": "Why this status was assigned"},
        },
        "required": ["task_id", "hypothesis", "approach", "output", "status", "reasoning"],
    },
    requires_main=False,
)
async def experiment_record(
    task_id: str,
    hypothesis: str,
    approach: str,
    output: str,
    status: str,
    reasoning: str,
    session_id: str = "agent:main",
) -> str:
    from claw.research.ledger import ResearchLedger
    from claw.research.experiment import ExperimentResult, ExperimentStatus
    from claw.core.storage import DB_PATH
    from datetime import datetime, timezone

    try:
        exp_status = ExperimentStatus(status)
    except ValueError:
        return f"Error: invalid status '{status}'. Must be keep/discard/crash."

    ledger = ResearchLedger(DB_PATH)
    result = ExperimentResult(
        task_id=task_id,
        hypothesis=hypothesis,
        approach=approach,
        output=output,
        metric=None,
        status=exp_status,
        reasoning=reasoning,
        ts=datetime.now(timezone.utc).isoformat(),
    )
    await ledger.record_experiment(result)
    return f"✅ Experiment recorded [{status.upper()}] for task {task_id}"


@tool(
    name="research_status",
    description="Check the status of a research task, or list all running tasks.",
    parameters={
        "type": "object",
        "properties": {
            "task_id": {
                "type": "string",
                "description": "Optional: specific task ID to inspect. Omit to list all running tasks.",
            },
        },
    },
    requires_main=True,
)
async def research_status(
    task_id: str = "",
    session_id: str = "agent:main",
) -> str:
    from claw.research.ledger import ResearchLedger
    from claw.core.storage import DB_PATH

    ledger = ResearchLedger(DB_PATH)

    if task_id:
        task = await ledger.get_task(task_id)
        if task is None:
            return f"Error: task not found: {task_id}"
        kept = [e for e in task.experiments if e.status.value == "keep"]
        lines = [
            f"Task: {task.task_id}",
            f"Status: {task.status}",
            f"Question: {task.question}",
            f"Criteria: {task.criteria or '(LLM self-evaluation)'}",
            f"Experiments: {len(task.experiments)} total, {len(kept)} kept",
            "",
            "Recent experiments:",
        ]
        for e in task.experiments[-5:]:
            lines.append(f"  [{e.status.value.upper()}] {e.hypothesis[:60]}... — {e.reasoning[:80]}")
        return "\n".join(lines)

    # List all running tasks
    tasks = await ledger.list_running_tasks()
    if not tasks:
        return "(No running research tasks)"
    lines = ["Running research tasks:"]
    for t in tasks:
        lines.append(f"  {t.task_id}: {t.question[:80]}...")
    return "\n".join(lines)
