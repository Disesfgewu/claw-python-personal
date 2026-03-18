from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Awaitable


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict          # JSON Schema（type: object, properties: {...}）
    handler: Callable[..., Awaitable[str]]   # async 函數
    requires_main: bool = False  # True = 只能在 main session 執行


_registry: dict[str, ToolSpec] = {}


def tool(
    name: str,
    description: str,
    parameters: dict,
    requires_main: bool = False,
):
    """裝飾器，把一個 async 函數注冊為 tool"""
    def decorator(fn: Callable) -> Callable:
        _registry[name] = ToolSpec(
            name=name,
            description=description,
            parameters=parameters,
            handler=fn,
            requires_main=requires_main,
        )
        return fn
    return decorator


def get_definitions(session_is_main: bool = False) -> list[dict]:
    """回傳 LLM-Router 可用的 tool definitions（OpenAI schema）"""
    specs = []
    for spec in _registry.values():
        if spec.requires_main and not session_is_main:
            continue    # 非 main session 看不到這個 tool
        specs.append({
            "type": "function",
            "function": {
                "name": spec.name,
                "description": spec.description,
                "parameters": spec.parameters,
            }
        })
    return specs


async def execute(name: str, arguments: dict, session_is_main: bool = False) -> str:
    """執行 tool，回傳結果字串"""
    spec = _registry.get(name)
    if spec is None:
        return f"Error: unknown tool '{name}'"
    if spec.requires_main and not session_is_main:
        return f"Error: tool '{name}' requires main session"
    try:
        result = await spec.handler(**arguments)
        return str(result)
    except Exception as e:
        return f"Error: {e}"
