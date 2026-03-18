from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class SkillRequirements:
    bins: list[str] = field(default_factory=list)
    any_bins: list[str] = field(default_factory=list)
    env: list[str] = field(default_factory=list)
    python: list[str] = field(default_factory=list)
    os: list[str] = field(default_factory=list)


@dataclass
class SkillManifest:
    name: str
    description: str = ""
    version: str = "1.0"
    requires: SkillRequirements = field(default_factory=SkillRequirements)
    openclaw_extras: dict = field(default_factory=dict)


class AbstractSkill(ABC):
    """
    Python class-based skill 的基底類別。
    繼承這個 class，覆寫需要的方法。
    """

    @property
    @abstractmethod
    def manifest(self) -> SkillManifest:
        """回傳 skill 的 metadata"""
        ...

    @property
    def system_prompt(self) -> str | None:
        """注入 system prompt 的文字；None = 不注入"""
        return None

    @property
    def tools(self) -> list:
        """
        這個 skill 提供的 tools。
        每個元素是一個 async function，已用 @tool 裝飾。
        回傳空 list = 不提供 tools。
        """
        return []

    def register_hooks(self) -> None:
        """
        在這裡呼叫 get_hooks().register(...)。
        Loader 載入 skill 時會呼叫這個方法。
        """
        pass

    def on_load(self) -> None:
        """Skill 被載入時呼叫"""
        pass

    def on_unload(self) -> None:
        """Skill 被卸載時呼叫"""
        pass
