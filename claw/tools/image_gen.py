from __future__ import annotations

import json
import httpx
from claw.tools.registry import tool


@tool(
    name="image_gen",
    description="生成圖片。指定 prompt，可選 size 和 model。回傳圖片 URL 或 base64。",
    parameters={
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": "圖片描述（繁體中文或英文）",
            },
            "size": {
                "type": "string",
                "enum": ["1024x1024", "1024x1792", "1792x1024"],
                "default": "1024x1024",
                "description": "圖片尺寸",
            },
            "model": {
                "type": "string",
                "enum": ["imagen-4-generate-001", "flux.1-pro", "flux.1-schnell"],
                "default": "imagen-4-generate-001",
                "description": "模型選擇",
            },
            "response_format": {
                "type": "string",
                "enum": ["url", "b64_json"],
                "default": "url",
                "description": "回傳格式：URL 或 base64",
            },
        },
        "required": ["prompt"],
    },
    requires_main=False,
)
async def image_gen(
    prompt: str,
    size: str = "1024x1024",
    model: str = "imagen-4-generate-001",
    response_format: str = "url",
    session_id: str = "agent:main",
) -> str:
    """Generate an image via LLM-Router /v1/images/generations."""
    from claw.core.config import get_config

    cfg = get_config()
    try:
        resp = await httpx.AsyncClient(timeout=60.0).post(
            f"{cfg.llm_router.url}/v1/images/generations",
            json={
                "prompt": prompt,
                "size": size,
                "model": model,
                "response_format": response_format,
                "n": 1,
            },
            headers={"Authorization": f"Bearer {cfg.llm_router.api_key}"},
        )
        resp.raise_for_status()
        data = resp.json()

        # Response: {"data": [{"url": "..."} or {"b64_json": "..."}]}
        if "data" not in data or len(data["data"]) == 0:
            return "Error: No image data in response"

        img = data["data"][0]
        if response_format == "url" and "url" in img:
            return f"✅ Image generated. URL: {img['url']}"
        elif response_format == "b64_json" and "b64_json" in img:
            b64 = img["b64_json"][:80]  # Truncate for display
            return f"✅ Image generated. Base64 (truncated): {b64}..."
        else:
            return f"Error: Unexpected response format: {img}"
    except httpx.TimeoutException:
        return f"Error: Request timed out after 60s"
    except httpx.RequestError as e:
        return f"Error: {e}"
    except Exception as e:
        return f"Error: {type(e).__name__}: {e}"
