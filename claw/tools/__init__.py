from claw.tools import web_fetch as _web_fetch  # noqa: F401
from claw.tools import file_tools as _file_tools  # noqa: F401
from claw.tools import research_tools as _research_tools  # noqa: F401
from claw.tools import mcp_bridge as _mcp_bridge  # noqa: F401
import claw.tools.image_gen as _image_gen  # noqa: F401
import claw.tools.browser as _browser  # noqa: F401
import claw.tools.bash as _bash  # noqa: F401
import claw.tools.search as _search  # noqa: F401
import claw.tools.memory_tools as _memory_tools  # noqa: F401
import claw.tools.cron as _cron  # noqa: F401
import claw.tools.sessions_tools as _sessions_tools  # noqa: F401

import json
import base64
from claw.tools.registry import tool as register_tool
from claw.tools.chart_tools import generate_candlestick_chart
from claw.tools.stock_tools import stock_screen, stock_chip, stock_news, sentiment_analyze

@register_tool(
    name="generate_chart_tool",
    description="Generate K-line candlestick chart for stock analysis.",
    parameters={
        "type": "object",
        "properties": {
            "symbol": {"type": "string"},
            "period": {"type": "string", "default": "3mo"}
        },
        "required": ["symbol"]
    }
)
def generate_chart_tool(symbol: str, period: str = "3mo") -> str:
    """Generate K-line candlestick chart for stock analysis."""
    try:
        from claw.tools.stock_tools import stock_fetch
        fetch_result = stock_fetch(symbol, period)
        png_bytes = generate_candlestick_chart(symbol, fetch_result.get("ohlcv", []) if isinstance(fetch_result, dict) else [])
        # 返回 base64 編碼方便透過 API 傳輸
        b64 = base64.b64encode(png_bytes).decode('utf-8')
        return json.dumps({
            "success": True,
            "symbol": symbol,
            "image_base64": b64,
            "size_kb": len(png_bytes) / 1024
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": str(e)
        }, ensure_ascii=False)

@register_tool(
    name="stock_screen_tool",
    description="Screen Taiwan 50 stocks based on technical criteria.",
    parameters={
        "type": "object",
        "properties": {
            "criteria": {"type": "string"}
        },
        "required": []
    }
)
def stock_screen_tool(criteria: str | None = None) -> str:
    """Screen Taiwan 50 stocks based on technical criteria."""
    try:
        criteria_dict = None
        if criteria:
            criteria_dict = json.loads(criteria)
        results = stock_screen(criteria_dict)
        result_list = [
            {
                "symbol": getattr(r, 'symbol', ''),
                "name": getattr(r, 'name', ''),
                "current_price": getattr(r, 'current_price', 0),
                "signal": getattr(r, 'signal', ''),
                "rsi": getattr(r.indicators, 'rsi', 0) if hasattr(r, 'indicators') else 0,
                "trend": getattr(r, 'trend', '')
            }
            for r in results
        ]
        return json.dumps(result_list, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)

@register_tool(
    name="stock_chip_tool",
    description="Query institutional chip analysis (foreign, trust, dealer).",
    parameters={
        "type": "object",
        "properties": {
            "symbol": {"type": "string"}
        },
        "required": ["symbol"]
    }
)
def stock_chip_tool(symbol: str) -> str:
    """Query institutional chip analysis (foreign, trust, dealer)."""
    try:
        result = stock_chip(symbol)
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)

@register_tool(
    name="stock_news_tool",
    description="Fetch and analyze recent news for a stock.",
    parameters={
        "type": "object",
        "properties": {
            "symbol": {"type": "string"},
            "limit": {"type": "integer", "default": 5}
        },
        "required": ["symbol"]
    }
)
def stock_news_tool(symbol: str, limit: int = 5) -> str:
    """Fetch and analyze recent news for a stock."""
    try:
        news_list = stock_news(symbol, limit)
        sentiment = sentiment_analyze(news_list)
        return json.dumps({
            "symbol": symbol,
            "news_count": len(news_list),
            "articles": news_list,
            "sentiment_analysis": sentiment
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)
