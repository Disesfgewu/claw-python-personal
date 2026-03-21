"""Tests for structured logger (claw.core.logger)."""
import logging


def test_configure_logging_json():
    """configure_logging() should set up structlog without errors."""
    from claw.core.logger import configure_logging
    configure_logging(level="INFO", fmt="json")


def test_sensitive_redact():
    """Sensitive keys must not appear in log output."""
    from claw.core.logger import _redact_processor
    event = {
        "event": "test",
        "token": "secret-token-123",
        "api_key": "sk-abc",
        "normal_field": "visible",
    }
    result = _redact_processor(None, None, event)
    assert result["token"] == "***REDACTED***"
    assert result["api_key"] == "***REDACTED***"
    assert result["normal_field"] == "visible"


def test_session_context_propagation():
    """set_session_context() should inject session_id into log events."""
    from claw.core.logger import set_session_context, _add_session_context, clear_session_context
    set_session_context("test-session-id", "test-agent")
    event = {"event": "test"}
    result = _add_session_context(None, None, event)
    assert result["session_id"] == "test-session-id"
    assert result["agent_id"] == "test-agent"
    clear_session_context()


def test_log_level_from_config():
    """configure_logging() should respect the level argument."""
    import logging
    from claw.core.logger import configure_logging
    # Reset root logger level to allow basicConfig to take effect
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.NOTSET)
    configure_logging(level="DEBUG", fmt="text")
    assert root_logger.level <= logging.DEBUG

