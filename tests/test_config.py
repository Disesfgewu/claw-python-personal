import os

import claw.core.config as config


def _reset_singleton():
    config._config = None


def _clear_env(monkeypatch):
    for key in [
        "LLM_ROUTER_URL",
        "LLM_ROUTER_API_KEY",
        "CLAW_HOST",
        "CLAW_PORT",
        "CLAW_AUTH_TOKEN",
        "CLAW_DATA_DIR",
    ]:
        monkeypatch.delenv(key, raising=False)


def test_default_values_when_yaml_missing(monkeypatch, tmp_path):
    _reset_singleton()
    _clear_env(monkeypatch)
    missing = tmp_path / "nope.yaml"
    cfg = config.load_config(path=str(missing))

    assert cfg.gateway.host == "127.0.0.1"
    assert cfg.gateway.port == 18790
    assert cfg.gateway.auth_token == ""
    assert cfg.llm_router.url == "http://127.0.0.1:8000"
    assert cfg.llm_router.api_key == ""


def test_yaml_overrides(monkeypatch, tmp_path):
    _reset_singleton()
    _clear_env(monkeypatch)
    path = tmp_path / "cfg.yaml"
    path.write_text(
        "\n".join(
            [
                "gateway:",
                "  host: \"0.0.0.0\"",
                "  port: 9999",
                "llm_router:",
                "  url: \"http://example.com:1234\"",
                "sandbox:",
                "  enabled: false",
            ]
        ),
        encoding="utf-8",
    )

    cfg = config.load_config(path=str(path))
    assert cfg.gateway.host == "0.0.0.0"
    assert cfg.gateway.port == 9999
    assert cfg.llm_router.url == "http://example.com:1234"
    assert cfg.sandbox.enabled is False


def test_env_overrides_yaml(monkeypatch, tmp_path):
    _reset_singleton()
    path = tmp_path / "cfg.yaml"
    path.write_text(
        "\n".join(
            [
                "gateway:",
                "  host: \"1.2.3.4\"",
                "  port: 1111",
                "  auth_token: \"from_yaml\"",
                "llm_router:",
                "  url: \"http://yaml\"",
                "  api_key: \"yaml\"",
                "storage:",
                "  db_path: \"/tmp/yaml.db\"",
                "  transcript_dir: \"/tmp/yaml_transcripts\"",
            ]
        ),
        encoding="utf-8",
    )

    data_dir = tmp_path / "data"
    monkeypatch.setenv("LLM_ROUTER_URL", "http://env")
    monkeypatch.setenv("LLM_ROUTER_API_KEY", "env_key")
    monkeypatch.setenv("CLAW_HOST", "9.9.9.9")
    monkeypatch.setenv("CLAW_PORT", "2222")
    monkeypatch.setenv("CLAW_AUTH_TOKEN", "env_token")
    monkeypatch.setenv("CLAW_DATA_DIR", str(data_dir))

    cfg = config.load_config(path=str(path))
    assert cfg.llm_router.url == "http://env"
    assert cfg.llm_router.api_key == "env_key"
    assert cfg.gateway.host == "9.9.9.9"
    assert cfg.gateway.port == 2222
    assert cfg.gateway.auth_token == "env_token"
    assert cfg.storage.db_path == os.path.join(str(data_dir), "claw.db")
    assert cfg.storage.transcript_dir == os.path.join(str(data_dir), "transcripts")


def test_missing_yaml_uses_defaults(monkeypatch, tmp_path):
    _reset_singleton()
    _clear_env(monkeypatch)
    cfg = config.load_config(path=str(tmp_path / "missing.yaml"))
    assert cfg.gateway.port == 18790
    assert cfg.skills.dir == "skills"
    assert cfg.skills.autoload is True
