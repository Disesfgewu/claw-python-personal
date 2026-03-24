from __future__ import annotations

import logging
from contextvars import ContextVar
from typing import Any

import structlog

# Context variables for per-request log context
_session_id: ContextVar[str] = ContextVar("session_id", default="")
_agent_id: ContextVar[str] = ContextVar("agent_id", default="")

# Fields that must be redacted from logs
_REDACT_KEYS = frozenset({
    "token", "api_key", "apikey", "password", "secret",
    "authorization", "auth", "credential", "private_key",
})


def _redact_processor(logger, method, event_dict: dict) -> dict:
    """Redact sensitive fields from log events."""
    for key in list(event_dict.keys()):
        if key.lower() in _REDACT_KEYS:
            event_dict[key] = "***REDACTED***"
    return event_dict


def _add_session_context(logger, method, event_dict: dict) -> dict:
    """Inject session_id and agent_id from context vars."""
    sid = _session_id.get()
    aid = _agent_id.get()
    if sid:
        event_dict["session_id"] = sid
    if aid:
        event_dict["agent_id"] = aid
    return event_dict


def configure_logging(level: str = "INFO", fmt: str = "json") -> None:
    """
    Initialize structlog. Call once at startup in main.py.

    Args:
        level: Log level string (DEBUG/INFO/WARNING/ERROR)
        fmt: "json" for production, "text" for development
    """
    log_level = getattr(logging, level.upper(), logging.INFO)

    shared_processors: list[Any] = [
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.CallsiteParameterAdder(
            parameters=[
                structlog.processors.CallsiteParameter.MODULE,
                structlog.processors.CallsiteParameter.FUNC_NAME,
                structlog.processors.CallsiteParameter.LINENO,
            ]
        ),
        _add_session_context,
        _redact_processor,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if fmt == "json":
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=shared_processors + [renderer],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    logging.basicConfig(
        format="%(message)s",
        level=log_level,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Get a structlog logger by name."""
    return structlog.get_logger(name)


def set_session_context(session_id: str, agent_id: str = "") -> None:
    """Set session context for current async task (call at start of each request)."""
    _session_id.set(session_id)
    _agent_id.set(agent_id)


def clear_session_context() -> None:
    """Clear session context."""
    _session_id.set("")
    _agent_id.set("")
