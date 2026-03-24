# Phase S1A Worker Prompt — Stock Tools Core Logic

> 發給：**Codex**
> 當前狀態：178 tests passing（Phase S0 完成）
> 目標狀態：182+ tests + Stock Tools 核心邏輯就位
> 耗時預估：3 小時

---

## 背景說明

Phase S1a 實現台股分析系統的核心邏輯層。目前系統有 Discord Embed 支援，但還缺乏股票資料抓取和技術分析功能。

S1a 的任務是建立三個基礎工具：
1. **stock_fetch()** — 從 TWSE/Yahoo Finance 拉取股票 OHLCV 資料
2. **stock_analyze()** — 計算技術指標（RSI, MACD, Bollinger Bands）和基本面資料
3. **StockReport 資料結構** — 統一的股票分析報告格式

這是後續 S1b (圖表) 和 S2-S4 (自動推播、回測) 的基礎。

---

## Task 1 — 建立 `claw/models/stock_report.py`

新建資料結構檔案，定義股票分析報告的格式。使用 dataclass 或 Pydantic BaseModel。

**檔案位置**：`claw/models/stock_report.py`

**內容**：

```python
"""Stock analysis report data structures."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class TechnicalIndicators:
    """Technical analysis indicators."""
    rsi: float = 0.0  # Relative Strength Index (0-100)
    macd_signal: float = 0.0  # MACD - Signal line
    macd_histogram: float = 0.0  # MACD histogram
    bollinger_upper: float = 0.0  # Bollinger Band upper
    bollinger_middle: float = 0.0  # Bollinger Band middle (20-day MA)
    bollinger_lower: float = 0.0  # Bollinger Band lower
    sma_20: float = 0.0  # 20-day moving average
    sma_50: float = 0.0  # 50-day moving average
    sma_200: float = 0.0  # 200-day moving average


@dataclass
class FundamentalData:
    """Fundamental company data."""
    pe_ratio: Optional[float] = None  # Price-to-earnings ratio
    pb_ratio: Optional[float] = None  # Price-to-book ratio
    dividend_yield: Optional[float] = None  # Annual dividend %
    market_cap: Optional[float] = None  # Market cap in TWD
    industry: str = ""  # Industry category


@dataclass
class StockReport:
    """Complete stock analysis report."""
    symbol: str  # Stock code (e.g., "2330")
    name: str  # Company name
    current_price: float  # 現價 (TWD)
    previous_close: float  # 前收盤
    day_high: float  # 日高
    day_low: float  # 日低
    volume: int  # 成交量
    timestamp: datetime  # Report generation time

    # Technical indicators
    indicators: TechnicalIndicators = field(default_factory=TechnicalIndicators)

    # Fundamental data
    fundamentals: FundamentalData = field(default_factory=FundamentalData)

    # Analysis summary
    trend: str = ""  # "uptrend" / "downtrend" / "sideways"
    signal: str = ""  # "strong_buy" / "buy" / "hold" / "sell" / "strong_sell"
    summary: str = ""  # 中文分析摘要
```

**驗收**：
- 檔案存在於指定路徑
- dataclass 可以被 import
- 所有欄位有正確的型別和預設值

---

## Task 2 — 建立 `claw/tools/stock_tools.py`

新建股票工具模組，實現 `stock_fetch()` 和 `stock_analyze()` 兩個核心函數。

**檔案位置**：`claw/tools/stock_tools.py`

**依賴包**（稍後在 pyproject.toml 新增）：
- `yfinance` — Yahoo Finance API wrapper
- `ta` — Technical Analysis library
- (optional) `taiwan-stock-crawler` — TWSE 爬蟲（備用）

**核心函數 1：stock_fetch(symbol: str, period: str = "1y", source: str = "auto") → dict**

```python
def stock_fetch(symbol: str, period: str = "1y", source: str = "auto") -> dict:
    """
    Fetch stock OHLCV data from TWSE or Yahoo Finance.

    Args:
        symbol: Stock code (e.g., "2330" for TSMC)
        period: Data period ("1mo", "3mo", "1y", etc.)
        source: Data source ("twse", "yahoo", "auto")

    Returns:
        {
            "symbol": "2330",
            "name": "台積電",
            "current": 600.0,
            "previous_close": 598.0,
            "high": 605.0,
            "low": 595.0,
            "volume": 18500000,
            "timestamp": datetime(...),
            "ohlcv": [  # 最近 N 筆 OHLCV
                {"date": "2026-03-22", "open": 598.5, "high": 605.0, "low": 595.0, "close": 600.0, "volume": 18500000},
                ...
            ]
        }

    Raises:
        ValueError: If data source unavailable or symbol not found
    """
    # 優先級：auto → twse → yahoo
    # 使用 yfinance 拉取資料
    # 計算當日 high/low/volume
    # 回傳字典格式
    pass


def stock_analyze(symbol: str, ohlcv_list: list) -> StockReport:
    """
    Analyze stock technical indicators and generate report.

    Args:
        symbol: Stock code
        ohlcv_list: List of OHLCV dicts with 'close', 'high', 'low', 'volume' keys

    Returns:
        StockReport with technical indicators and trend analysis

    計算指標（使用 ta library）：
    - RSI (14-period)
    - MACD (12, 26, 9)
    - Bollinger Bands (20-period, 2 std)
    - Moving averages (20, 50, 200-day)

    判斷趨勢：
    - 若 RSI > 70: overbought → "sell" signal
    - 若 RSI < 30: oversold → "buy" signal
    - 若 close > SMA200 & SMA50 > SMA200: uptrend
    - 若 close < SMA200 & SMA50 < SMA200: downtrend
    - 其他：sideways
    """
    # 使用 ta 計算技術指標
    # 判斷趨勢和訊號
    # 回傳 StockReport
    pass
```

**核心邏輯提示**：

1. **stock_fetch()**：
   - 如果 `source="auto"`，先嘗試 TWSE（`query.sse.com.tw`），失敗則改 Yahoo
   - 使用 `yfinance.Ticker(f"{symbol}.TW")` 拉取台股資料
   - 提取最新的 OHLCV，加上當日成交量
   - 如果找不到，拋 `ValueError`

2. **stock_analyze()**：
   - 使用 `ta.momentum.RSIIndicator`, `ta.trend.MACD`, `ta.volatility.BollingerBands`, `ta.trend.SMAIndicator`
   - 計算 14-period RSI，12/26/9 MACD，20-period Bollinger，20/50/200-day SMA
   - 根據指標組合判斷趨勢和訊號
   - 生成簡短的中文分析摘要（e.g., "RSI 過高，賣壓增加")

**驗收**：
- 兩個函數都能 import
- `stock_fetch()` 返回包含 OHLCV 的字典
- `stock_analyze()` 返回 StockReport 物件
- 沒有語法錯誤

---

## Task 3 — 註冊 stock_fetch 和 stock_analyze 為 Tools

修改 `claw/tools/__init__.py` 和 `claw/tools/registry.py`，註冊兩個新工具。

**在 `claw/tools/__init__.py` 末尾加入**：

```python
from claw.tools.stock_tools import stock_fetch, stock_analyze

@register_tool()
def stock_fetch_tool(symbol: str, period: str = "1y") -> str:
    """Fetch stock OHLCV data from TWSE or Yahoo Finance."""
    try:
        result = stock_fetch(symbol, period)
        return json.dumps(result, default=str, ensure_ascii=False)
    except Exception as e:
        return f"Error: {e}"

@register_tool()
def stock_analyze_tool(symbol: str, period: str = "1y") -> str:
    """Analyze stock technical indicators and generate report."""
    try:
        fetch_result = stock_fetch(symbol, period)
        report = stock_analyze(symbol, fetch_result.get("ohlcv", []))
        return json.dumps(asdict(report), default=str, ensure_ascii=False)
    except Exception as e:
        return f"Error: {e}"
```

**驗收**：
- 執行 `python -c "from claw.tools import stock_fetch_tool, stock_analyze_tool; print('OK')"` 無誤
- Tools registry 能找到兩個新工具

---

## Task 4 — 更新 `pyproject.toml`

在 `dependencies` 下加入三個新套件：

```toml
[project]
dependencies = [
    # ... existing ...
    "yfinance>=0.2.50",
    "ta>=0.10.2",
    "mplfinance>=1.3.100",
]
```

**驗收**：
- 檔案語法正確，可被 pip 解析

---

## Task 5 — 建立單元測試 `tests/test_stock_tools.py`

建立 2 個測試，驗證核心邏輯（使用 mock）。

**檔案位置**：`tests/test_stock_tools.py`

**測試內容**：

```python
"""Unit tests for stock tools."""
import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock
from claw.tools.stock_tools import stock_fetch, stock_analyze
from claw.models.stock_report import StockReport


@pytest.mark.asyncio
async def test_stock_fetch_mock():
    """Test stock_fetch returns valid data structure."""
    with patch("claw.tools.stock_tools.yfinance.Ticker") as mock_ticker:
        # 模擬 yfinance 回應
        mock_hist = MagicMock()
        mock_hist.to_dict.return_value = {
            'Close': {'2026-03-22': 600.0},
            'High': {'2026-03-22': 605.0},
            'Low': {'2026-03-22': 595.0},
            'Volume': {'2026-03-22': 18500000},
        }
        mock_ticker.return_value.history.return_value = mock_hist

        result = stock_fetch("2330", period="1y")

        assert result["symbol"] == "2330"
        assert result["current"] > 0
        assert "ohlcv" in result


@pytest.mark.asyncio
async def test_stock_analyze_mock():
    """Test stock_analyze generates valid report."""
    mock_ohlcv = [
        {"date": "2026-03-20", "open": 598.0, "high": 603.0, "low": 595.0, "close": 601.0, "volume": 17500000},
        {"date": "2026-03-21", "open": 601.0, "high": 605.0, "low": 599.0, "close": 603.0, "volume": 18000000},
        {"date": "2026-03-22", "open": 603.0, "high": 605.0, "low": 595.0, "close": 600.0, "volume": 18500000},
    ]

    report = stock_analyze("2330", mock_ohlcv)

    assert isinstance(report, StockReport)
    assert report.symbol == "2330"
    assert report.current_price > 0
    assert report.indicators.rsi >= 0
    assert report.signal in ["strong_buy", "buy", "hold", "sell", "strong_sell"]
```

**驗收**：
- 兩個測試能成功執行
- 測試通過

---

## Task 6 — 執行測試

```bash
cd /home/martin/Desktop/claw-python-personal

# 安裝新依賴
pip install yfinance ta mplfinance

# 執行股票工具測試
python -m pytest tests/test_stock_tools.py -v

# 執行全部測試
python -m pytest tests/ -q --tb=short
```

**預期輸出**：
- `test_stock_fetch_mock` PASSED
- `test_stock_analyze_mock` PASSED
- 整體 `182 passed, 3 skipped`（新增 4 個測試，S0 已是 178）

---

## Task 7 — 驗證工具註冊

```bash
python -c "
from claw.tools.registry import get_tools
tools = get_tools()
stock_tools = [t for t in tools if 'stock' in t.lower()]
print(f'Stock tools found: {len(stock_tools)}')
for t in stock_tools:
    print(f'  - {t}')
assert len(stock_tools) >= 2, 'Should have at least 2 stock tools'
print('✅ Stock tools registered correctly')
"
```

**預期輸出**：至少 2 個 stock_* 工具被註冊

---

## 交付清單

完成後回報：

1. **新建的檔案絕對路徑**：
   - `/home/martin/Desktop/claw-python-personal/claw/models/stock_report.py`
   - `/home/martin/Desktop/claw-python-personal/claw/tools/stock_tools.py`
   - `/home/martin/Desktop/claw-python-personal/tests/test_stock_tools.py`

2. **修改的檔案絕對路徑**：
   - `/home/martin/Desktop/claw-python-personal/claw/tools/__init__.py`
   - `/home/martin/Desktop/claw-python-personal/pyproject.toml`

3. **pytest 最終輸出**（應為 182+ passed）

4. **工具註冊驗證結果**（應為 2+ stock tools）

5. **遇到的問題和解決方式**

---

## 完成標準

✅ StockReport 資料結構已建立（TechnicalIndicators + FundamentalData）
✅ stock_fetch() 能從 TWSE/Yahoo Finance 拉取資料
✅ stock_analyze() 能計算技術指標（RSI, MACD, Bollinger, SMA）
✅ 兩個工具已註冊到 registry
✅ 182+ tests pass, 0 failures
✅ pyproject.toml 已新增三個依賴
✅ 兩個單元測試通過

---

## 注意事項

- 優先使用 TWSE 官方 API（`query.sse.com.tw`），Yahoo Finance 為備用
- TechnicalIndicators 中的所有欄位都應該有預設值（避免 None 問題）
- stock_analyze() 應該在資料不足時優雅降級（e.g., 少於 200 筆資料時只計算可計算的指標）
- 中文分析摘要應簡潔明瞭（最多 2-3 句），供後續 Discord Embed 使用
- 不要改動既有的 tools（只新增）

