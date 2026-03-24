"""Discord response classifier — maps user query + LLM response to a ResponseType."""
from __future__ import annotations

import re
from enum import Enum


class ResponseType(Enum):
    STOCK          = "stock"
    SCREEN         = "screen"
    WEATHER        = "weather"
    REPORT         = "report"
    EVENT          = "event"
    PORTFOLIO      = "portfolio"
    MORNING_REPORT = "morning_report"
    WEEKLY_REPORT  = "weekly_report"
    GENERAL        = "general"


# ─── Keyword patterns ─────────────────────────────────────────────────────────

_STOCK_PATTERNS = [
    re.compile(r'(?<!\d)\d{4}(?!\d)'),           # 4-digit stock code
    re.compile(r'台積電|聯發科|鴻海|中鋼|台泥|大立光|聯電|台塑'),
    re.compile(r'股票|股價|K線|技術分析|本益比|外資|投信|籌碼'),
    re.compile(r'\.TW\b', re.IGNORECASE),
]

_SCREEN_PATTERNS = [
    re.compile(r'推薦.*標的|標的.*推薦'),
    re.compile(r'選股|強勢股|今日最強|熱門股|潛力股'),
    re.compile(r'值得買|可以買|哪幾檔|幾檔.*推薦|推薦.*幾檔'),
    re.compile(r'推薦.*買|買.*推薦|現在.*適合|適合.*買'),
    re.compile(r'推薦.*[0-9]+.*檔|推薦.*[五五個幾]+.*股|台股.*推薦|推薦.*台股'),
    re.compile(r'幫.*推薦|給.*推薦|推薦.*給我'),
    re.compile(r'five.?stocks?|top.?stocks?|best.?stocks?', re.IGNORECASE),
]

_WEATHER_PATTERNS = [
    re.compile(r'天氣|氣溫|溫度|降雨|濕度|颱風|風速|紫外線'),
    re.compile(r'weather|forecast|temperature|rain|humidity', re.IGNORECASE),
    re.compile(r'今天|明天|後天|這週|下週.*天氣'),
]

_WEEKLY_REPORT_PATTERNS = [
    re.compile(r'週報|周報|本週報告|這週報告|週策略|本週策略'),
    re.compile(r'weekly.?report|week.?report', re.IGNORECASE),
    re.compile(r'這週|本週|上週.*表現|本週.*強勢|本週.*推薦'),
]

_MORNING_REPORT_PATTERNS = [
    re.compile(r'日報|晨報|早報|早安報|股市日報|股價日報'),
    re.compile(r'morning.?report|daily.?report', re.IGNORECASE),
    re.compile(r'今天的報告|今日報告|今天報告|今天的股市|今日股市'),
]

_REPORT_PATTERNS = [
    re.compile(r'報告|分析|研究|市場|產業|趨勢|比較|排名|統計'),
    re.compile(r'report|analysis|research|market|industry|trend', re.IGNORECASE),
    re.compile(r'成長率|市佔率|占比|份額'),
]

_EVENT_PATTERNS = [
    re.compile(r'活動|行程|日程|會議|提醒|行事曆|排程|預約|預定'),
    re.compile(r'event|calendar|schedule|meeting|reminder|appointment', re.IGNORECASE),
    re.compile(r'幾點|幾號|星期|禮拜|下午|上午|早上'),
]

_PORTFOLIO_PATTERNS = [
    re.compile(r'持倉|庫存|我的股票|我持有|我買了|加倉|減倉|成本價|平均成本|損益|賺了|虧了'),
    re.compile(r'portfolio|holding|position|cost.?basis|p&l|pnl', re.IGNORECASE),
    re.compile(r'\d+張.*成本|\d+股.*成本|成本.*\d+元|買.*\d+張'),
    re.compile(r'新增持倉|刪除持倉|更新持倉|我的倉位'),
]

_PATTERNS: dict[ResponseType, list[re.Pattern]] = {
    ResponseType.STOCK:          _STOCK_PATTERNS,
    ResponseType.SCREEN:         _SCREEN_PATTERNS,
    ResponseType.WEATHER:        _WEATHER_PATTERNS,
    ResponseType.MORNING_REPORT: _MORNING_REPORT_PATTERNS,
    ResponseType.WEEKLY_REPORT:  _WEEKLY_REPORT_PATTERNS,
    ResponseType.REPORT:         _REPORT_PATTERNS,
    ResponseType.EVENT:          _EVENT_PATTERNS,
    ResponseType.PORTFOLIO:      _PORTFOLIO_PATTERNS,
}


# ─── Classifier ───────────────────────────────────────────────────────────────

class DiscordFormatter:
    """
    Classifies (user_query, llm_response) into a ResponseType.

    Strategy:
    1. Fast keyword matching on the query string (O(n) regex)
    2. If ambiguous, check llm_response for hints
    3. Default to GENERAL
    """

    def classify(
        self,
        query: str,
        llm_response: str = "",
    ) -> tuple[ResponseType, dict]:
        """
        Returns:
            (ResponseType, context_dict)

        context_dict keys:
            query           original user query
            llm_response    LLM text response
            stock_code      str | None  (only for STOCK)
        """
        combined = query + " " + llm_response

        # Score each type
        scores: dict[ResponseType, int] = {t: 0 for t in ResponseType}
        for rtype, patterns in _PATTERNS.items():
            for pat in patterns:
                if pat.search(combined):
                    scores[rtype] += 1

        # Pick highest score (ignoring GENERAL which has no patterns)
        best_type = ResponseType.GENERAL
        best_score = 0
        for rtype, score in scores.items():
            if rtype == ResponseType.GENERAL:
                continue
            if score > best_score:
                best_score = score
                best_type = rtype

        # Tie-break: MORNING_REPORT beats STOCK when both score (日報 is more specific than 股價)
        if (best_type == ResponseType.STOCK
                and scores.get(ResponseType.MORNING_REPORT, 0) >= scores.get(ResponseType.STOCK, 0) > 0):
            best_type = ResponseType.MORNING_REPORT

        # Build context
        context: dict = {"query": query, "llm_response": llm_response}
        if best_type == ResponseType.STOCK:
            context["stock_code"] = self._extract_stock_code(query)

        return best_type, context

    @staticmethod
    def _extract_stock_code(text: str) -> str | None:
        """Extract first 4-digit stock code from text."""
        m = re.search(r'(?<!\d)(\d{4})(?!\d)', text)
        if m:
            return m.group(1)
        # Name mapping fallback
        _name_map = {
            "台積電": "2330", "聯發科": "2454", "鴻海": "2317",
            "中鋼": "2002", "台泥": "1101", "大立光": "3008",
            "聯電": "2303", "台塑": "1301",
        }
        for name, code in _name_map.items():
            if name in text:
                return code
        return None
