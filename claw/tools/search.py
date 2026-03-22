import httpx
from .registry import tool


@tool(
    name="search_web",
    description="用 DDGS 搜尋網路，回傳前 5 個結果",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜尋關鍵字"},
        },
        "required": ["query"],
    },
)
async def search_web_tool(query: str) -> str:
    from claw.core.config import get_config

    cfg = get_config()
    resp = await httpx.AsyncClient().post(
        f"{cfg.llm_router.url}/mcp/messages",
        json={
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "search_web",
                "arguments": {"query": query, "max_results": 5},
            },
            "id": 1,
        },
        headers={"Authorization": f"Bearer {cfg.llm_router.api_key}"},
        timeout=15.0,
    )
    data = resp.json()
    # MCP response: {"result": {"content": [{"type": "text", "text": "[{...}, ...]"}]}}
    content = data.get("result", {}).get("content", [])
    if content and content[0].get("type") == "text":
        import json as _json
        try:
            results = _json.loads(content[0]["text"])
        except Exception:
            return content[0]["text"]
    else:
        results = []
    if not results:
        return "(no results)"
    return "\n\n".join(
        f"[{i+1}] {r.get('title')}\n{r.get('href')}\n{r.get('body', '')}"
        for i, r in enumerate(results)
    )
