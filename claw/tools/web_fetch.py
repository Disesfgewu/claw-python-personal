from __future__ import annotations
import httpx
from claw.tools.registry import tool


@tool(
    name="web_fetch",
    description="Fetch content from a URL. Returns the response body as text (HTML/JSON/plain text). Use for reading web pages, APIs, or any HTTP resource.",
    parameters={
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The URL to fetch (must include http:// or https://)",
            },
            "method": {
                "type": "string",
                "enum": ["GET", "POST"],
                "default": "GET",
                "description": "HTTP method",
            },
            "headers": {
                "type": "string",
                "description": "Optional JSON object of extra headers",
            },
            "body": {
                "type": "string",
                "description": "Optional request body for POST",
            },
            "timeout": {
                "type": "integer",
                "default": 15,
                "description": "Request timeout in seconds",
            },
        },
        "required": ["url"],
    },
    requires_main=False,
)
async def web_fetch(
    url: str,
    method: str = "GET",
    headers: str = "{}",
    body: str = "",
    timeout: int = 15,
    session_id: str = "agent:main",
) -> str:
    """Fetch a URL and return response content."""
    import json
    try:
        extra_headers = json.loads(headers) if headers and headers != "{}" else {}
    except Exception:
        extra_headers = {}

    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            if method.upper() == "POST":
                resp = await client.post(url, content=body.encode() if body else b"", headers=extra_headers)
            else:
                resp = await client.get(url, headers=extra_headers)

        content_type = resp.headers.get("content-type", "")
        text = resp.text
        # Truncate very large responses
        if len(text) > 10000:
            text = text[:10000] + f"\n[truncated — original {len(resp.content)} bytes]"
        return f"[HTTP {resp.status_code}] {text}"
    except httpx.TimeoutException:
        return f"Error: Request to {url} timed out after {timeout}s"
    except httpx.RequestError as e:
        return f"Error: {e}"
