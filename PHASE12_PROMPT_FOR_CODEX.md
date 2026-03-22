# Phase 12 Worker Prompt — Image Generation Tool

你是實作 claw-python Phase 12 的 worker。工作目錄：`/home/martin/Desktop/claw-python-personal/`。
當前狀態：157 tests 通過，0 failures。**嚴格按照順序，每步驗證後再繼續。**

---

## 背景說明

LLM-Router 已支援 `/v1/images/generations` endpoint，使用 Google Imagen 4 或 FLUX.1 生成圖片。Agent 目前無法呼叫此功能。本 Phase 實作 `image_gen` tool 讓 agent 可以生成圖片。

---

## Task 1 — 建立 `claw/tools/image_gen.py`

```python
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
```

---

## Task 2 — 在 `claw/tools/__init__.py` 加入 import

在末尾加入（如果還沒有）：

```python
import claw.tools.image_gen as _image_gen  # noqa: F401
```

完成後應為：
```python
from claw.tools import web_fetch as _web_fetch  # noqa: F401
from claw.tools import file_tools as _file_tools  # noqa: F401
from claw.tools import research_tools as _research_tools  # noqa: F401
import claw.tools.image_gen as _image_gen  # noqa: F401
```

---

## Task 3 — 在 `claw/main.py` 加入 import

在工具 import 區塊末尾加入：

```python
import claw.tools.image_gen    # 觸發 image_gen tool 的注冊
```

---

## Task 4 — 建立測試 `tests/test_image_gen.py`（3 tests）

```python
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_image_gen_success():
    """image_gen successfully posts to LLM-Router /v1/images/generations."""
    from claw.tools.image_gen import image_gen

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json = MagicMock(return_value={
        "data": [{"url": "https://example.com/image.png"}]
    })
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_response)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await image_gen("a cat sitting on a table")

    assert "URL" in result
    assert "example.com/image.png" in result
    mock_client.post.assert_called_once()
    call_args = mock_client.post.call_args
    assert "/v1/images/generations" in call_args[0][0]
    payload = call_args[1]["json"]
    assert payload["prompt"] == "a cat sitting on a table"


@pytest.mark.asyncio
async def test_image_gen_b64_response():
    """image_gen handles base64 response format."""
    from claw.tools.image_gen import image_gen

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json = MagicMock(return_value={
        "data": [{"b64_json": "iVBORw0KGg..." + "X" * 100}]
    })
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_response)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await image_gen("test", response_format="b64_json")

    assert "Base64" in result
    assert "truncated" in result


@pytest.mark.asyncio
async def test_image_gen_timeout():
    """image_gen handles timeout gracefully."""
    import httpx
    from claw.tools.image_gen import image_gen

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("timeout"))

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await image_gen("test")

    assert "timed out" in result.lower()
```

---

## Task 5 — 執行測試

```bash
cd /home/martin/Desktop/claw-python-personal
python -m pytest tests/ -x --tb=short
```

預期：**160 tests 通過，0 failures**（157 + 3 新增）

---

## 交付清單

完成後回報：
1. 每個新建/修改的檔案絕對路徑
2. pytest 最終輸出最後 5 行
3. 遇到的問題和解決方式

---

## 預期測試計數

| 來源 | 數量 |
|---|---|
| Phase 11（現有） | 157 |
| test_image_gen.py | +3 |
| **目標** | **160** |
