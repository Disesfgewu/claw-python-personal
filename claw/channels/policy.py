from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class ChannelPolicy:
    allow_from: list[str] = field(default_factory=list)
    dm_policy: str = "open"   # "open" | "paired" | "disabled"
    command_roles: dict[str, list[str]] = field(default_factory=dict)

    def is_allowed(self, user_id: str) -> bool:
        if not self.allow_from:
            return True
        return user_id in self.allow_from
