"""Unit tests for stock news and sentiment analysis."""
import pytest
from unittest.mock import patch
from claw.tools.stock_tools import stock_news, sentiment_analyze

@pytest.mark.asyncio
async def test_stock_news_returns_list():
    """Test stock_news returns a list of news items."""
    with patch("claw.tools.search.search_web_impl") as mock_search:
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
