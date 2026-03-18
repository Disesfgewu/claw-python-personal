from dataclasses import dataclass, field
from typing import Literal


@dataclass
class TextChunk:
    type: Literal["text_chunk"] = "text_chunk"
    content: str = ""


@dataclass
class ToolCallStart:
    type: Literal["tool_call_start"] = "tool_call_start"
    tool_call_id: str = ""
    name: str = ""
    arguments: dict = field(default_factory=dict)


@dataclass
class ToolCallResult:
    type: Literal["tool_call_result"] = "tool_call_result"
    tool_call_id: str = ""
    name: str = ""
    result: str = ""


@dataclass
class RunComplete:
    type: Literal["run_complete"] = "run_complete"
    full_content: str = ""
    usage: dict = field(default_factory=dict)


@dataclass
class RunError:
    type: Literal["run_error"] = "run_error"
    error: str = ""


Event = TextChunk | ToolCallStart | ToolCallResult | RunComplete | RunError
