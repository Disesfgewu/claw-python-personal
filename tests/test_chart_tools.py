"""Unit tests for chart tools."""
import pytest
from io import BytesIO
from claw.tools.chart_tools import generate_candlestick_chart


@pytest.mark.asyncio
async def test_generate_candlestick_chart():
    """Test K-line chart generation returns valid PNG."""
    mock_ohlcv = [
        {"date": f"2026-03-{i:02d}", "open": 598.0 + i, "high": 603.0 + i, "low": 595.0 + i, "close": 600.0 + i, "volume": 17500000}
        for i in range(1, 11)  # 10 days of data
    ]

    png_bytes = generate_candlestick_chart("2330", mock_ohlcv)

    assert isinstance(png_bytes, bytes)
    assert len(png_bytes) > 0
    # PNG magic number: \x89PNG\r\n\x1a\n
    assert png_bytes[:8] == b'\x89PNG\r\n\x1a\n'
    assert png_bytes[1:4] == b'PNG'
