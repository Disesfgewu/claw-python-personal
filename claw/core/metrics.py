from __future__ import annotations

from prometheus_client import (
    Counter,
    Histogram,
    Gauge,
    CollectorRegistry,
    generate_latest,
    CONTENT_TYPE_LATEST,
)

# Use a dedicated registry (not the default global)
# to avoid conflicts in tests
REGISTRY = CollectorRegistry()

# ── Counters ────────────────────────────────────────────────────────────

agent_runs_total = Counter(
    "claw_agent_runs_total",
    "Total agent run requests",
    ["session_id", "model"],
    registry=REGISTRY,
)

tokens_used_total = Counter(
    "claw_tokens_used_total",
    "Total LLM tokens consumed",
    ["type"],  # prompt / completion
    registry=REGISTRY,
)

tool_calls_total = Counter(
    "claw_tool_calls_total",
    "Total tool calls executed",
    ["tool_name", "verdict"],  # verdict: success / error / egress_denied
    registry=REGISTRY,
)

egress_decisions_total = Counter(
    "claw_egress_decisions_total",
    "Egress policy decisions",
    ["verdict"],  # allow / deny / pending
    registry=REGISTRY,
)

llm_errors_total = Counter(
    "claw_llm_errors_total",
    "Total LLM router errors",
    ["error_type"],
    registry=REGISTRY,
)

# ── Histograms ───────────────────────────────────────────────────────────

agent_run_duration_seconds = Histogram(
    "claw_agent_run_duration_seconds",
    "Agent run duration in seconds",
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0],
    registry=REGISTRY,
)

# ── Gauges ───────────────────────────────────────────────────────────────

queue_depth = Gauge(
    "claw_queue_depth",
    "Current number of items in message queue",
    registry=REGISTRY,
)

active_sessions = Gauge(
    "claw_active_sessions",
    "Number of active sessions",
    registry=REGISTRY,
)

sandbox_containers = Gauge(
    "claw_sandbox_containers",
    "Number of active sandbox containers",
    registry=REGISTRY,
)


# ── Helper functions ──────────────────────────────────────────────────────

def record_agent_run(session_id: str, model: str) -> None:
    agent_runs_total.labels(session_id=session_id, model=model).inc()


def record_tool_call(tool_name: str, verdict: str = "success") -> None:
    tool_calls_total.labels(tool_name=tool_name, verdict=verdict).inc()


def record_egress_decision(verdict: str) -> None:
    egress_decisions_total.labels(verdict=verdict).inc()


def record_tokens(prompt_tokens: int, completion_tokens: int) -> None:
    if prompt_tokens:
        tokens_used_total.labels(type="prompt").inc(prompt_tokens)
    if completion_tokens:
        tokens_used_total.labels(type="completion").inc(completion_tokens)


def get_metrics_output() -> tuple[bytes, str]:
    """Return (content, content_type) for /metrics endpoint."""
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST
