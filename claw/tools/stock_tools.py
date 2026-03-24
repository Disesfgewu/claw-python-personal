from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta
from typing import Optional, Any

import pandas as pd
import numpy as np
import httpx
from typing import Any, cast
import ta  # type: ignore

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

_stock_data_cache: dict[str, tuple[datetime, dict]] = {}
STOCK_DATA_CACHE_TTL = 3600

def _get_stock_cache(cache_key: str) -> dict | None:
    if cache_key not in _stock_data_cache:
        return None
    cached_time, cached_data = _stock_data_cache[cache_key]
    if datetime.now() - cached_time < timedelta(seconds=STOCK_DATA_CACHE_TTL):
        return cached_data
    _stock_data_cache.pop(cache_key, None)
    return None

def _set_stock_cache(cache_key: str, data: dict) -> None:
    _stock_data_cache[cache_key] = (datetime.now(), data)


def _safe_last(series: Any, fallback: float = 0.0) -> float:
    try:
        value = series.iloc[-1]
    except Exception:
        return float(fallback)
    if pd.isna(value):
        return float(fallback)
    return float(value)


def _normalize_df(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df

    # Handle MultiIndex columns (from yfinance multi-ticker downloads)
    if isinstance(df.columns, pd.MultiIndex):
        # For single ticker, extract the first (and only) ticker level
        if df.columns.nlevels == 2:
            # Get the first level values (Price columns: Close, High, Low, Open, Volume)
            df.columns = df.columns.get_level_values(0)

    # Ensure Date is a column, not index
    if 'Date' not in df.columns:
        df = df.reset_index()
        if 'index' in df.columns and 'Date' not in df.columns:
            df = df.rename(columns={'index': 'Date'})

    return df


def _build_ohlcv_list(df: pd.DataFrame) -> list[dict]:
    if df is None or df.empty:
        return []
    df = _normalize_df(df.copy())
    records = []
    for _, row in df.iterrows():
        date_val = row.get('Date') if hasattr(row, 'get') else row['Date'] if 'Date' in row.index else None
        if isinstance(date_val, pd.Timestamp):
            date_str = date_val.date().isoformat()
        else:
            date_str = str(date_val) if date_val is not None else ""

        # Safely extract OHLCV values, handling NaN and missing data
        def safe_float(val, default=0.0):
            if val is None or (isinstance(val, float) and pd.isna(val)):
                return default
            try:
                return float(val)
            except (TypeError, ValueError):
                return default

        def safe_int(val, default=0):
            if val is None or (isinstance(val, float) and pd.isna(val)):
                return default
            try:
                return int(val)
            except (TypeError, ValueError):
                return default

        records.append({
            "date": date_str,
            "open": safe_float(row.get('Open', None) if hasattr(row, 'get') else row.get('Open') if 'Open' in row.index else None),
            "high": safe_float(row.get('High', None) if hasattr(row, 'get') else row.get('High') if 'High' in row.index else None),
            "low": safe_float(row.get('Low', None) if hasattr(row, 'get') else row.get('Low') if 'Low' in row.index else None),
            "close": safe_float(row.get('Close', None) if hasattr(row, 'get') else row.get('Close') if 'Close' in row.index else None),
            "volume": safe_int(row.get('Volume', None) if hasattr(row, 'get') else row.get('Volume') if 'Volume' in row.index else None),
        })
    return records


def _build_fetch_result(symbol: str, df: pd.DataFrame, name: str | None = None) -> dict:
    df = _normalize_df(df)
    if df is None or df.empty:
        raise ValueError(f"No data for {symbol}")
    ohlcv = _build_ohlcv_list(df)
    last = ohlcv[-1] if ohlcv else {}
    prev_close = ohlcv[-2]["close"] if len(ohlcv) > 1 else last.get("close", 0)
    return {
        "symbol": symbol,
        "name": name or symbol,
        "current": last.get("close", 0),
        "previous_close": prev_close,
        "high": last.get("high", 0),
        "low": last.get("low", 0),
        "volume": last.get("volume", 0),
        "timestamp": last.get("date", datetime.now().isoformat()),
        "ohlcv": ohlcv,
    }


async def _stock_fetch_impl_async(
    symbol: str,
    period: str,
    source: str,
) -> dict:
    df = None
    if source in ("auto", "twse"):
        df = await _fetch_from_twse_crawler(symbol, period)
    if (df is None or df.empty) and source in ("auto", "yahoo"):
        df = await _fetch_from_yahoo(symbol, period)
    if df is None or df.empty:
        raise ValueError(f"Could not fetch data for {symbol}")
    name = await _fetch_stock_name(symbol)
    return _build_fetch_result(symbol, df, name=name)


def _stock_fetch_impl(
    symbol: str,
    period: str,
    source: str,
) -> dict:
    df = None
    if source in ("auto", "twse"):
        df = _fetch_from_twse_crawler_sync(symbol, period)
    if (df is None or df.empty) and source in ("auto", "yahoo"):
        df = _fetch_from_yahoo_sync(symbol, period)
    if df is None or df.empty:
        raise ValueError(f"Could not fetch data for {symbol}")
    return _build_fetch_result(symbol, df, name=symbol)


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
        fetch_result = await stock_fetch_data(
            symbol,
            period=period,
            source="auto",
            use_cache=True,
            max_retries=3,
        )
        df = _ohlcv_to_df(fetch_result.get("ohlcv", []))
        df = df.reset_index()
        res = df.to_json(orient="records", date_format="iso")
        return str(res) if res is not None else "[]"
    except Exception as e:
        logger.error(f"stock_fetch({symbol}) failed: {e}")
        return f"Error: {type(e).__name__}: {e}"


async def stock_fetch_data(
    symbol: str,
    period: str = "1y",
    source: str = "auto",
    use_cache: bool = True,
    max_retries: int = 3,
) -> dict:
    """Structured data wrapper for stock fetch (dict + OHLCV list)."""
    cache_key = f"{symbol}:{period}:{source}"
    if use_cache:
        cached = _get_stock_cache(cache_key)
        if cached is not None:
            logger.debug(f"Stock data cache hit for {symbol}")
            return cached

    for attempt in range(max_retries):
        try:
            result = await _stock_fetch_impl_async(symbol, period, source)
            if use_cache:
                _set_stock_cache(cache_key, result)
            return result
        except ConnectionError as e:
            logger.warning(f"Connection error (attempt {attempt+1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(2 ** attempt)
                continue
            raise
        except ValueError as e:
            logger.error(f"Invalid symbol or data: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error: {e}", exc_info=True)
            raise

    raise ValueError(f"Could not fetch data for {symbol}")


def stock_fetch_data_sync(
    symbol: str,
    period: str = "1y",
    source: str = "auto",
    use_cache: bool = True,
    max_retries: int = 3,
) -> dict:
    """Sync wrapper for stock_fetch_data to avoid awaiting in sync flows."""
    cache_key = f"{symbol}:{period}:{source}"
    if use_cache:
        cached = _get_stock_cache(cache_key)
        if cached is not None:
            logger.debug(f"Stock data cache hit for {symbol}")
            return cached

    for attempt in range(max_retries):
        try:
            result = _stock_fetch_impl(symbol, period, source)
            if use_cache:
                _set_stock_cache(cache_key, result)
            return result
        except ConnectionError as e:
            logger.warning(f"Connection error (attempt {attempt+1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
            raise
        except ValueError as e:
            logger.error(f"Invalid symbol or data: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error: {e}", exc_info=True)
            raise

    raise ValueError(f"Could not fetch data for {symbol}")


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


def _fetch_from_twse_crawler_sync(symbol: str, period: str) -> Optional[pd.DataFrame]:
    """Sync version of TWSE fetch (currently not implemented)."""
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


def _fetch_from_yahoo_sync(symbol: str, period: str) -> Optional[pd.DataFrame]:
    """Sync Yahoo Finance fetch (for stock_screen and other sync flows)."""
    try:
        import yfinance as yf
        ticker = f"{symbol}.TW" if len(symbol) == 4 else symbol
        df = yf.download(ticker, period=period, progress=False)
        return df if df is not None and not df.empty else None
    except Exception as e:
        logger.error(f"Yahoo Finance fetch error (sync): {e}")
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

        try:
            ohlcv_list = json.loads(ohlcv_json)
        except Exception:
            return "Error: invalid OHLCV json"

        df = _ohlcv_to_df(ohlcv_list)

        # Step 2: Calculate technical indicators
        report = stock_analyze_report(symbol, ohlcv_list)

        # Step 3: Fetch fundamental data (from Yahoo Finance or AKShare)
        fundamental = await _fetch_fundamental(symbol)
        report.fundamental = fundamental

        # Step 4: Generate chart (暫時 skip，委派給 S1b)
        report.chart_bytes = await _generate_chart(symbol, df, report.indicators)

        # Step 5: Build recommendation
        report.recommendation = _build_recommendation(report.indicators, fundamental)
        if not report.signal:
            report.signal = _recommendation_to_signal(report.recommendation)

        # Step 5b: News sentiment (non-blocking — runs in thread)
        try:
            news_list = await asyncio.to_thread(stock_news, symbol, 3)
            news_sentiment = sentiment_analyze(news_list)
            if hasattr(report, 'fundamentals') and report.fundamentals:
                report.fundamentals.news_sentiment = news_sentiment.get('overall_sentiment', 'neutral')
            if news_list:
                summary = news_sentiment.get('summary', '')
                advice = news_sentiment.get('advice', '')
                if advice:
                    report.summary += f" | 新聞情緒: {summary}（{advice}）"
                else:
                    report.summary += f" | 新聞情緒: {summary}"
        except Exception as e:
            logger.warning(f"News fetch skipped for {symbol}: {e}")

        # 回傳 JSON（chart_bytes 編碼為 base64）
        import base64

        report_dict = {
            'symbol': report.symbol,
            'name': report.name,
            'current_price': float(report.current_price),
            'change_pct': float(report.change_pct),
            'change_amount': float(report.change_amount),
            'previous_close': float(report.previous_close),
            'day_high': float(report.day_high),
            'day_low': float(report.day_low),
            'volume': int(report.volume),
            'timestamp': report.timestamp,
            'trend': report.trend,
            'signal': report.signal,
            'summary': report.summary,
            'indicators': {
                'ma_5': float(report.indicators.ma_5),
                'ma_10': float(report.indicators.ma_10),
                'ma_20': float(report.indicators.ma_20),
                'ma_50': float(report.indicators.ma_50),
                'ma_200': float(report.indicators.ma_200),
                'rsi_5': float(report.indicators.rsi_5),
                'rsi_10': float(report.indicators.rsi_10),
                'rsi_14': float(report.indicators.rsi_14),
                'macd': float(report.indicators.macd),
                'macd_signal': float(report.indicators.macd_signal),
                'macd_hist': float(report.indicators.macd_hist),
                'osc': float(report.indicators.macd_hist),  # OSC = MACD hist
                'kd_k': float(report.indicators.kd_k),
                'kd_d': float(report.indicators.kd_d),
                'bollinger_upper': float(report.indicators.bollinger_upper),
                'bollinger_middle': float(report.indicators.bollinger_middle),
                'bollinger_lower': float(report.indicators.bollinger_lower),
                'vol_5': float(report.indicators.vol_5),
                'vol_10': float(report.indicators.vol_10),
                'ma_signal': report.indicators.ma_signal,
                'rsi_signal': report.indicators.rsi_signal,
                'macd_signal_str': report.indicators.macd_signal_str,
            },
            'fundamental': {
                'pe_ratio': report.fundamental.pe_ratio,
                'pb_ratio': report.fundamental.pb_ratio,
                'roe': report.fundamental.roe,
                'dividend_yield': report.fundamental.dividend_yield,
                'debt_ratio': report.fundamental.debt_ratio,
                'market_cap': report.fundamental.market_cap,
                'industry': report.fundamental.industry,
                'fundamental_score': float(report.fundamental.fundamental_score),
            },
            'recommendation': report.recommendation,
            'confidence': float(report.confidence),
            'chart_base64': base64.b64encode(report.chart_bytes).decode() if report.chart_bytes else None,
        }

        return json.dumps(report_dict, ensure_ascii=False)

    except Exception as e:
        logger.error(f"stock_analyze({symbol}) failed: {e}")
        return f"Error: {type(e).__name__}: {e}"


def stock_analyze_report(symbol: str, ohlcv_list: list[dict]) -> StockReport:
    """S1A structured analysis: return StockReport from OHLCV list."""
    df = _ohlcv_to_df(ohlcv_list)
    indicators = _calculate_indicators(df)

    current_price = float(df['Close'].iloc[-1])
    prev_price = float(df['Close'].iloc[-2]) if len(df) > 1 else current_price
    change_pct = (current_price - prev_price) / prev_price * 100 if prev_price else 0.0
    change_amount = current_price - prev_price

    last_row = df.iloc[-1]
    previous_close = prev_price
    day_high = float(last_row.get('High', current_price))
    day_low = float(last_row.get('Low', current_price))
    volume = int(last_row.get('Volume', 0) or 0)
    timestamp = str(last_row.get('Date', datetime.now().isoformat()))

    trend = _build_trend(indicators, current_price)
    signal = _build_signal(indicators)
    summary = _build_summary(indicators, signal)

    report = StockReport(
        symbol=symbol,
        name=symbol,
        current_price=current_price,
        change_pct=change_pct,
        change_amount=change_amount,
        indicators=indicators,
        fundamental=FundamentalData(),
        previous_close=previous_close,
        day_high=day_high,
        day_low=day_low,
        volume=volume,
        timestamp=timestamp,
        trend=trend,
        signal=signal,
        summary=summary,
    )
    
    return report


def _ohlcv_to_df(ohlcv_list: list[dict]) -> pd.DataFrame:
    if not ohlcv_list:
        raise ValueError("OHLCV list is empty")
    df = pd.DataFrame(ohlcv_list)
    # Normalize column names
    cols = {c.lower(): c for c in df.columns}
    if 'date' in cols:
        df['Date'] = pd.to_datetime(df[cols['date']])
    elif 'Date' in df.columns:
        df['Date'] = pd.to_datetime(df['Date'])
    else:
        df['Date'] = pd.date_range(end=datetime.now(), periods=len(df))
    df = df.rename(columns={
        cols.get('open', 'open'): 'Open',
        cols.get('high', 'high'): 'High',
        cols.get('low', 'low'): 'Low',
        cols.get('close', 'close'): 'Close',
        cols.get('volume', 'volume'): 'Volume',
    })
    df = df[['Date', 'Open', 'High', 'Low', 'Close', 'Volume']]
    df = df.set_index('Date').sort_index()
    return df


def _calculate_indicators(df: pd.DataFrame) -> TechnicalIndicators:
    """計算所有技術指標"""
    close = df['Close']
    high = df['High']
    low = df['Low']
    volume = df['Volume'].astype(float)

    ta_a = cast(Any, ta)

    # 均線
    ma_5  = _safe_last(ta_a.trend.sma_indicator(close, window=5),  _safe_last(close))
    ma_10 = _safe_last(ta_a.trend.sma_indicator(close, window=10), _safe_last(close))
    ma_20 = _safe_last(ta_a.trend.sma_indicator(close, window=20), _safe_last(close))
    ma_50 = _safe_last(ta_a.trend.sma_indicator(close, window=50), ma_20)
    ma_200 = _safe_last(ta_a.trend.sma_indicator(close, window=200), ma_50)

    # RSI
    rsi_5  = _safe_last(ta_a.momentum.rsi(close, window=5),  50.0)
    rsi_10 = _safe_last(ta_a.momentum.rsi(close, window=10), 50.0)
    rsi_14 = _safe_last(ta_a.momentum.rsi(close, window=14), 50.0)

    # MACD (12/26/9)
    macd      = _safe_last(ta_a.trend.macd(close), 0.0)
    macd_signal = _safe_last(ta_a.trend.macd_signal(close), 0.0)
    macd_hist = _safe_last(ta_a.trend.macd_diff(close), 0.0)

    # Bollinger Bands
    bb = ta_a.volatility.BollingerBands(close, window=20, window_dev=2)
    bb_upper  = _safe_last(bb.bollinger_hband(), _safe_last(close))
    bb_middle = _safe_last(bb.bollinger_mavg(),  _safe_last(close))
    bb_lower  = _safe_last(bb.bollinger_lband(), _safe_last(close))

    # KD Stochastic (9 days, 真實計算)
    kd_k, kd_d = _calculate_kd_real(high, low, close)

    # 成交量均線
    vol_5  = _safe_last(volume.rolling(5).mean(),  0.0)
    vol_10 = _safe_last(volume.rolling(10).mean(), 0.0)

    return TechnicalIndicators(
        ma_5=ma_5,
        ma_10=ma_10,
        ma_20=ma_20,
        ma_50=ma_50,
        ma_200=ma_200,
        rsi_5=rsi_5,
        rsi_10=rsi_10,
        rsi_14=rsi_14,
        macd=macd,
        macd_signal=macd_signal,
        macd_hist=macd_hist,
        kd_k=kd_k,
        kd_d=kd_d,
        bollinger_upper=bb_upper,
        bollinger_middle=bb_middle,
        bollinger_lower=bb_lower,
        vol_5=vol_5,
        vol_10=vol_10,
    )


def _calculate_kd(close: Any, high: Any, low: Any) -> tuple[float, float]:
    """Legacy stub — kept for compatibility."""
    return (50.0, 50.0)


def _calculate_kd_real(
    high: pd.Series, low: pd.Series, close: pd.Series, window: int = 9
) -> tuple[float, float]:
    """KD Stochastic 真實計算 (window=9, smooth=3)"""
    try:
        ta_a = cast(Any, ta)
        stoch = ta_a.momentum.StochasticOscillator(
            high=high, low=low, close=close,
            window=window, smooth_window=3,
        )
        k = _safe_last(stoch.stoch(), 50.0)
        d = _safe_last(stoch.stoch_signal(), 50.0)
        return k, d
    except Exception as e:
        logger.warning(f"KD calculation failed, falling back to 50/50: {e}")
        return (50.0, 50.0)


def _build_trend(indicators: TechnicalIndicators, current_price: float) -> str:
    if current_price > indicators.ma_200 and indicators.ma_50 > indicators.ma_200:
        return "uptrend"
    if current_price < indicators.ma_200 and indicators.ma_50 < indicators.ma_200:
        return "downtrend"
    return "sideways"


def _build_signal(indicators: TechnicalIndicators) -> str:
    rsi = indicators.rsi_14
    if rsi <= 25:
        return "strong_buy"
    if rsi < 30:
        return "buy"
    if rsi >= 75:
        return "strong_sell"
    if rsi > 70:
        return "sell"
    return "hold"


def _build_summary(indicators: TechnicalIndicators, signal: str) -> str:
    if signal in ("strong_buy", "buy"):
        return "RSI 偏低，可能超賣，觀察反彈訊號。"
    if signal in ("strong_sell", "sell"):
        return "RSI 偏高，可能過熱，留意回檔風險。"
    return "技術指標中性，建議觀望。"


def _recommendation_to_signal(reco: str) -> str:
    if "買" in reco:
        return "buy"
    if "賣" in reco:
        return "sell"
    return "hold"


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
            market_cap=info.get('marketCap'),
            industry=info.get('industry', ""),
        )
    except Exception as e:
        logger.warning(f"Could not fetch fundamental data for {symbol}: {e}")
        return FundamentalData()


async def _fetch_stock_name(symbol: str) -> str:
    """從 TWSE 拿股票名稱"""
    try:
        # TODO: 呼叫 TWSE 公司名稱查詢
        return symbol
    except Exception:
        return symbol


async def _generate_chart(
    symbol: str,
    df: pd.DataFrame,
    indicators: TechnicalIndicators
) -> Optional[bytes]:
    """生成 K 線圖（委派給 S1b chart_tools，暫時回傳 None）"""
    try:
        # TODO: S1b 實作
        # 暫時回傳 None，讓 chart_bytes 為 None
        return None
    except Exception as e:
        logger.error(f"Chart generation failed: {e}")
        return None


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


def stock_screen(criteria: dict | None = None) -> list[StockReport]:
    """
    Screen Taiwan 50 stocks based on technical criteria.
    """
    # Taiwan 50 symbols (real TWSE codes)
    taiwan_50 = [
        "2330", "2498", "1101", "3034", "2412", "1216", "2409", "2891",
        "2454", "2881", "2882", "1108", "1302", "3008", "1326", "2886",
        "2801", "2379", "2884", "2885", "2383", "4904", "1324", "2889",
        "4938", "2454", "2352", "1229", "2357", "2330", "2388", "3045",
        "2356", "2355", "3017", "4904", "3231", "1303", "2382", "1216",
        "6505", "2395", "2353", "1101", "2340", "1605", "3008", "2365",
        "2886", "1590", "2891"
    ]
    # 去重
    taiwan_50 = list(set(taiwan_50))[:50]

    reports: list[StockReport] = []
    for symbol in taiwan_50:
        try:
            fetch_result = stock_fetch_data_sync(symbol, period="3mo")
            report = stock_analyze_report(symbol, fetch_result.get("ohlcv", []))
            report.name = fetch_result.get("name", report.name)
            report.current_price = fetch_result.get("current", report.current_price)
            report.previous_close = fetch_result.get("previous_close", report.previous_close)
            report.day_high = fetch_result.get("high", report.day_high)
            report.day_low = fetch_result.get("low", report.day_low)
            report.volume = fetch_result.get("volume", report.volume)
            report.timestamp = fetch_result.get("timestamp", report.timestamp)
            reports.append(report)
        except Exception:  # nosec B112
            # 忽略單一股票的拉取失敗
            continue

    # 應用篩選條件
    if criteria is None:
        criteria = {
            'rsi_min': 30,
            'rsi_max': 70,
            'volume_threshold': 10000000,
            'signal': ['buy', 'strong_buy']
        }

    filtered = []
    for report in reports:
        if criteria.get('rsi_min') is not None and report.indicators.rsi < criteria['rsi_min']:
            continue
        if criteria.get('rsi_max') is not None and report.indicators.rsi > criteria['rsi_max']:
            continue
        if criteria.get('volume_threshold') is not None and getattr(report, 'volume', 0) < criteria['volume_threshold']:
            continue
        if criteria.get('signal') is not None:
            allowed_signals = criteria['signal'] if isinstance(criteria['signal'], list) else [criteria['signal']]
            if getattr(report, 'signal', '') not in allowed_signals:
                continue
        filtered.append(report)

    # 依 signal 強度排序
    signal_rank = {'strong_buy': 5, 'buy': 4, 'hold': 3, 'sell': 2, 'strong_sell': 1}
    filtered.sort(key=lambda r: signal_rank.get(getattr(r, 'signal', ''), 0), reverse=True)

    return filtered[:15]  # 返回前 15 個


def stock_chip(symbol: str) -> dict:
    """
    Query institutional chip analysis (法人/融資/融券).

    Tries TWSE OpenAPI first; falls back to neutral mock on failure.
    Now supports looking back up to 7 days for the latest data.
    """
    # Normalize symbol (strip .TW or .TWO)
    orig_symbol = symbol
    symbol = symbol.split(".")[0].upper()

    base = {
        "symbol": orig_symbol,
        "date": datetime.now().strftime("%Y-%m-%d"),
        # 外資
        "foreign_buy": 0, "foreign_sell": 0, "net_foreign": 0,
        "foreign_holding_pct": None,
        # 投信
        "trust_buy": 0, "trust_sell": 0, "net_trust": 0,
        "trust_holding_pct": None,
        # 融資
        "margin_buy": 0, "margin_sell": 0, "margin_balance": 0,
        # 融券
        "short_buy": 0, "short_sell": 0, "short_balance": 0,
        "chip_signal": "neutral",
        "source": "mock",
    }

    try:
        import httpx as _httpx
        # http2=False: TWSE server incompatible with HTTP/2 from Python TLS stack
        _client = _httpx.Client(http2=False, timeout=12, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
        # Find latest available trading day (look back up to 7 days)
        found_chip = False
        is_otc = ".TWO" in orig_symbol.upper()

        for i in range(7):
            dt = datetime.now() - timedelta(days=i)
            query_date = dt.strftime("%Y%m%d")

            # --- Try TWSE (Listed) first unless explicitly .TWO ---
            if not is_otc:
                url_3f = f"https://www.twse.com.tw/fund/T86?response=json&date={query_date}&selectType=ALL"
                resp = _client.get(url_3f)
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("stat") == "OK":
                        rows = data.get("data", [])
                        for row in rows:
                            if len(row) > 0 and str(row[0]).strip() == symbol:
                                try:
                                    def _int(v): return int(str(v).replace(",", "").strip() or "0")
                                    # T86 values are in 股 (shares); divide by 1000 → 張
                                    base["foreign_buy"]  = _int(row[2]) // 1000
                                    base["foreign_sell"] = _int(row[3]) // 1000
                                    base["net_foreign"]  = _int(row[4]) // 1000
                                    base["trust_buy"]    = _int(row[8]) // 1000
                                    base["trust_sell"]   = _int(row[9]) // 1000
                                    base["net_trust"]    = _int(row[10]) // 1000
                                    base["date"] = f"{query_date[:4]}-{query_date[4:6]}-{query_date[6:8]}"
                                    base["source"] = "twse_3f"
                                    found_chip = True
                                except Exception: pass
                                break
                        if found_chip: break

            # --- Try TPEX (OTC) ---
            # TPEX uses Minguo date format: YYY/MM/DD
            yyy = dt.year - 1911
            minguo_date = f"{yyy}/{dt.strftime('%m/%s')}".replace("/0", "/").replace("//", "/").replace("/ ", "/")
            # Better format logic:
            minguo_date = f"{yyy}/{dt.month:02d}/{dt.day:02d}"
            url_otc = f"https://www.tpex.org.tw/web/stock/3insti/daily_trade/3itrade_hedge_result.php?l=zh-tw&o=json&se=EW&t=D&d={minguo_date}"
            resp = _client.get(url_otc)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("iTotalRecords", 0) > 0:
                    rows = data.get("aaData", [])
                    for row in rows:
                        if len(row) > 0 and str(row[0]).strip() == symbol:
                            try:
                                def _int(v): return int(str(v).replace(",", "").strip() or "0")
                                # TPEX: Code(0), Name(1), Foreign Net(10), Trust Net(11)... indices differ
                                # Actually check TPEX T86 header for indices:
                                # Foreign Buy(2), Foreign Sell(3), Foreign Net(4)
                                # Trust Buy(5), Trust Sell(6), Trust Net(7)
                                base["foreign_buy"]  = _int(row[2])
                                base["foreign_sell"] = _int(row[3])
                                base["net_foreign"]  = _int(row[4])
                                base["trust_buy"]    = _int(row[5])
                                base["trust_sell"]   = _int(row[6])
                                base["net_trust"]    = _int(row[7])
                                base["date"] = f"{dt.year}-{dt.month:02d}-{dt.day:02d}"
                                base["source"] = "tpex_3f"
                                found_chip = True
                            except Exception: pass
                            break
                    if found_chip: break

        # --- 融資融券 (僅 Listed) ---
        if found_chip and base["source"] == "twse_3f":
            query_date = base["date"].replace("-", "")
            url_mg = f"https://www.twse.com.tw/exchangeReport/MI_MARGN?response=json&date={query_date}&selectType=ALL"
            resp = _client.get(url_mg)
            if resp.status_code == 200:
                data = resp.json()
                rows = data.get("data", [])
                for row in rows:
                    if len(row) > 0 and str(row[0]).strip() == symbol:
                        try:
                            def _int(v): return int(str(v).replace(",", "").strip() or "0")
                            base["margin_buy"]     = _int(row[2])
                            base["margin_sell"]    = _int(row[3])
                            base["margin_balance"] = _int(row[4])
                            base["short_buy"]      = _int(row[5])
                            base["short_sell"]     = _int(row[6])
                            base["short_balance"]  = _int(row[7])
                            base["source"] = base.get("source", "") + "+twse_margin"
                        except Exception: pass
                        break

    except Exception as e:
        logger.warning(f"[stock_chip] chip fetch failed for {symbol}: {e}")

    # 訊號判斷
    net = base["net_foreign"] + base["net_trust"]
    if net > 500:
        base["chip_signal"] = "positive"
    elif net < -500:
        base["chip_signal"] = "negative"

    return base


def _extract_text_from_html(html: str) -> str:
    import re as _re
    cleaned = _re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", html)
    cleaned = _re.sub(r"(?is)<noscript.*?>.*?</noscript>", " ", cleaned)
    cleaned = _re.sub(r"(?is)<.*?>", " ", cleaned)
    cleaned = _re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def _summarize_text(text: str, fallback: str = "", max_len: int = 240) -> str:
    base = (text or "").strip()
    if not base and fallback:
        base = fallback.strip()
    if len(base) <= max_len:
        return base
    return base[:max_len].rsplit(" ", 1)[0] + "..."


def _fetch_article_text(url: str, timeout: int = 10) -> str:
    if not url:
        return ""
    try:
        import httpx
    except Exception:
        return ""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
        }
        with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as client:
            resp = client.get(url)
        if resp.status_code != 200:
            return ""
        text = resp.text
        if len(text) > 20000:
            text = text[:20000]
        if "<html" in text.lower():
            return _extract_text_from_html(text)
        return text.strip()
    except Exception:
        return ""


def stock_news(symbol: str, limit: int = 5) -> list[dict]:
    """
    Fetch recent news for a stock symbol.

    Args:
        symbol: Stock code (e.g., "2330") or company name
        limit: Maximum number of news articles to fetch (default 5)

    Returns:
        List of news dicts
    """
    try:
        from claw.tools.search import search_web_impl
        from datetime import datetime

        # For Taiwan 4-6 digit stock codes, use Chinese query for relevant results
        import re as _re
        if _re.match(r'^\d{4,6}$', symbol):
            query = f"{symbol} 台股 新聞"
        else:
            query = f"{symbol} stock news"
        search_results = search_web_impl(query, max_results=limit * 2)

        news_list: list[dict] = []
        seen_urls: set[str] = set()

        for result in search_results:
            raw_url = (result.get("href") or result.get("url") or "").strip()
            if not raw_url or raw_url in seen_urls:
                continue
            seen_urls.add(raw_url)

            # Extract domain as source when no explicit source field
            try:
                from urllib.parse import urlparse
                domain = urlparse(raw_url).netloc.replace("www.", "") if raw_url else "Web"
            except Exception:
                domain = "Web"

            snippet = result.get("body", result.get("summary", "")) or ""
            content_text = _fetch_article_text(raw_url)
            summary_text = _summarize_text(content_text, fallback=snippet, max_len=240)

            news_item = {
                "title": result.get("title", ""),
                "url": raw_url,
                "source": result.get("source", domain),
                "publish_date": result.get("date", datetime.now().strftime("%Y-%m-%d")),
                "summary": summary_text,
                "content": content_text[:2000] if content_text else "",
                "sentiment": "neutral",
            }
            if news_item["title"]:  # skip empty results
                news_list.append(news_item)
            if len(news_list) >= limit:
                break

        return news_list

    except Exception as e:
        logger.warning(f"Failed to fetch news for {symbol}: {e}")
        return []


def sentiment_analyze(news_list: list) -> dict:
    """
    Analyze sentiment of a list of news articles.

    Args:
        news_list: List of news dicts (from stock_news())

    Returns:
        dict with sentiment analysis
    """
    if not news_list:
        return {
            "overall_sentiment": "neutral",
            "positive_count": 0,
            "neutral_count": 0,
            "negative_count": 0,
            "sentiment_score": 0.0,
            "summary": "無新聞數據",
            "advice": "新聞不足，維持觀望",
        }

    # 簡化實作：使用關鍵詞匹配（標題+摘要+內容）
    positive_keywords = [
        '上升', '成長', '利好', '看好', '漲', '買入', '強勢', '獲利', '上修', '創高', '突破',
        '增持', '優於預期', '回升', '復甦'
    ]
    negative_keywords = [
        '下跌', '衰退', '利空', '看壞', '跌', '賣出', '弱勢', '虧損', '下修', '跌破',
        '減持', '不如預期', '放緩', '衰退'
    ]

    sentiment_counts = {'positive': 0, 'neutral': 0, 'negative': 0}
    total_pos = 0
    total_neg = 0

    for news in news_list:
        text = " ".join([
            news.get('title', ''),
            news.get('summary', ''),
            news.get('content', ''),
        ]).lower()

        pos_hits = sum(1 for kw in positive_keywords if kw in text)
        neg_hits = sum(1 for kw in negative_keywords if kw in text)
        total_pos += pos_hits
        total_neg += neg_hits

        if pos_hits > neg_hits:
            sentiment = 'positive'
        elif neg_hits > pos_hits:
            sentiment = 'negative'
        else:
            sentiment = 'neutral'

        sentiment_counts[sentiment] += 1
        news['sentiment'] = sentiment
        news['sentiment_score'] = pos_hits - neg_hits

    total = len(news_list)
    positive_ratio = sentiment_counts['positive'] / total
    negative_ratio = sentiment_counts['negative'] / total

    if positive_ratio > 0.5:
        overall = 'positive'
    elif negative_ratio > 0.5:
        overall = 'negative'
    else:
        overall = 'neutral'

    denom = max(total_pos + total_neg, 1)
    sentiment_score = (total_pos - total_neg) / denom

    if overall == 'positive':
        summary = f"輿論整體偏向正面，{sentiment_counts['positive']} 則正面新聞"
        advice = "新聞面偏多，注意追價風險"
    elif overall == 'negative':
        summary = f"輿論整體偏向負面，{sentiment_counts['negative']} 則負面新聞"
        advice = "新聞面偏空，留意下行風險"
    else:
        summary = "輿論整體中立，市場信號不明確"
        advice = "新聞面中性，等待更多催化"

    return {
        "overall_sentiment": overall,
        "positive_count": sentiment_counts['positive'],
        "neutral_count": sentiment_counts['neutral'],
        "negative_count": sentiment_counts['negative'],
        "sentiment_score": round(sentiment_score, 2),
        "summary": summary,
        "advice": advice,
    }
