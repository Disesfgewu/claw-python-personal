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
        f"{cfg.llm_router.url}/v1/search",
        json={"query": query, "max_results": 5},
        headers={"Authorization": f"Bearer {cfg.llm_router.api_key}"},
        timeout=15.0,
    )
    data = resp.json()
    results = data.get("results", [])
    return "\n\n".join(
        f"[{i+1}] {r.get('title')}\n{r.get('href')}\n{r.get('body', '')}"
        for i, r in enumerate(results)
    )
