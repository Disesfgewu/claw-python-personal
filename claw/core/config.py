from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

import yaml
from dotenv import load_dotenv

load_dotenv()


@dataclass
class GatewayConfig:
    host: str = "127.0.0.1"
    port: int = 18790
    auth_token: str = ""


@dataclass
class LLMRouterConfig:
    url: str = "http://127.0.0.1:8000"
    api_key: str = ""


@dataclass
class AgentConfig:
    system_prompt: str | None = None
    queue_mode: str = "collect"
    sandbox: bool = False
    max_tool_rounds: int = 8
    prompt_tools: bool = True


@dataclass
class SandboxConfig:
    enabled: bool = True
    image: str = "claw-sandbox:latest"
    workspace_dir: str = "/workspace"
    timeout: int = 60
    memory_limit: str = "256m"
    cpu_period: int = 100000
    cpu_quota: int = 50000


@dataclass
class SkillsConfig:
    dir: str = "skills"
    autoload: bool = True


@dataclass
class StorageConfig:
    db_path: str = "~/.claw/claw.db"
    transcript_dir: str = "~/.claw/transcripts"


@dataclass
class LoggingConfig:
    level: str = "INFO"
    format: str = "text"


@dataclass
class TelegramConfig:
    enabled: bool = False
    token: str = ""
    polling: bool = True  # True=polling, False=webhook


@dataclass
class SlackConfig:
    enabled: bool = False
    bot_token: str = ""
    app_token: str = ""  # Socket Mode app token


@dataclass
class DiscordConfig:
    enabled: bool = False
    token: str = ""
    stock_channel_id: int = 0
    morning_report_channel_id: int = 0
    intent_model: str = "gemma3:27b"  # Model used for intent pre-classification and AI opinion


@dataclass
class ClawConfig:
    gateway: GatewayConfig = field(default_factory=GatewayConfig)
    llm_router: LLMRouterConfig = field(default_factory=LLMRouterConfig)
    agents: dict[str, AgentConfig] = field(default_factory=lambda: {"default": AgentConfig()})
    sandbox: SandboxConfig = field(default_factory=SandboxConfig)
    skills: SkillsConfig = field(default_factory=SkillsConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    telegram: TelegramConfig = field(default_factory=TelegramConfig)
    slack: SlackConfig = field(default_factory=SlackConfig)
    discord: DiscordConfig = field(default_factory=DiscordConfig)
    def get_agent(self, agent_id: str) -> AgentConfig:
        return self.agents.get(agent_id) or self.agents.get("default") or AgentConfig()


_config: ClawConfig | None = None


def load_config(path: str = "config/default.yaml") -> ClawConfig:
    """讀取 YAML + env 覆蓋，回傳 ClawConfig"""
    raw: dict[str, Any] = {}
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}

    _apply_env_overrides(raw)

    cfg = ClawConfig(
        gateway=GatewayConfig(**raw.get("gateway", {})),
        llm_router=LLMRouterConfig(**raw.get("llm_router", {})),
        sandbox=SandboxConfig(**raw.get("sandbox", {})),
        skills=SkillsConfig(**raw.get("skills", {})),
        storage=StorageConfig(**raw.get("storage", {})),
        logging=LoggingConfig(**raw.get("logging", {})),
        telegram=TelegramConfig(**raw.get("telegram", {})),
        slack=SlackConfig(**raw.get("slack", {})),
        discord=DiscordConfig(**raw.get("discord", {})),
    )

    agents_raw = raw.get("agents") or {"default": {}}
    cfg.agents = {k: AgentConfig(**v) for k, v in agents_raw.items()}

    return cfg


def get_config() -> ClawConfig:
    """全域 singleton，首次呼叫時載入"""
    global _config
    if _config is None:
        _config = load_config()
    return _config


def _apply_env_overrides(raw: dict[str, Any]) -> None:
    """把特定 env vars 覆蓋到 raw dict"""
    overrides: dict[str, tuple[str, str] | None] = {
        "LLM_ROUTER_URL": ("llm_router", "url"),
        "LLM_ROUTER_API_KEY": ("llm_router", "api_key"),
        "CLAW_HOST": ("gateway", "host"),
        "CLAW_PORT": ("gateway", "port"),
        "CLAW_AUTH_TOKEN": ("gateway", "auth_token"),
        "CLAW_GATEWAY_AUTH_TOKEN": ("gateway", "auth_token"),
        "DISCORD_TOKEN": ("discord", "token"),
        "TELEGRAM_TOKEN": ("telegram", "token"),
        "SLACK_BOT_TOKEN": ("slack", "bot_token"),
        "SLACK_APP_TOKEN": ("slack", "app_token"),
        "CLAW_DATA_DIR": None,
    }

    for env_key, path in overrides.items():
        val = os.getenv(env_key)
        if val is None or path is None:
            continue
        if env_key == "CLAW_PORT":
            try:
                val = int(val)
            except ValueError:
                continue
        section, key = path
        raw.setdefault(section, {})[key] = val

    # 處理整數型的環境變數（Discord/Telegram channel IDs）
    int_overrides = {
        "DISCORD_CHANNEL_ID": ("discord", "stock_channel_id"),
    }
    for env_key, path in int_overrides.items():
        val = os.getenv(env_key)
        if val is not None:
            try:
                section, key = path
                raw.setdefault(section, {})[key] = int(val)
            except ValueError:
                pass

    data_dir = os.getenv("CLAW_DATA_DIR")
    if data_dir:
        data_dir = os.path.expanduser(data_dir)
        raw.setdefault("storage", {})["db_path"] = os.path.join(data_dir, "claw.db")
        raw.setdefault("storage", {})["transcript_dir"] = os.path.join(
            data_dir, "transcripts"
        )
