import pytest

import claw.core.config as config_module
from claw.core.config import ClawConfig, GatewayConfig
import claw.core.pairing as pairing
from claw.core.auth import verify_gateway_token


def _set_auth_token(token: str):
    cfg = ClawConfig()
    cfg.gateway = GatewayConfig(auth_token=token)
    config_module._config = cfg


def _reset_pairing():
    pairing._pending.clear()
    pairing._paired.clear()


def test_verify_gateway_token_empty_allows():
    _set_auth_token("")
    assert verify_gateway_token("") is True
    assert verify_gateway_token("anything") is True


def test_verify_gateway_token_match_and_mismatch():
    _set_auth_token("secret")
    assert verify_gateway_token("secret") is True
    assert verify_gateway_token("wrong") is False


def test_pairing_success():
    _reset_pairing()
    code = pairing.generate_code("agent:main")
    assert pairing.verify_code("agent:main", code, "peer1") is True
    assert pairing.is_paired("peer1") is True
    pairing.unpair("peer1")
    assert pairing.is_paired("peer1") is False


def test_pairing_expired_and_wrong_code(monkeypatch):
    _reset_pairing()
    monkeypatch.setattr(pairing.time, "time", lambda: 1000.0)
    code = pairing.generate_code("agent:main")

    # wrong code
    assert pairing.verify_code("agent:main", "000000", "peer1") is False

    # expired
    monkeypatch.setattr(pairing.time, "time", lambda: 1000.0 + pairing.PAIRING_CODE_TTL + 1)
    assert pairing.verify_code("agent:main", code, "peer1") is False
