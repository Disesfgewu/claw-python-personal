"""
Prompt-based tool calling fallback。

當 LLM-Router 路由到不支援 native function calling 的 model 時，
把工具定義注入 system prompt，解析 <tool_call> XML 輸出。

格式：
  LLM 輸出：
    <tool_call>
    {"name": "bash", "arguments": {"command": "date"}}
    </tool_call>

  多個 tool call：
    <tool_call>
    {"name": "bash", "arguments": {"command": "date"}}
    </tool_call>
    <tool_call>
    {"name": "bash", "arguments": {"command": "whoami"}}
    </tool_call>
"""
from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass

from claw.llm.router_client import ToolDefinition


# ── 注入進 system prompt 的工具區塊 ──────────────────────────────────────────

TOOL_CALLING_INSTRUCTIONS = """\

You have access to the following tools. To use a tool, output a <tool_call> block with a JSON object containing "name" and "arguments". You may call multiple tools. Always wait for tool results before continuing.

<tools>
{tool_descriptions}
</tools>

To call a tool:
<tool_call>
{{"name": "tool_name", "arguments": {{...}}}}
</tool_call>

After calling tools, wait for the results before providing your final answer.
Do NOT explain what you are going to do — just call the tool directly.
"""


def build_tool_system_prompt(tools: list[ToolDefinition]) -> str:
    """把 tool definitions 轉成 system prompt 附加段落"""
    descriptions = []
    for t in tools:
        params_str = json.dumps(t.parameters, ensure_ascii=False, indent=2)
        descriptions.append(
            f"### {t.name}\n"
            f"{t.description}\n"
            f"Parameters (JSON Schema):\n```json\n{params_str}\n```"
        )
    tool_block = "\n\n".join(descriptions)
    return TOOL_CALLING_INSTRUCTIONS.format(tool_descriptions=tool_block)


# ── 解析 LLM 回應中的 <tool_call> ─────────────────────────────────────────────

@dataclass
class ParsedToolCall:
    id: str
    name: str
    arguments: dict


_TOOL_CALL_PATTERN = re.compile(
    r"<tool_call>\s*(.*?)\s*</tool_call>",
    re.DOTALL,
)


def parse_tool_calls(text: str) -> list[ParsedToolCall]:
    """
    從 LLM 回應文字中提取所有 <tool_call> block。
    回傳空 list 表示沒有 tool call。
    """
    results: list[ParsedToolCall] = []
    for match in _TOOL_CALL_PATTERN.finditer(text):
        raw = match.group(1).strip()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            # 嘗試修復尾巴不完整的 JSON
            data = _try_repair_json(raw)
            if data is None:
                continue

        name = data.get("name", "")
        arguments = data.get("arguments", {})
        if not name:
            continue
        if not isinstance(arguments, dict):
            try:
                arguments = json.loads(arguments)
            except Exception:
                arguments = {}

        results.append(ParsedToolCall(
            id=f"ptc_{uuid.uuid4().hex[:8]}",
            name=name,
            arguments=arguments,
        ))
    return results


def strip_tool_calls(text: str) -> str:
    """把 <tool_call>...</tool_call> block 從文字中移除"""
    return _TOOL_CALL_PATTERN.sub("", text).strip()


# ── 工具結果注入 message ───────────────────────────────────────────────────────

def format_tool_result_message(calls: list[ParsedToolCall], results: list[str]) -> str:
    """
    把多個 tool 結果格式化為 user-side message（讓 model 看到）。
    使用 <tool_result> 標籤。
    """
    parts = []
    for call, result in zip(calls, results):
        parts.append(
            f"<tool_result name=\"{call.name}\" id=\"{call.id}\">\n"
            f"{result}\n"
            f"</tool_result>"
        )
    return "\n".join(parts)


# ── JSON 修復 ──────────────────────────────────────────────────────────────────

def _try_repair_json(raw: str) -> dict | None:
    """嘗試提取第一個完整的 JSON object（tolerant parse）"""
    # 找到第一個 { 到最後一個 } 之間的內容
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1:
        return None
    candidate = raw[start:end + 1]
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        return None
