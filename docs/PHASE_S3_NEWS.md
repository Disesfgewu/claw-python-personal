# Phase S3 Worker Prompt — News Fetching + Sentiment Analysis

> 發給：**Gemini**
> 當前狀態：187 tests passing（Phase S2 完成）
> 目標狀態：189+ tests + 新聞追蹤 + 情緒分析
> 耗時預估：2-3 小時
> 依賴：Phase S1a (stock_tools) 必須先完成

---

## 背景說明

Phase S3 擴展股票分析系統，加入新聞面的信息。目前的系統只有技術面和籌碼面，缺乏對市場新聞和情緒的追蹤。

S3 的任務是實現兩個功能：
1. **stock_news(symbol: str, limit: int = 5) → list[dict]** — 搜尋個股相關新聞
2. **sentiment_analyze(news_list: list) → dict** — 分析新聞整體情緒（正面/中立/負面）

新聞信息將被整合到 StockReport 中，供晨報和分析報告使用。

---

## Task 1 — 擴展 `claw/tools/stock_tools.py`

在既有的 stock_tools.py 中加入 stock_news 函數。

**函數：stock_news(symbol: str, limit: int = 5) → list[dict]**

```python
def stock_news(symbol: str, limit: int = 5) -> list[dict]:
    """
    Fetch recent news for a stock symbol.

    Args:
        symbol: Stock code (e.g., "2330") or company name
        limit: Maximum number of news articles to fetch (default 5)

    Returns:
        List of news dicts:
        [
            {
                "title": "台積電宣布新廠投資計畫",
                "url": "https://example.com/news/123",
                "source": "經濟日報",
                "publish_date": "2026-03-22",
                "summary": "台積電今日宣布...",
                "sentiment": "positive"  # positive / neutral / negative
            },
            ...
        ]

    實作邏輯：
    1. 使用 search_web tool（DDGS via LLM-Router MCP）搜尋
       查詢："{symbol} 股票" 或 "{company_name}" + 時間範圍（近 7 天）
    2. 對每個搜尋結果提取：title, url, 發布日期
    3. 呼叫 web_fetch 拉取摘要（如果可行）
    4. 對每則新聞進行初步情緒判斷（基於標題和摘要中的關鍵詞）
    5. 返回前 N 則新聞
    """
    try:
        from claw.tools.search import search_web_impl
        from datetime import datetime, timedelta

        # 搜尋查詢
        query = f"{symbol} stock news"
        # 使用 DDGS 搜尋
        search_results = search_web_impl(query, max_results=limit * 2)

        news_list = []
        for result in search_results[:limit]:
            # 簡化實作：直接使用搜尋結果
            news_item = {
                "title": result.get("title", ""),
                "url": result.get("url", ""),
                "source": result.get("source", "Web"),
                "publish_date": result.get("date", datetime.now().strftime("%Y-%m-%d")),
                "summary": result.get("body", "")[:200],  # 摘要前 200 字
                "sentiment": "neutral"  # 稍後由 sentiment_analyze 填充
            }
            news_list.append(news_item)

        return news_list

    except Exception as e:
        logger.warning(f"Failed to fetch news for {symbol}: {e}")
        return []
```

**驗收**：
- 函數能 import
- 返回新聞列表（即使為空）
- 沒有語法錯誤

---

## Task 2 — 建立情緒分析函數

在 `claw/tools/stock_tools.py` 中加入 sentiment_analyze 函數。

**函數：sentiment_analyze(news_list: list) → dict**

```python
def sentiment_analyze(news_list: list) -> dict:
    """
    Analyze sentiment of a list of news articles.

    Args:
        news_list: List of news dicts (from stock_news())

    Returns:
        {
            "overall_sentiment": "positive",  # positive / neutral / negative
            "positive_count": 2,
            "neutral_count": 2,
            "negative_count": 1,
            "sentiment_score": 0.4,  # -1 (most negative) to +1 (most positive)
            "summary": "輿論整體偏向正面，買盤信心充足"
        }

    實作邏輯：
    1. 對每則新聞的 title + summary 進行情緒分類
    2. 使用關鍵詞匹配或 LLM 調用進行分類
    3. 計算正負中三種情緒的比例
    4. 生成整體情緒評分和摘要
    """
    if not news_list:
        return {
            "overall_sentiment": "neutral",
            "positive_count": 0,
            "neutral_count": 0,
            "negative_count": 0,
            "sentiment_score": 0.0,
            "summary": "無新聞數據"
        }

    # 簡化實作：使用關鍵詞匹配
    positive_keywords = ['上升', '成長', '利好', '看好', '漲', '買入', '超漲', '強勢', '獲利']
    negative_keywords = ['下跌', '衰退', '利空', '看壞', '跌', '賣出', '超跌', '弱勢', '虧損']

    sentiment_counts = {'positive': 0, 'neutral': 0, 'negative': 0}

    for news in news_list:
        title_lower = (news.get('title', '') + ' ' + news.get('summary', '')).lower()

        # 檢查關鍵詞
        positive_score = sum(1 for kw in positive_keywords if kw in title_lower)
        negative_score = sum(1 for kw in negative_keywords if kw in title_lower)

        if positive_score > negative_score:
            sentiment = 'positive'
        elif negative_score > positive_score:
            sentiment = 'negative'
        else:
            sentiment = 'neutral'

        sentiment_counts[sentiment] += 1
        news['sentiment'] = sentiment

    # 計算整體情緒
    total = len(news_list)
    positive_ratio = sentiment_counts['positive'] / total
    negative_ratio = sentiment_counts['negative'] / total
    neutral_ratio = sentiment_counts['neutral'] / total

    # 決定整體情緒
    if positive_ratio > 0.5:
        overall = 'positive'
    elif negative_ratio > 0.5:
        overall = 'negative'
    else:
        overall = 'neutral'

    # 計算情緒分數（-1 到 +1）
    sentiment_score = positive_ratio - negative_ratio

    # 生成摘要
    if overall == 'positive':
        summary = f"輿論整體偏向正面，{sentiment_counts['positive']} 則正面新聞，買盤信心充足"
    elif overall == 'negative':
        summary = f"輿論整體偏向負面，{sentiment_counts['negative']} 則負面新聞，市場信心不足"
    else:
        summary = "輿論整體中立，市場信號不明確"

    return {
        "overall_sentiment": overall,
        "positive_count": sentiment_counts['positive'],
        "neutral_count": sentiment_counts['neutral'],
        "negative_count": sentiment_counts['negative'],
        "sentiment_score": round(sentiment_score, 2),
        "summary": summary
    }
```

**驗收**：
- 函數能 import
- 返回包含 overall_sentiment 的字典
- 沒有語法錯誤

---

## Task 3 — 擴展 stock_analyze 整合新聞

修改 `claw/tools/stock_tools.py` 中的 `stock_analyze()` 函數，整合新聞信息。

**在 stock_analyze() 末尾加入**：

```python
    # ... (現有技術指標計算邏輯)

    # 新增：新聞追蹤
    try:
        news_list = stock_news(symbol, limit=3)
        news_sentiment = sentiment_analyze(news_list)
        report.fundamentals.news_sentiment = news_sentiment['overall_sentiment']
        # 在 summary 中加入新聞評論
        if news_list:
            report.summary += f" | 新聞情緒: {news_sentiment['summary']}"
    except Exception as e:
        logger.warning(f"Failed to fetch news for {symbol}: {e}")

    return report
```

**同時修改 FundamentalData dataclass**，在 `claw/models/stock_report.py` 中加入：

```python
@dataclass
class FundamentalData:
    """Fundamental company data."""
    pe_ratio: Optional[float] = None
    pb_ratio: Optional[float] = None
    dividend_yield: Optional[float] = None
    market_cap: Optional[float] = None
    industry: str = ""
    news_sentiment: str = "neutral"  # 新增：新聞情緒
```

**驗收**：
- stock_analyze() 能整合新聞信息
- FundamentalData 包含 news_sentiment 欄位
- 沒有語法錯誤

---

## Task 4 — 註冊工具到 Registry

修改 `claw/tools/__init__.py`，加入新聞相關工具註冊。

**在 `claw/tools/__init__.py` 末尾加入**：

```python
from claw.tools.stock_tools import stock_news, sentiment_analyze

@register_tool()
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
```

**驗收**：
- 執行 `python -c "from claw.tools import stock_news_tool; print('OK')"` 無誤

---

## Task 5 — 建立單元測試 `tests/test_stock_news.py`

建立 2 個測試，驗證新聞和情緒分析函數。

**檔案位置**：`tests/test_stock_news.py`

**測試內容**：

```python
"""Unit tests for stock news and sentiment analysis."""
import pytest
from unittest.mock import patch, MagicMock
from claw.tools.stock_tools import stock_news, sentiment_analyze


@pytest.mark.asyncio
async def test_stock_news_returns_list():
    """Test stock_news returns a list of news items."""
    with patch("claw.tools.stock_tools.search_web_impl") as mock_search:
        mock_search.return_value = [
            {
                "title": "台積電漲停",
                "url": "https://example.com/1",
                "source": "經濟日報",
                "date": "2026-03-22",
                "body": "台積電今日因重大利好消息上漲..."
            }
        ]

        news_list = stock_news("2330", limit=1)

        assert isinstance(news_list, list)
        if news_list:
            assert "title" in news_list[0]
            assert "url" in news_list[0]


@pytest.mark.asyncio
async def test_sentiment_analyze_classifies_correctly():
    """Test sentiment analysis correctly classifies news sentiment."""
    news_list = [
        {"title": "台積電上升成長利好", "summary": "強勢表現"},
        {"title": "股價下跌衰退利空", "summary": "弱勢表現"},
        {"title": "平穩表現", "summary": "中立新聞"}
    ]

    result = sentiment_analyze(news_list)

    assert "overall_sentiment" in result
    assert result["overall_sentiment"] in ["positive", "neutral", "negative"]
    assert result["positive_count"] >= 0
    assert result["negative_count"] >= 0
    assert result["neutral_count"] >= 0
    assert "summary" in result
```

**驗收**：
- 兩個測試能成功執行
- 測試通過

---

## Task 6 — 執行測試

```bash
cd /home/martin/Desktop/claw-python-personal

# 執行新聞測試
python -m pytest tests/test_stock_news.py -v

# 執行全部測試
python -m pytest tests/ -q --tb=short
```

**預期輸出**：
- `test_stock_news_returns_list` PASSED
- `test_sentiment_analyze_classifies_correctly` PASSED
- 整體 `189 passed, 3 skipped`（新增 2 個測試）

---

## Task 7 — 驗證工具註冊

```bash
python -c "
from claw.tools.registry import get_tools
tools = get_tools()
news_tools = [t for t in tools if 'news' in t.lower() or 'sentiment' in t.lower()]
print(f'News tools found: {len(news_tools)}')
for t in news_tools:
    print(f'  - {t}')
assert len(news_tools) >= 1, 'Should have at least 1 news tool'
print('✅ Stock news tools registered correctly')
"
```

**預期輸出**：至少 1 個 news 工具被註冊

---

## 交付清單

完成後回報：

1. **修改的檔案絕對路徑**：
   - `/home/martin/Desktop/claw-python-personal/claw/tools/stock_tools.py`
   - `/home/martin/Desktop/claw-python-personal/claw/tools/__init__.py`
   - `/home/martin/Desktop/claw-python-personal/claw/models/stock_report.py`

2. **新建的檔案絕對路徑**：
   - `/home/martin/Desktop/claw-python-personal/tests/test_stock_news.py`

3. **pytest 最終輸出**（應為 189+ passed）

4. **工具註冊驗證結果**（應為 1+ 新聞工具）

5. **遇到的問題和解決方式**

---

## 完成標準

✅ stock_news() 能搜尋個股相關新聞
✅ sentiment_analyze() 能分析新聞情緒（positive/neutral/negative）
✅ stock_analyze() 整合新聞信息到報告中
✅ 新聞工具已註冊到 registry
✅ 189+ tests pass, 0 failures
✅ 2 個單元測試通過

---

## 注意事項

- stock_news() 應優雅處理搜尋失敗（返回空列表，不拋異常）
- 情緒分析目前使用關鍵詞匹配，後續可升級為 LLM 調用
- news_sentiment 應被加到 StockReport 的分析摘要中
- 新聞搜尋可能涉及非中文網站，應優先篩選中文新聞
- 不要改動既有的 tools（只新增）

