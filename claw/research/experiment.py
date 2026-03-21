from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ExperimentStatus(str, Enum):
    KEEP    = "keep"
    DISCARD = "discard"
    CRASH   = "crash"


@dataclass
class ExperimentResult:
    task_id: str
    hypothesis: str
    approach: str
    output: str
    metric: float | None          # C層 eval_cmd 的數值結果，None = 未提供
    status: ExperimentStatus
    reasoning: str
    ts: str


@dataclass
class ResearchTask:
    task_id: str
    question: str
    criteria: str | None          # A層：用戶明確的成功標準
    eval_cmd: str | None          # C層：bash 命令，exit code 0 = 成功，或 stdout float
    status: str                   # "running" | "completed" | "stopped"
    max_experiments: int
    created_at: str
    completed_at: str | None = None
    experiments: list[ExperimentResult] = field(default_factory=list)
