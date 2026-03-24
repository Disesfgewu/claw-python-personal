"""Web search via MCP SSE + JSON-RPC (search_web tool on LLM API)."""
from __future__ import annotations

import asyncio
import json
import logging
import re
import threading
from typing import Any

from claw.core.config import get_config
from claw.tools.mcp_bridge import MCPClient, MCPServerConfig
from .registry import tool

logger = logging.getLogger(__name__)


@tool(
    name="search_web",
    description="透過 MCP (DDGS) 搜尋網路，回傳結構化結果",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜尋關鍵字"},
            "max_results": {"type": "integer", "default": 5},
        },
        "required": ["query"],
    },
)
async def search_web_tool(query: str, max_results: int = 5) -> str:
    data = await _mcp_search_structured_async(query, max_results)
    return json.dumps(data, ensure_ascii=False)


def search_web_impl(query: str, max_results: int = 5, structured: bool = False) -> list[dict] | dict:
    """Synchronous wrapper used by stock/news sync callers."""
    data = _run_coro_sync(_mcp_search_structured_async(query, max_results))
    return data if structured else data.get("results", [])


def _run_coro_sync(coro: Any) -> Any:
    """Run a coroutine from sync code, even if an event loop is already running."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    result: dict[str, Any] = {"value": None, "error": None}

    def _runner() -> None:
        try:
            result["value"] = asyncio.run(coro)
        except Exception as e:  # nosec B110
            result["error"] = e

    th = threading.Thread(target=_runner, daemon=True)
    th.start()
    th.join()
    if result["error"] is not None:
        raise result["error"]
    return result["value"]


def _normalize_result_item(item: dict, rank: int) -> dict:
    title = item.get("title", "") or ""
    url = item.get("url", item.get("href", "")) or ""
    snippet = item.get("snippet", item.get("body", item.get("summary", ""))) or ""
    detail = item.get("detail", "") or ""
    return {
        "rank": int(item.get("rank", rank)),
        "title": title,
        "url": url,
        "snippet": snippet,
        "detail": detail,
        # compatibility fields for downstream callers
        "href": url,
        "body": snippet,
        "summary": snippet,
    }


def _extract_results_from_text(text: str) -> tuple[list[dict], str | None]:
    """Parse MCP TextContent into structured search results + error (if any)."""
    raw = (text or "").strip()
    if not raw:
        return [], None

    if "搜尋發生錯誤" in raw or "Search error" in raw:
        return [], raw

    # Backward-compatible payloads: some servers return JSON text blocks.
    if raw.startswith("{") or raw.startswith("["):
        try:
            decoded = json.loads(raw)
            if isinstance(decoded, dict) and isinstance(decoded.get("results"), list):
                results = [_normalize_result_item(x, i + 1) for i, x in enumerate(decoded["results"]) if isinstance(x, dict)]
                return results, decoded.get("error")
            if isinstance(decoded, list):
                results = [_normalize_result_item(x, i + 1) for i, x in enumerate(decoded) if isinstance(x, dict)]
                return results, None
        except Exception:  # nosec B110
            pass

    results: list[dict] = []
    current: dict[str, Any] = {}

    for line in raw.splitlines():
        s = line.strip()
        if not s:
            continue

        m_index = re.match(r"^\[(\d+)\]\s*(.*)$", s)
        if m_index:
            if current:
                results.append(current)
            current = {"rank": int(m_index.group(1))}
            title = m_index.group(2).strip()
            if title:
                current["title"] = title
            continue

        m_url_key = re.match(r"^(?:URL|Url|url)\s*:\s*(https?://\S+)$", s)
        if m_url_key:
            current["url"] = m_url_key.group(1)
            continue

        m_url_plain = re.match(r"^(https?://\S+)$", s)
        if m_url_plain:
            if "url" not in current:
                current["url"] = m_url_plain.group(1)
            continue

        m_snippet = re.match(r"^(?:Snippet|snippet|Summary|summary)\s*:\s*(.+)$", s)
        if m_snippet:
            current["snippet"] = m_snippet.group(1).strip()
            continue

        m_detail = re.match(r"^(?:Detail|detail)\s*:\s*(.+)$", s)
        if m_detail:
            current["detail"] = m_detail.group(1).strip()
            continue

        if "title" not in current:
            current["title"] = s
        elif "snippet" not in current:
            current["snippet"] = s
        else:
            current["detail"] = (current.get("detail", "") + " " + s).strip()

    if current:
        results.append(current)

    # Fallback: just URLs
    if not results:
        urls = re.findall(r"https?://\S+", raw)
        for i, u in enumerate(urls, start=1):
            results.append({"rank": i, "title": f"Result {i}", "url": u, "snippet": "", "detail": ""})

    normalized = [_normalize_result_item(item, i + 1) for i, item in enumerate(results)]
    return normalized, None


def _extract_results_from_rpc(rpc: dict) -> tuple[list[dict], str | None]:
    content = rpc.get("result", {}).get("content", [])
    text_blocks = [c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text"]
    all_results: list[dict] = []
    error: str | None = None
    for block in text_blocks:
        results, block_error = _extract_results_from_text(block)
        if results:
            all_results.extend(results)
        if block_error:
            error = block_error
    return all_results, error


def _build_structured_response(
    query: str,
    max_results: int,
    results: list[dict],
    error: str | None = None,
    engine: str = "ddgs",
) -> dict:
    return {
        "query": query,
        "raw_query": query,
        "used_query": query,
        "engine": engine,
        "max_results": int(max_results),
        "no_results": len(results) == 0,
        "error": error or "",
        "results": results,
    }


async def _mcp_search_structured_async(query: str, max_results: int = 5) -> dict:
    cfg = get_config()
    base_url = cfg.llm_router.url.rstrip("/")

    headers: dict[str, str] = {}
    if cfg.llm_router.api_key:
        headers["Authorization"] = f"Bearer {cfg.llm_router.api_key}"

    client = MCPClient(MCPServerConfig(
        name="llm-router",
        transport="sse",
        url=base_url,
        headers=headers,
        sse_mode="stream",
        sse_path="/mcp/sse",
        protocol_version="2025-11-25",
        client_info={"name": "claw-search", "version": "1.0"},
    ))
    await client.connect()
    try:
        rpc_resp = await client.call_tool_raw(
            "search_web",
            {"query": query, "max_results": max_results},
        )
        results, error = _extract_results_from_rpc(rpc_resp)
        return _build_structured_response(query, max_results, results, error=error)
    finally:
        await client.close()
