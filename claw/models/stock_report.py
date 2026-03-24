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
    bollinger_upper: float = 0.0
    bollinger_middle: float = 0.0
    bollinger_lower: float = 0.0
    # 短期均線
    ma_5: float = 0.0
    ma_10: float = 0.0
    # 短期 RSI
    rsi_5: float = 0.0
    rsi_10: float = 0.0
    # 成交量均線
    vol_5: float = 0.0
    vol_10: float = 0.0

    # --- Compatibility aliases (S1A) ---
    @property
    def rsi(self) -> float:
        return self.rsi_14

    @property
    def sma_20(self) -> float:
        return self.ma_20

    @property
    def sma_50(self) -> float:
        return self.ma_50

    @property
    def sma_200(self) -> float:
        return self.ma_200

    @property
    def macd_histogram(self) -> float:
        return self.macd_hist

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
    def macd_signal_str(self) -> str:
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
    market_cap: Optional[float] = None
    industry: str = ""
    news_sentiment: str = "neutral"  # 新增：新聞情緒

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

    # S1A compatibility fields
    previous_close: float = 0.0
    day_high: float = 0.0
    day_low: float = 0.0
    volume: int = 0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    trend: str = ""
    signal: str = ""
    summary: str = ""

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

    # --- Compatibility alias ---
    @property
    def fundamentals(self) -> FundamentalData:
        return self.fundamental

    @fundamentals.setter
    def fundamentals(self, value: FundamentalData) -> None:
        self.fundamental = value

    def to_embed_description(self) -> str:
        """轉成 Discord Embed 描述"""
        return f"""
**{self.symbol} {self.name}**
現價: ${self.current_price:,.2f} {self.change_pct:+.2f}%

**技術面**
MA: {self.indicators.ma_signal}
RSI: {self.indicators.rsi_signal} ({self.indicators.rsi_14:.1f})
MACD: {self.indicators.macd_signal_str}

**基本面**
PE比: {self.fundamental.pe_ratio or 'N/A'}
ROE: {self.fundamental.roe or 'N/A'}%
評分: {self.fundamental.fundamental_score}/100

**建議**: {self.recommendation} (信心: {self.confidence*100:.0f}%)
"""
