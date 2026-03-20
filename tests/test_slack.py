import pytest

pytest.importorskip("slack_bolt", reason="slack-bolt not installed")

from claw.channels.slack import SlackChannel


def test_slack_channel_init():
    ch = SlackChannel("xoxb-fake", "fake_secret", None)
    assert ch.app is not None


def test_slack_session_to_channel_mapping():
    ch = SlackChannel("xoxb-fake", "fake_secret", None)
    ch._session_to_channel["agent:slack:ch:C123"] = "C123"
    assert ch._session_to_channel.get("agent:slack:ch:C123") == "C123"
