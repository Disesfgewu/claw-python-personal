from typing import AsyncIterator
import json
from datetime import datetime, timezone

from claw.core.storage import Storage, MessageRow
from claw.llm.router_client import LLMRouterClient, CompletionRequest, StreamChunk
from claw.tools import registry as tool_registry
from claw.tools.policy import is_main_session
from claw.agent.events import (
    Event, TextChunk, ToolCallStart, ToolCallResult, RunComplete, RunError
)
from claw.agent.context import build_context, DEFAULT_SYSTEM_PROMPT
from claw.agent.prompt_tools import (
    build_tool_system_prompt, parse_tool_calls, strip_tool_calls,
    format_tool_result_message,
)

MAX_TOOL_ROUNDS = 8   # 最多幾輪 tool call，防止無限迴圈


class AgentLoop:
    def __init__(self, storage: Storage, llm: LLMRouterClient):
        self.storage = storage
        self.llm = llm

    async def run(
        self,
        session_id: str,
        user_message: str,
        system_prompt: str | None = None,
        model: str = "auto",
        prompt_tools: bool = True,   # True = prompt-based fallback，False = native only
    ) -> AsyncIterator[Event]:
        """
        執行一次 agent run，yield Events。
        caller 用 async for 收 events，即時串流輸出。
        """
        session = await self.storage.get_session(session_id)
        if session is None:
            yield RunError(error=f"session not found: {session_id}")
            return

        is_main = is_main_session(session_id)
        sys_prompt = system_prompt or session.system_prompt or DEFAULT_SYSTEM_PROMPT

        # 把 user message 存入 storage
        await self._save_message(session_id, "user", user_message)
        self.storage.append_transcript(session_id, {
            "ts": now_iso(), "type": "user_message", "content": user_message
        })

        messages = await build_context(self.storage, session_id, user_message, sys_prompt)
        tool_defs = tool_registry.get_definitions(session_is_main=is_main)

        # prompt-based mode：工具定義注入 system prompt，不送 native tools
        use_prompt_tools = prompt_tools and bool(tool_defs)
        effective_sys_prompt = sys_prompt
        if use_prompt_tools:
            from claw.llm.router_client import ToolDefinition
            tool_def_objs = [
                ToolDefinition(
                    name=t["function"]["name"],
                    description=t["function"]["description"],
                    parameters=t["function"]["parameters"],
                )
                for t in tool_defs
            ]
            effective_sys_prompt = sys_prompt + build_tool_system_prompt(tool_def_objs)

        full_content = ""
        usage = {}

        try:
            for round_num in range(MAX_TOOL_ROUNDS + 1):
                if use_prompt_tools:
                    req = self._make_request(
                        messages, effective_sys_prompt, [], model, round_num
                    )
                else:
                    req = self._make_request(
                        messages, effective_sys_prompt, tool_defs, model, round_num
                    )

                # --- streaming ---
                content_buffer = ""
                tool_call_buffers: dict[int, dict] = {}   # index → partial tool call

                self.storage.append_transcript(session_id, {
                    "ts": now_iso(), "type": "assistant_start", "model": model
                })

                async for chunk in self.llm.stream(req):
                    # 文字 chunk
                    if chunk.content:
                        content_buffer += chunk.content
                        # prompt-based 模式：先緩衝，不即時 yield（等解析完才知道哪些是工具呼叫）
                        if not use_prompt_tools:
                            yield TextChunk(content=chunk.content)

                    # native tool call delta（分段累積）
                    if chunk.tool_call_delta:
                        for tc_delta in chunk.tool_call_delta:
                            idx = tc_delta.get("index", 0)
                            if idx not in tool_call_buffers:
                                tool_call_buffers[idx] = {
                                    "id": "", "name": "", "arguments": ""
                                }
                            buf = tool_call_buffers[idx]
                            fn = tc_delta.get("function", {})
                            buf["id"] = tc_delta.get("id") or buf["id"]
                            buf["name"] = fn.get("name") or buf["name"]
                            buf["arguments"] += fn.get("arguments") or ""

                    if chunk.usage:
                        usage = chunk.usage

                # --- prompt-based：解析 <tool_call> blocks ---
                if use_prompt_tools and not tool_call_buffers:
                    parsed_calls = parse_tool_calls(content_buffer)
                    if parsed_calls:
                        # 有 tool call：把純文字部分先 yield
                        visible_text = strip_tool_calls(content_buffer)
                        if visible_text:
                            yield TextChunk(content=visible_text)

                        # 執行 tool calls
                        call_results: list[str] = []
                        for pc in parsed_calls:
                            self.storage.append_transcript(session_id, {
                                "ts": now_iso(), "type": "tool_call",
                                "name": pc.name, "args": pc.arguments
                            })
                            yield ToolCallStart(
                                tool_call_id=pc.id, name=pc.name, arguments=pc.arguments
                            )

                            result = await tool_registry.execute(
                                pc.name, pc.arguments, session_is_main=is_main
                            )
                            call_results.append(result)

                            self.storage.append_transcript(session_id, {
                                "ts": now_iso(), "type": "tool_result",
                                "name": pc.name, "result": result[:500]
                            })
                            yield ToolCallResult(
                                tool_call_id=pc.id, name=pc.name, result=result
                            )

                        # 組合 tool result message，以 user role 送回（prompt-based 無 tool role）
                        from claw.llm.router_client import ChatMessage
                        result_msg = format_tool_result_message(parsed_calls, call_results)
                        messages.append(ChatMessage(role="assistant", content=content_buffer))
                        messages.append(ChatMessage(role="user", content=result_msg))
                        await self._save_message(session_id, "assistant", content_buffer)
                        continue  # 繼續下一輪

                    else:
                        # 沒有 tool call，純文字回覆
                        yield TextChunk(content=content_buffer)
                        full_content += content_buffer
                        await self._save_message(session_id, "assistant", content_buffer)
                        self.storage.append_transcript(session_id, {
                            "ts": now_iso(), "type": "assistant_message",
                            "content": content_buffer
                        })
                        break

                # --- native tool calls 處理（原有邏輯）---
                if not tool_call_buffers:
                    # 沒有 tool call，這一輪結束
                    full_content += content_buffer
                    if use_prompt_tools:
                        pass  # 已在上面處理
                    else:
                        await self._save_message(session_id, "assistant", content_buffer)
                        self.storage.append_transcript(session_id, {
                            "ts": now_iso(), "type": "assistant_message",
                            "content": content_buffer
                        })
                    break

                # 把 assistant message（含 tool_calls）加入 messages
                tool_calls_payload = []
                for idx, buf in sorted(tool_call_buffers.items()):
                    tool_calls_payload.append({
                        "id": buf["id"],
                        "type": "function",
                        "function": {
                            "name": buf["name"],
                            "arguments": buf["arguments"],
                        }
                    })
                from claw.llm.router_client import ChatMessage
                messages.append(ChatMessage(
                    role="assistant",
                    content=content_buffer or "",
                    tool_calls=tool_calls_payload,
                ))

                # 執行每個 tool call
                for buf in tool_call_buffers.values():
                    tc_id = buf["id"]
                    tc_name = buf["name"]
                    try:
                        tc_args = json.loads(buf["arguments"])
                    except json.JSONDecodeError:
                        tc_args = {}

                    self.storage.append_transcript(session_id, {
                        "ts": now_iso(), "type": "tool_call",
                        "name": tc_name, "args": tc_args
                    })
                    yield ToolCallStart(
                        tool_call_id=tc_id, name=tc_name, arguments=tc_args
                    )

                    result = await tool_registry.execute(
                        tc_name, tc_args, session_is_main=is_main
                    )

                    self.storage.append_transcript(session_id, {
                        "ts": now_iso(), "type": "tool_result",
                        "name": tc_name, "result": result[:500]  # truncate for transcript
                    })
                    yield ToolCallResult(
                        tool_call_id=tc_id, name=tc_name, result=result
                    )

                    # tool result 加入 messages，下一輪繼續
                    messages.append(ChatMessage(
                        role="tool",
                        content=result,
                        tool_call_id=tc_id,
                    ))
                    await self._save_message(
                        session_id, "tool", result,
                        tool_call_id=tc_id, tool_name=tc_name
                    )

            await self.storage.update_last_active(session_id)
            self.storage.append_transcript(session_id, {
                "ts": now_iso(), "type": "run_complete", "usage": usage
            })
            yield RunComplete(full_content=full_content, usage=usage)

        except Exception as e:
            self.storage.append_transcript(session_id, {
                "ts": now_iso(), "type": "run_error", "error": str(e)
            })
            yield RunError(error=str(e))

    def _make_request(
        self,
        messages,
        system_prompt: str,
        tool_defs: list,
        model: str,
        round_num: int,
    ) -> CompletionRequest:
        from claw.llm.router_client import CompletionRequest, ToolDefinition
        tools = None
        if tool_defs:
            tools = [
                ToolDefinition(
                    name=t["function"]["name"],
                    description=t["function"]["description"],
                    parameters=t["function"]["parameters"],
                )
                for t in tool_defs
            ]
        return CompletionRequest(
            messages=messages,
            model=model,
            tools=tools,
            system=system_prompt if round_num == 0 else None,
        )

    async def _save_message(
        self,
        session_id: str,
        role: str,
        content,
        tool_call_id: str | None = None,
        tool_name: str | None = None,
    ) -> None:
        import json as _json
        content_str = content if isinstance(content, str) else _json.dumps(content)
        await self.storage.add_message(MessageRow(
            session_id=session_id,
            role=role,
            content=content_str,
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            created_at=now_iso(),
        ))


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
