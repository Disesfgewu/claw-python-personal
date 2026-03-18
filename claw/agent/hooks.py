from __future__ import annotations

import inspect
import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)

HookHandler = Callable[..., Any]

_MODIFIABLE_HOOKS: dict[str, str] = {
    "before_prompt_build": "base_prompt",
    "after_user_message": "message",
    "after_tool_call": "result",
    "before_send": "content",
}


class HookRegistry:
    def __init__(self) -> None:
        self._handlers: dict[str, list[HookHandler]] = {}

    def register(self, event: str, handler: HookHandler) -> None:
        self._handlers.setdefault(event, []).append(handler)

    def unregister(self, event: str, handler: HookHandler) -> None:
        handlers = self._handlers.get(event)
        if not handlers:
            return
        try:
            handlers.remove(handler)
        except ValueError:
            return

    async def fire(self, event: str, **kwargs) -> Any:
        handlers = self._handlers.get(event, [])
        mod_key = _MODIFIABLE_HOOKS.get(event)

        if mod_key:
            value = kwargs.get(mod_key)
            for h in handlers:
                try:
                    result = h(**kwargs)
                    if inspect.isawaitable(result):
                        result = await result
                    if result is not None:
                        value = result
                        kwargs[mod_key] = value
                except Exception as e:
                    logger.warning(f"hook error: {event} {e}")
            return value

        for h in handlers:
            try:
                result = h(**kwargs)
                if inspect.isawaitable(result):
                    await result
            except Exception as e:
                logger.warning(f"hook error: {event} {e}")
        return None

    def clear(self) -> None:
        self._handlers.clear()


_hooks: HookRegistry | None = None


def get_hooks() -> HookRegistry:
    global _hooks
    if _hooks is None:
        _hooks = HookRegistry()
    return _hooks
