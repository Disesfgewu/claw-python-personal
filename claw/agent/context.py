from claw.core.storage import Storage, MessageRow
from claw.llm.router_client import ChatMessage

DEFAULT_SYSTEM_PROMPT = """\
You are a helpful assistant. Answer concisely and accurately.
When you need to search the web or run commands, use the available tools.
"""

MAX_CONTEXT_MESSAGES = 40    # 最多帶入 40 則歷史訊息
MAX_CONTEXT_TOKENS = 8000    # 保守估計，避免超過 context window


async def build_context(
    storage: Storage,
    session_id: str,
    new_user_message: str,
    system_prompt: str | None = None,
) -> list[ChatMessage]:
    """
    組裝送給 LLM 的 messages list。
    順序：system → 歷史訊息（最近 N 筆）→ 新的 user message
    """
    history = await storage.get_messages(session_id, limit=MAX_CONTEXT_MESSAGES)

    messages: list[ChatMessage] = []

    # 歷史訊息
    for row in history:
        content = row.content
        if isinstance(content, str):
            try:
                import json
                content = json.loads(content)
            except Exception:
                pass  # 保持原始 string
        msg = ChatMessage(role=row.role, content=content)
        if row.tool_call_id:
            msg.tool_call_id = row.tool_call_id
        messages.append(msg)

    # 新 user message
    messages.append(ChatMessage(role="user", content=new_user_message))
    return messages
