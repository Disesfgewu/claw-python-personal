from __future__ import annotations

from claw.skills.base import AbstractSkill


class SkillRegistry:
    def __init__(self):
        self._skills: dict[str, AbstractSkill] = {}

    def register(self, skill: AbstractSkill) -> None:
        name = skill.manifest.name
        self._skills[name] = skill
        for _ in skill.tools:
            pass  # tools 已透過 @tool 裝飾器自動注冊到 tool_registry

    def get(self, name: str) -> AbstractSkill | None:
        return self._skills.get(name)

    def all(self) -> list[AbstractSkill]:
        return list(self._skills.values())

    def unload(self, name: str) -> None:
        skill = self._skills.pop(name, None)
        if skill:
            skill.on_unload()
