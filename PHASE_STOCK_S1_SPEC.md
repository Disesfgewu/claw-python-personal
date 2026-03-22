# Phase S1 完整實現規範 — Stock Tools + Chart Generation

> 目標：建立股票分析的核心工具層，能實時分析個股並生成 K 線圖

---

## 新增檔案清單（Phase S1）

```
claw/tools/stock_tools.py          # 核心股票工具（fetch, analyze, screen, chip）
claw/tools/chart_tools.py          # K線圖生成
claw/models/stock_report.py        # 股票報告數據結構
claw/research/stock_strategy.py    # 股票策略回測框架（S4 用，先建立空框架）
tests/test_stock_tools.py          # 單元測試
tests/test_chart_tools.py          # 圖表測試
skills/taiwan-stock/SKILL.md       # 台股分析 Skill
```

---

## 1. `claw/models/stock_report.py` — 資料結構

```python
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import pandas as pd


@dataclass
class TechnicalIndicators:
    """技術指標計算結果"""
    ma_20: float
    ma_50: float
    ma_200: float
    rsi_14: float
    macd: float
    macd_signal: float
    macd_hist: float
    kd_k: float
    kd_d: float

    @property
    def ma_signal(self) -> str:
        """MA 訊號：金叉/死叉/平"""
        if self.ma_20 > self.ma_50 > self.ma_200:
            return "金叉 ⬆"
        elif self.ma_20 < self.ma_50 < self.ma_200:
            return "死叉 ⬇"
        else:
            return "平"

    @property
    def rsi_signal(self) -> str:
        """RSI 訊號"""
        if self.rsi_14 > 70:
            return "超買"
        elif self.rsi_14 < 30:
            return "超賣"
        else:
            return "中立"

    @property
    def macd_signal(self) -> str:
        """MACD 訊號"""
        if self.macd > self.macd_signal:
            return "看漲 🟢"
        else:
            return "看跌 🔴"


@dataclass
class FundamentalData:
    """基本面資料"""
    pe_ratio: Optional[float] = None
    pb_ratio: Optional[float] = None
    roe: Optional[float] = None
    dividend_yield: Optional[float] = None
    debt_ratio: Optional[float] = None

    @property
    def fundamental_score(self) -> float:
        """簡單基本面評分 0-100"""
        score = 50  # 基礎分

        if self.pe_ratio:
            # PE < 15 時給分
            if 10 < self.pe_ratio < 15:
                score += 10
            elif self.pe_ratio < 10:
                score += 5

        if self.pb_ratio:
            if 1.0 < self.pb_ratio < 2.0:
                score += 10

        if self.roe and self.roe > 15:
            score += 15

        if self.dividend_yield and self.dividend_yield > 3:
            score += 10

        return min(100, score)


@dataclass
class NewsItem:
    """新聞項目"""
    title: str
    url: str
    sentiment: str  # "正面" | "負面" | "中立"
    published_at: str


@dataclass
class StockReport:
    """完整股票分析報告"""
    symbol: str
    name: str

    # 價格資訊
    current_price: float
    change_pct: float
    change_amount: float

    # 技術面
    indicators: TechnicalIndicators

    # 基本面
    fundamental: FundamentalData

    # 新聞 + 情緒（S3 才用）
    news: list[NewsItem] = field(default_factory=list)
    sentiment_score: float = 0.5  # 0-1, 0.5 = 中立

    # 圖表（bytes）
    chart_bytes: Optional[bytes] = None

    # 最終建議
    recommendation: str = "觀望"
    confidence: float = 0.0

    # 生成時間
    generated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_embed_description(self) -> str:
        """轉成 Discord Embed 描述"""
        return f"""
**{self.symbol} {self.name}**
現價: ${self.current_price:,.2f} {self.change_pct:+.2f}%

**技術面**
MA: {self.indicators.ma_signal}
RSI: {self.rsi_signal} ({self.indicators.rsi_14:.1f})
MACD: {self.indicators.macd_signal}

**基本面**
PE比: {self.fundamental.pe_ratio or 'N/A'}
ROE: {self.fundamental.roe or 'N/A'}%
評分: {self.fundamental.fundamental_score}/100

**建議**: {self.recommendation} (信心: {self.confidence*100:.0f}%)
"""
```

---

## 2. `claw/tools/stock_tools.py` — 核心工具

```python
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd
import numpy as np
import httpx
import ta  # pip install ta

from claw.tools.registry import tool
from claw.models.stock_report import (
    StockReport,
    TechnicalIndicators,
    FundamentalData,
)
from claw.core.config import get_config

logger = logging.getLogger(__name__)

# TWSE API endpoints
TWSE_API_HIST = "https://query.sse.com.tw/StockInfo/StockData.aspx"  # 或 mds.twse.com.tw
YAHOO_FINANCE = "https://query1.finance.yahoo.com"


@tool(
    name="stock_fetch",
    description="從 TWSE/Yahoo Finance 抓取股票歷史行情（OHLCV）。返回 DataFrame。",
    parameters={
        "type": "object",
        "properties": {
            "symbol": {
                "type": "string",
                "description": "股票代碼，例如 '2330' (台積電) 或 '0050' (元大台灣50)",
            },
            "period": {
                "type": "string",
                "enum": ["1mo", "3mo", "6mo", "1y", "max"],
                "default": "3mo",
                "description": "時間區間",
            },
        },
        "required": ["symbol"],
    },
    requires_main=False,
)
async def stock_fetch(
    symbol: str,
    period: str = "3mo",
    session_id: str = "agent:main",
) -> str:
    """
    Fetch historical OHLCV data from TWSE (priority) or Yahoo Finance (fallback).

    Returns JSON string with columns: Date, Open, High, Low, Close, Volume
    """
    try:
        # 策略：先嘗試 TWSE 爬蟲（最可靠）
        df = await _fetch_from_twse_crawler(symbol, period)

        if df is None or df.empty:
            # fallback 到 Yahoo Finance
            logger.info(f"TWSE fetch failed for {symbol}, falling back to Yahoo Finance")
            df = await _fetch_from_yahoo(symbol, period)

        if df is None or df.empty:
            return f"Error: Could not fetch data for {symbol}"

        # 轉成 JSON 回傳
        return df.to_json(orient="records", date_format="iso")

    except Exception as e:
        logger.error(f"stock_fetch({symbol}) failed: {e}")
        return f"Error: {type(e).__name__}: {e}"


async def _fetch_from_twse_crawler(symbol: str, period: str) -> Optional[pd.DataFrame]:
    """
    使用 ga642381/Taiwan-Stock-Crawler 的邏輯
    或直接呼叫 TWSE 官方 API
    """
    try:
        # TODO: 根據實際 TWSE API 實作
        # 這裡假設有 subprocess 呼叫或直接 HTTP 呼叫
        # 簡化版：直接用 yfinance fallback
        return None
    except Exception as e:
        logger.error(f"TWSE crawler error: {e}")
        return None


async def _fetch_from_yahoo(symbol: str, period: str) -> Optional[pd.DataFrame]:
    """
    從 Yahoo Finance 拿資料（備用源）
    """
    try:
        # yfinance 是異步的，用 asyncio 包裝
        import yfinance as yf

        # 轉換股票代碼（台股加 .TW 後綴）
        ticker = f"{symbol}.TW" if len(symbol) == 4 else symbol

        # period_map
        period_days = {
            "1mo": 30,
            "3mo": 90,
            "6mo": 180,
            "1y": 365,
            "max": 3650,
        }
        days = period_days.get(period, 90)

        # 用 executor 包裝同步呼叫
        loop = asyncio.get_event_loop()
        df = await loop.run_in_executor(
            None,
            lambda: yf.download(ticker, period=period, progress=False)
        )

        return df if df is not None and not df.empty else None

    except Exception as e:
        logger.error(f"Yahoo Finance fetch error: {e}")
        return None


@tool(
    name="stock_analyze",
    description="分析個股：計算技術指標、基本面評分、生成 K 線圖。返回 StockReport JSON。",
    parameters={
        "type": "object",
        "properties": {
            "symbol": {
                "type": "string",
                "description": "股票代碼",
            },
            "period": {
                "type": "string",
                "default": "3mo",
            },
        },
        "required": ["symbol"],
    },
    requires_main=False,
)
async def stock_analyze(
    symbol: str,
    period: str = "3mo",
    session_id: str = "agent:main",
) -> str:
    """
    Complete stock analysis: technical + fundamental + chart generation.
    """
    try:
        # Step 1: Fetch data
        ohlcv_json = await stock_fetch(symbol, period)
        if "Error" in ohlcv_json:
            return ohlcv_json

        df = pd.read_json(ohlcv_json)
        df['Date'] = pd.to_datetime(df.get('Date', df.index))
        df = df.set_index('Date').sort_index()

        # Step 2: Calculate technical indicators
        indicators = _calculate_indicators(df)

        # Step 3: Fetch fundamental data (from Yahoo Finance or AKShare)
        fundamental = await _fetch_fundamental(symbol)

        # Step 4: Generate chart
        chart_bytes = await _generate_chart(symbol, df, indicators)

        # Step 5: Build recommendation
        recommendation = _build_recommendation(indicators, fundamental)

        # Step 6: Create report
        current_price = df['Close'].iloc[-1]
        prev_price = df['Close'].iloc[-2] if len(df) > 1 else current_price
        change_pct = (current_price - prev_price) / prev_price * 100

        report = StockReport(
            symbol=symbol,
            name=await _fetch_stock_name(symbol),
            current_price=current_price,
            change_pct=change_pct,
            change_amount=current_price - prev_price,
            indicators=indicators,
            fundamental=fundamental,
            recommendation=recommendation,
            confidence=0.75,
            chart_bytes=chart_bytes,
        )

        # 回傳 JSON（chart_bytes 編碼為 base64）
        import json
        import base64

        report_dict = {
            'symbol': report.symbol,
            'name': report.name,
            'current_price': report.current_price,
            'change_pct': report.change_pct,
            'indicators': {
                'ma_signal': report.indicators.ma_signal,
                'rsi_signal': report.indicators.rsi_signal,
                'macd_signal': report.indicators.macd_signal,
            },
            'recommendation': report.recommendation,
            'chart_base64': base64.b64encode(report.chart_bytes).decode() if report.chart_bytes else None,
        }

        return json.dumps(report_dict, ensure_ascii=False)

    except Exception as e:
        logger.error(f"stock_analyze({symbol}) failed: {e}")
        return f"Error: {type(e).__name__}: {e}"


def _calculate_indicators(df: pd.DataFrame) -> TechnicalIndicators:
    """計算所有技術指標"""
    close = df['Close'].values
    high = df['High'].values
    low = df['Low'].values

    return TechnicalIndicators(
        ma_20=ta.trend.sma_indicator(pd.Series(close), window=20).iloc[-1],
        ma_50=ta.trend.sma_indicator(pd.Series(close), window=50).iloc[-1],
        ma_200=ta.trend.sma_indicator(pd.Series(close), window=200).iloc[-1],
        rsi_14=ta.momentum.rsi(pd.Series(close), window=14).iloc[-1],
        macd=ta.trend.macd(pd.Series(close)).iloc[-1],
        macd_signal=ta.trend.macd_signal(pd.Series(close)).iloc[-1],
        macd_hist=ta.trend.macd_diff(pd.Series(close)).iloc[-1],
        kd_k=_calculate_kd(close, high, low)[0],
        kd_d=_calculate_kd(close, high, low)[1],
    )


def _calculate_kd(close: np.ndarray, high: np.ndarray, low: np.ndarray) -> tuple[float, float]:
    """KD 指標計算（簡化版）"""
    # TODO: 實作完整的 KD 指標
    return (50.0, 50.0)


async def _fetch_fundamental(symbol: str) -> FundamentalData:
    """從 Yahoo Finance 或 AKShare 拿基本面資料"""
    try:
        import yfinance as yf
        ticker_obj = yf.Ticker(f"{symbol}.TW")
        info = ticker_obj.info

        return FundamentalData(
            pe_ratio=info.get('trailingPE'),
            pb_ratio=info.get('priceToBook'),
            roe=info.get('returnOnEquity'),
            dividend_yield=info.get('dividendYield'),
            debt_ratio=info.get('debtToEquity'),
        )
    except Exception as e:
        logger.warning(f"Could not fetch fundamental data for {symbol}: {e}")
        return FundamentalData()


async def _fetch_stock_name(symbol: str) -> str:
    """從 TWSE 拿股票名稱"""
    try:
        # TODO: 呼叫 TWSE 公司名稱查詢
        return symbol
    except:
        return symbol


async def _generate_chart(
    symbol: str,
    df: pd.DataFrame,
    indicators: TechnicalIndicators
) -> bytes:
    """生成 K 線圖（委派給 chart_tools）"""
    from claw.tools.chart_tools import generate_candlestick_chart

    return await generate_candlestick_chart(symbol, df, indicators)


def _build_recommendation(
    indicators: TechnicalIndicators,
    fundamental: FundamentalData
) -> str:
    """根據指標生成買賣建議"""
    score = 0

    # 技術面打分
    if indicators.ma_20 > indicators.ma_50:
        score += 1
    if indicators.rsi_14 < 30:
        score += 1
    if indicators.macd > indicators.macd_signal:
        score += 1

    # 基本面打分
    if fundamental.pe_ratio and 10 < fundamental.pe_ratio < 20:
        score += 1
    if fundamental.roe and fundamental.roe > 15:
        score += 1

    if score >= 4:
        return "買進 🟢"
    elif score >= 2:
        return "觀望 🟡"
    else:
        return "賣出 🔴"


# Phase S2 工具（先建立空框架）

@tool(
    name="stock_screen",
    description="篩選股票：根據條件掃描指定池子（e.g., 台灣50）。",
    parameters={
        "type": "object",
        "properties": {
            "pool": {
                "type": "string",
                "default": "tw50",
                "description": "股票池：tw50 | twx | all",
            },
            "criteria": {
                "type": "string",
                "description": "篩選條件 JSON，例如：{\"rsi_threshold\": 30, \"ma_signal\": \"金叉\"}",
            },
        },
        "required": ["pool"],
    },
    requires_main=False,
)
async def stock_screen(
    pool: str = "tw50",
    criteria: str = "{}",
    session_id: str = "agent:main",
) -> str:
    """
    Screen stocks from a pool based on criteria.
    S2 task: 實作完整邏輯
    """
    # TODO: S2 實作
    return "stock_screen not yet implemented (Phase S2)"


@tool(
    name="stock_chip",
    description="籌碼分析：查詢法人買賣超、融資融券等。",
    parameters={
        "type": "object",
        "properties": {
            "symbol": {
                "type": "string",
                "description": "股票代碼",
            },
        },
        "required": ["symbol"],
    },
    requires_main=False,
)
async def stock_chip(
    symbol: str,
    session_id: str = "agent:main",
) -> str:
    """
    Fetch chip data (foreign investors, investment trusts, etc.)
    S2 task: 實作完整邏輯
    """
    # TODO: S2 實作
    return "stock_chip not yet implemented (Phase S2)"
```

---

## 3. `claw/tools/chart_tools.py` — 圖表生成

```python
from __future__ import annotations

import asyncio
import io
import logging
from typing import Optional

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.dates import DateFormatter
import mplfinance as mpf

from claw.tools.registry import tool
from claw.models.stock_report import TechnicalIndicators

logger = logging.getLogger(__name__)


async def generate_candlestick_chart(
    symbol: str,
    df: pd.DataFrame,
    indicators: TechnicalIndicators,
    width: int = 12,
    height: int = 6,
) -> bytes:
    """
    Generate a candlestick chart with technical indicators.
    Returns PNG bytes.
    """
    try:
        loop = asyncio.get_event_loop()
        png_bytes = await loop.run_in_executor(
            None,
            _generate_chart_sync,
            symbol,
            df,
            indicators,
            width,
            height,
        )
        return png_bytes
    except Exception as e:
        logger.error(f"Chart generation failed: {e}")
        return b""


def _generate_chart_sync(
    symbol: str,
    df: pd.DataFrame,
    indicators: TechnicalIndicators,
    width: int,
    height: int,
) -> bytes:
    """
    Synchronous chart generation using mplfinance.
    """
    # 確保索引是 DatetimeIndex
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)

    # 準備資料
    ohlc_df = df[['Open', 'High', 'Low', 'Close', 'Volume']].copy()

    # 添加 MA 線
    ohlc_df['MA20'] = df['Close'].rolling(20).mean()
    ohlc_df['MA50'] = df['Close'].rolling(50).mean()
    ohlc_df['MA200'] = df['Close'].rolling(200).mean()

    # 用 mplfinance 生成 K 線圖
    # 注意：mplfinance 預期 OHLC 順序
    apds = [
        mpf.make_addplot(ohlc_df['MA20'], color='orange', width=1.5),
        mpf.make_addplot(ohlc_df['MA50'], color='blue', width=1.5),
        mpf.make_addplot(ohlc_df['MA200'], color='red', width=1.5),
    ]

    # 圖表設定
    style = mpf.make_mpf_style(base_mpl_style='seaborn-v0_8-darkgrid')

    # 生成圖表到 BytesIO
    buf = io.BytesIO()

    mpf.plot(
        ohlc_df[-100:],  # 只顯示最近 100 根 K 線
        type='candle',
        style=style,
        title=f'{symbol} K線圖 (MA20/50/200)',
        ylabel='Price (TWD)',
        volume=True,
        addplot=apds,
        returnfig=False,
        savefig=dict(fname=buf, dpi=100, pad_inches=0.3),
    )

    buf.seek(0)
    return buf.getvalue()


@tool(
    name="generate_chart",
    description="生成 K 線圖。",
    parameters={
        "type": "object",
        "properties": {
            "symbol": {"type": "string"},
            "period": {"type": "string", "default": "3mo"},
        },
        "required": ["symbol"],
    },
    requires_main=False,
)
async def generate_chart(
    symbol: str,
    period: str = "3mo",
    session_id: str = "agent:main",
) -> str:
    """
    Generate and return a candlestick chart for a stock.
    Wrapper around generate_candlestick_chart.
    """
    from claw.tools.stock_tools import stock_fetch

    try:
        # Fetch data
        ohlcv_json = await stock_fetch(symbol, period)
        if "Error" in ohlcv_json:
            return ohlcv_json

        df = pd.read_json(ohlcv_json)
        df['Date'] = pd.to_datetime(df.get('Date', df.index))
        df = df.set_index('Date').sort_index()

        # Generate chart
        chart_bytes = await generate_candlestick_chart(symbol, df, None)

        # Return as base64
        import base64
        b64 = base64.b64encode(chart_bytes).decode()
        return f"Chart generated. Base64: {b64[:50]}..."

    except Exception as e:
        return f"Error: {type(e).__name__}: {e}"
```

---

## 4. `skills/taiwan-stock/SKILL.md`

```markdown
# 台股基礎分析 Skill

## 說明
台灣股市實時分析和技術面評估。

## 工具
- `stock_fetch` — 拉取歷史行情
- `stock_analyze` — 完整分析（技術+基本面+圖表）
- `generate_chart` — 單獨生成 K 線圖

## Prompt

你是台股投資顧問。當用戶要求分析股票時：

1. **理解需求** — 用戶問的是哪支股票？分析時間？
2. **拉取資料** — 用 `stock_fetch` 取近期行情
3. **分析指標** — 用 `stock_analyze` 計算技術面 + 基本面
4. **給出建議** — 根據 MA/RSI/MACD/基本面評分，給出「買進/觀望/賣出」
5. **輸出格式** — 如果是 Discord，用 Embed 格式；如果是 Telegram，用 Markdown

## 範例對話

**用戶：** 分析台積電（2330）

**助手：**
1. 正在獲取台積電近 3 個月的行情...
2. 計算技術指標...
3. 取得基本面資料...
4. 生成分析報告...

**結果：**
```
2330 台積電
現價: $589.00 (+2.1%)

技術面
- MA: 金叉 ⬆ (短期向上)
- RSI: 中立 (62.3)
- MACD: 看漲 🟢

基本面
- PE比: 24.3x
- ROE: 32.5%
- 評分: 72/100

建議: 買進 🟢 (信心: 75%)
```

## 局限
- 不做期貨或選擇權分析
- 資料延遲 15 分鐘（Yahoo Finance 限制）
- 技術指標只是參考，不代表投資建議
```

---

## 5. 新增 `claw/main.py` imports

```python
import claw.tools.stock_tools
import claw.tools.chart_tools
```

在工具 import 區塊加入。

---

## 6. 單元測試 — `tests/test_stock_tools.py`

```python
from __future__ import annotations

import pytest
import pandas as pd
import json
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_stock_fetch_success():
    """stock_fetch returns OHLCV JSON."""
    from claw.tools.stock_tools import stock_fetch

    # Mock the Yahoo Finance fetch
    mock_df = pd.DataFrame({
        'Date': pd.date_range('2026-01-01', periods=10),
        'Open': [100] * 10,
        'High': [102] * 10,
        'Low': [98] * 10,
        'Close': [101] * 10,
        'Volume': [1000000] * 10,
    })

    with patch('claw.tools.stock_tools._fetch_from_twse_crawler', return_value=None):
        with patch('claw.tools.stock_tools._fetch_from_yahoo', return_value=mock_df):
            result = await stock_fetch("2330", period="3mo")

    assert "Error" not in result
    data = json.loads(result)
    assert len(data) == 10
    assert 'Close' in data[0]


@pytest.mark.asyncio
async def test_stock_analyze_success():
    """stock_analyze returns StockReport JSON with all fields."""
    from claw.tools.stock_tools import stock_analyze

    # Mock the fetch and fundamental data
    mock_df = pd.DataFrame({
        'Date': pd.date_range('2026-01-01', periods=50),
        'Open': [100 + i*0.5 for i in range(50)],
        'High': [102 + i*0.5 for i in range(50)],
        'Low': [98 + i*0.5 for i in range(50)],
        'Close': [101 + i*0.5 for i in range(50)],
        'Volume': [1000000] * 50,
    })

    with patch('claw.tools.stock_tools.stock_fetch') as mock_fetch:
        with patch('claw.tools.stock_tools._fetch_fundamental') as mock_fund:
            with patch('claw.tools.stock_tools._generate_chart') as mock_chart:
                mock_fetch.return_value = mock_df.to_json(orient='records')
                mock_fund.return_value = None
                mock_chart.return_value = b'PNG_DATA'

                result = await stock_analyze("2330")

    assert "Error" not in result
    report = json.loads(result)
    assert report['symbol'] == '2330'
    assert 'current_price' in report
    assert 'recommendation' in report
    assert 'chart_base64' in report
```

---

## 驗收標準 (Phase S1)

✅ 3 個新工具註冊成功 (`stock_fetch`, `stock_analyze`, `generate_chart`)
✅ `stock_analyze("2330")` 回傳完整報告（含 K 線圖 base64）
✅ 所有新增單元測試通過
✅ Skill SKILL.md 已建立
✅ Tests 從 167 → 170+ (新增 3+ 個測試)
✅ 伺服器啟動無錯誤

---

## 依賴

需要安裝：
```bash
pip install yfinance pandas-ta mplfinance
```

更新 `pyproject.toml`:
```toml
dependencies = [
    ...existing...,
    "yfinance>=0.2.30",
    "ta>=0.10.0",  # Technical Analysis library
    "mplfinance>=0.12.9",
]
```
