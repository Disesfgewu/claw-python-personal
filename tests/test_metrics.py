"""Tests for Prometheus metrics (claw.core.metrics)."""
import pytest


def test_metrics_module_imports():
    """All metric objects should be importable."""
    from claw.core.metrics import (
        agent_runs_total,
        tokens_used_total,
        tool_calls_total,
        egress_decisions_total,
        agent_run_duration_seconds,
        queue_depth,
        active_sessions,
        sandbox_containers,
        llm_errors_total,
    )
    assert agent_runs_total is not None
    assert tokens_used_total is not None


def test_metrics_endpoint_returns_prometheus_format(client):
    """GET /metrics should return 200 with Prometheus text format."""
    response = client.get("/metrics")
    assert response.status_code == 200
    # Prometheus text format starts with # HELP or metric lines
    content = response.text
    assert "claw_" in content or response.headers["content-type"].startswith("text/plain")


def test_record_agent_run_increments_counter():
    """record_agent_run() should increment the counter."""
    from claw.core.metrics import agent_runs_total, record_agent_run
    before = agent_runs_total.labels(session_id="test-sess", model="test")._value.get()
    record_agent_run(session_id="test-sess", model="test")
    after = agent_runs_total.labels(session_id="test-sess", model="test")._value.get()
    assert after == before + 1
