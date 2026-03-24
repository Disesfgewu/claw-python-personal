from __future__ import annotations
import logging

from claw.core.storage import Storage, MessageRow
from claw.llm.router_client import ChatMessage

DEFAULT_SYSTEM_PROMPT = """\
You are a helpful assistant. Answer concisely and accurately.
When you need to search the web or run commands, use the available tools.
"""

MAX_CONTEXT_MESSAGES = 40    # 最多帶入 40 則歷史訊息
MAX_CONTEXT_TOKENS = 8000    # 保守估計，避免超過 context window

logger = logging.getLogger(__name__)


async def build_context(
    storage: Storage,
    session_id: str,
    new_user_message: str,
    system_prompt: str | None = None,
    context_builder: "ContextBuilder | None" = None,
) -> list[ChatMessage]:
    """
    組裝送給 LLM 的 messages list。
    順序：system → 歷史訊息（最近 N 筆）→ 新的 user message
    """
    history = await storage.get_messages(session_id, limit=MAX_CONTEXT_MESSAGES)

    if context_builder is None:
        context_builder = ContextBuilder()

    # 歷史訊息
    history_msgs: list[ChatMessage] = []
    for row in history:
        content = row.content
        if isinstance(content, str):
            try:
                import json
                content = json.loads(content)
            except Exception:  # nosec B110
                pass  # 保持原始 string
        msg = ChatMessage(role=row.role, content=content)
        if row.tool_call_id:
            msg.tool_call_id = row.tool_call_id
        history_msgs.append(msg)

    # 轉 dict 做 compaction（只用 role + content）
    raw_dicts = [{"role": m.role, "content": m.content} for m in history_msgs]
    compacted_dicts = context_builder.compact_if_needed(raw_dicts)

    # 還原 ChatMessage（tool_call_id 依索引對應）
    # compaction 只保留尾端，對應到 history_msgs 尾端
    offset = len(history_msgs) - len(compacted_dicts)
    messages: list[ChatMessage] = []
    for i, d in enumerate(compacted_dicts):
        original_idx = offset + i
        if 0 <= original_idx < len(history_msgs):
            msg = history_msgs[original_idx]
        else:
            msg = ChatMessage(role=d["role"], content=d["content"])
        messages.append(msg)

    # 新 user message
    messages.append(ChatMessage(role="user", content=new_user_message))
    if system_prompt:
        messages.insert(0, ChatMessage(role="system", content=system_prompt))
    return messages


class ContextBuilder:
    """Token counting and head+tail compaction for long conversation histories."""

    def __init__(self, max_tokens: int = 120_000):
        self.max_tokens = max_tokens
        try:
            import tiktoken
            self.encoder = tiktoken.get_encoding("cl100k_base")
        except Exception:
            logger.warning("tiktoken not available, token counting disabled")
            self.encoder = None

    def count_tokens(self, messages: list[dict]) -> int:
        """Estimate token count of a messages list."""
        if not self.encoder:
            return 0
        total = 0
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                total += len(self.encoder.encode(content))
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and isinstance(part.get("text"), str):
                        total += len(self.encoder.encode(part["text"]))
        return total

    def compact_if_needed(self, messages: list[dict]) -> list[dict]:
        """
        If total tokens exceed max_tokens, apply head + tail compaction:
        - Keep system message (if any)
        - Keep last 20 messages
        - Drop everything in between
        """
        if not self.encoder:
            return messages

        token_count = self.count_tokens(messages)
        if token_count <= self.max_tokens:
            return messages

        logger.info(
            f"Context compaction triggered: {token_count} tokens > {self.max_tokens} limit"
        )

        # Identify system message
        system = messages[0] if messages and messages[0].get("role") == "system" else None
        tail_limit = 20
        tail = messages[-tail_limit:]

        result = ([system] if system else []) + tail
        logger.info(f"Compacted from {len(messages)} → {len(result)} messages")
        return result
