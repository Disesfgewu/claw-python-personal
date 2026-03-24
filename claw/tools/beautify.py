"""Universal beautification tool: format any query result into Discord Embed."""
from __future__ import annotations

import json
import logging
import re
import uuid
from typing import Any, Optional

import httpx

from claw.tools.registry import tool
from claw.tools.universal_charts import generate_timeseries_chart, generate_bar_chart

logger = logging.getLogger(__name__)


def _generate_chart_from_spec(spec: dict) -> Optional[bytes]:
    """Generate chart PNG bytes from LLM-provided chart spec."""
    if not spec or spec.get("type") is None:
        return None
    chart_type = spec.get("type", "line")
    data = spec.get("data", [])
    title = spec.get("title", "")
    y_label = spec.get("y_label", "")

    if not data:
        return None

    try:
        if chart_type == "line":
            return generate_timeseries_chart(
                title, data, x_key="x", y_key="y", y_label=y_label
            )
        elif chart_type == "bar":
            categories = [str(d.get("x", "")) for d in data]
            values = [float(d.get("y", 0)) for d in data]
            return generate_bar_chart(title, categories, values, y_label=y_label)
    except Exception as e:
        logger.warning(f"Chart generation from spec failed: {e}")
    return None


async def beautify_to_discord_embed(
    data: Any,
    title: str = "Query Result",
    data_context: str = "以下是查詢結果。",
) -> tuple[dict, Optional[bytes]]:
    """
    使用 LLM 把任何查詢結果美化成 Discord Embed 格式，並嘗試生成對應圖表。

    Args:
        data: 要美化的數據（dict、list、str 等）
        title: Embed 標題
        data_context: 數據說明（用於 LLM 理解上下文）

    Returns:
        (embed_dict, chart_bytes) — Discord Embed JSON dict，以及圖表 PNG bytes（可為 None）
    """

    # 序列化數據
    if isinstance(data, str):
        data_str = data
    else:
        data_str = json.dumps(data, ensure_ascii=False, default=str, indent=2)

    # 構建 LLM 提示（要求同時返回 chart spec）
    prompt = f"""你是一個 Discord Embed 美化專家。

**上下文：** {data_context}
**標題建議：** {title}

**任務：**
將以下數據格式化成 Discord Embed JSON，並提供圖表規格。
- 合理分組（技術、基本面、建議等）
- 顏色：紅(0xFF4444)=賣出/下跌，綠(0x44FF44)=買進/上漲，黃(0xFFAA00)=中性
- 如果數據有時間序列，在 chart 欄位提供折線圖數據
- 如果數據有類別比較，在 chart 欄位提供柱狀圖數據
- 如果沒有適合的圖表，chart.type 設為 null

**數據：**
{data_str}

**回應格式（純 JSON，不要其他文字）：**
{{
  "embeds": [{{
    "title": "...",
    "description": "...",
    "color": 0xFFFFFF,
    "fields": [{{"name": "...", "value": "...", "inline": true}}],
    "timestamp": "2026-03-23T00:00:00Z"
  }}],
  "chart": {{
    "type": "line",
    "title": "圖表標題",
    "y_label": "Y軸標籤（含單位）",
    "data": [{{"x": "2026-03-01", "y": 25.3}}]
  }}
}}"""

    # 使用唯一 session ID 防止對話歷史汙染
    session_id = f"beautify:{uuid.uuid4().hex[:8]}"
    fallback_embed = {
        "embeds": [{
            "title": title,
            "description": f"```\n{data_str[:400]}...\n```" if len(data_str) > 400 else data_str,
            "color": 0xAAAAAA,
            "timestamp": None,
        }]
    }

    try:
        from claw.core.config import get_config
        cfg = get_config()
        gateway_url = f"http://{cfg.gateway.host}:{cfg.gateway.port}"
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{gateway_url}/v1/chat/completions",
                json={
                    "session_id": session_id,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False,
                },
            )
            result = response.json()
            content = (
                result.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
            )

        if not content:
            logger.warning("Beautify: empty LLM response, using fallback")
            return fallback_embed, None

        # 清除 thinking 模型的 <think>...</think> 區塊（DeepSeek/QwQ 等）
        content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL)
        # 清理 markdown code block
        content = re.sub(r'^```(?:json)?\n?', '', content)
        content = re.sub(r'\n?```$', '', content)
        content = content.strip()

        # 將 0x 十六進制顏色轉為十進制（JSON 不支援 0x 語法）
        content = re.sub(r':\s*0x([0-9A-Fa-f]+)', lambda m: f': {int(m.group(1), 16)}', content)

        # 解析 JSON
        result_dict = json.loads(content)

        # 提取 chart spec（從結果中移除，不要傳給 Discord embed API）
        chart_spec = result_dict.pop("chart", None)
        chart_bytes = _generate_chart_from_spec(chart_spec) if chart_spec else None

        logger.info(f"Beautified '{title}' → embed + {'chart' if chart_bytes else 'no chart'}")
        return result_dict, chart_bytes

    except Exception as e:
        logger.error(f"Beautify failed: {e}")
        return fallback_embed, None


@tool(
    name="beautify",
    description="Format any query result (stock data, news, etc) into beautiful Discord Embed format using LLM.",
    parameters={
        "type": "object",
        "properties": {
            "data": {
                "type": "string",
                "description": "要美化的數據（JSON 字符串或純文本）",
            },
            "title": {
                "type": "string",
                "description": "Discord Embed 標題",
                "default": "Result",
            },
            "context": {
                "type": "string",
                "description": "數據說明，幫助 LLM 理解上下文",
                "default": "Query result data",
            },
        },
        "required": ["data"],
    },
    requires_main=False,
)
async def beautify(
    data: str,
    title: str = "Result",
    context: str = "Query result data",
) -> str:
    """通用美化工具 - 把任何查詢結果格式化成 Discord Embed。"""
    try:
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except json.JSONDecodeError:
                pass

        embed, _ = await beautify_to_discord_embed(data, title=title, data_context=context)
        return json.dumps(embed, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Beautify tool failed: {e}")
        return json.dumps({
            "embeds": [{"title": title, "description": f"格式化失敗: {e}", "color": 0xFF0000}]
        })
