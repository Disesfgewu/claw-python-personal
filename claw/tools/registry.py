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


def get_tools() -> list[ToolSpec]:
    """Return a list of all registered tools."""
    return list(_registry.values())


async def execute(
    name: str,
    arguments: dict,
    session_id: str = "agent:main",
    session_is_main: bool | None = None,
) -> str:
    """執行 tool，回傳結果字串"""
    spec = _registry.get(name)
    if spec is None:
        return f"Error: unknown tool '{name}'"
    if session_is_main is None:
        from claw.tools.policy import is_main_session
        session_is_main = is_main_session(session_id)
    if spec.requires_main and not session_is_main:
        return f"Error: tool '{name}' requires main session"
    try:
        # Inject session_id into arguments if the handler function signature accepts it.
        # This makes context available to tools without relying on the LLM to provide it.
        import inspect
        sig = inspect.signature(spec.handler)
        if 'session_id' in sig.parameters:
            arguments['session_id'] = session_id

        result = await spec.handler(**arguments)
        return str(result)
    except Exception as e:
        return f"Error: {e}"


class ToolRegistry:
    def register_dynamic(
        self,
        name: str,
        description: str,
        parameters: dict,
        fn: Callable,
    ) -> None:
        """Register a dynamically-created tool function (e.g. from MCP bridge)."""
        _registry[name] = ToolSpec(
            name=name,
            description=description,
            parameters=parameters,
            handler=fn,
            requires_main=False,
        )

    def list_tools(self) -> list[ToolSpec]:
        """Return a list of all registered tools."""
        return list(_registry.values())

_registry_instance = ToolRegistry()

def get_registry() -> ToolRegistry:
    return _registry_instance
