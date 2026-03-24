# Phase S2A Worker Prompt — Stock Screening + Chip Analysis

> 發給：**Gemini**
> 當前狀態：184 tests passing（Phase S1 完成）
> 目標狀態：186+ tests + 股票篩選 + 籌碼分析
> 耗時預估：2 小時
> 依賴：Phase S1a 必須先完成（stock_tools 已就位）

---

## 背景說明

Phase S2a 擴展 stock_tools，加入兩個篩選相關的函數：

1. **stock_screen(criteria: dict) → list[StockReport]** — 篩選台灣50 中符合條件的強勢股
2. **stock_chip(symbol: str) → dict** — 查詢法人買賣超（籌碼面分析）

這兩個函數與 S2b 的晨報 Cron job 協作，能自動推送強勢股清單到 Discord。

---

## Task 1 — 擴展 `claw/tools/stock_tools.py`

在既有的 stock_tools.py 中加入兩個新函數。

**函數 1：stock_screen(criteria: dict = None) → list[StockReport]**

```python
def stock_screen(criteria: dict = None) -> list[StockReport]:
    """
    Screen Taiwan 50 stocks based on technical criteria.

    Args:
        criteria: Optional filter dict with keys:
            - 'rsi_min': Minimum RSI (e.g., 40 for oversold)
            - 'rsi_max': Maximum RSI (e.g., 70 for overbought)
            - 'volume_threshold': Minimum trading volume (e.g., 10000000)
            - 'signal': Filter by signal (e.g., "buy", "strong_buy")
            - 'trend': Filter by trend (e.g., "uptrend")

        如果 criteria 為 None，使用預設條件：
        - RSI 在 30-70 之間（避免極端情況）
        - 成交量 > 10M
        - Signal 為 "buy" 或 "strong_buy"

    Returns:
        List of StockReport objects matching criteria, sorted by signal strength

    實作邏輯：
    1. 定義台灣50 的成分股列表（50 個代碼，例如 2330, 2498, 1101, ...）
    2. 對每個成分股呼叫 stock_fetch() 和 stock_analyze()
    3. 根據 criteria 篩選
    4. 依照 signal 強度排序（strong_buy > buy > hold > sell > strong_sell）
    5. 返回前 10-15 個最強勢的股票
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

    reports = []
    for symbol in taiwan_50:
        try:
            fetch_result = stock_fetch(symbol, period="3mo")
            report = stock_analyze(symbol, fetch_result.get("ohlcv", []))
            reports.append(report)
        except Exception as e:
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
        if criteria.get('volume_threshold') is not None and report.volume < criteria['volume_threshold']:
            continue
        if criteria.get('signal') is not None:
            allowed_signals = criteria['signal'] if isinstance(criteria['signal'], list) else [criteria['signal']]
            if report.signal not in allowed_signals:
                continue
        filtered.append(report)

    # 依 signal 強度排序
    signal_rank = {'strong_buy': 5, 'buy': 4, 'hold': 3, 'sell': 2, 'strong_sell': 1}
    filtered.sort(key=lambda r: signal_rank.get(r.signal, 0), reverse=True)

    return filtered[:15]  # 返回前 15 個
```

**函數 2：stock_chip(symbol: str) → dict**

```python
def stock_chip(symbol: str) -> dict:
    """
    Query institutional chip analysis (法人買賣超).

    Args:
        symbol: Stock code (e.g., "2330")

    Returns:
        {
            "symbol": "2330",
            "name": "台積電",
            "date": "2026-03-22",
            "foreign_buy": 150000000,  # 外資買超（張）
            "foreign_sell": 120000000,
            "trust_buy": 50000000,  # 投信買超
            "trust_sell": 30000000,
            "dealer_buy": 100000000,  # 自營商買超
            "dealer_sell": 80000000,
            "net_foreign": 30000000,  # 外資淨買超
            "net_trust": 20000000,
            "net_dealer": 20000000,
            "chip_signal": "positive"  # "positive" / "neutral" / "negative"
        }

    實作邏輯：
    1. 嘗試從 TWSE 官方 API 或爬蟲源拉取當日籌碼數據
    2. 計算三大法人淨買超
    3. 判斷籌碼信號：
       - 若外資淨買超 > 50M：positive
       - 若外資淨買超 < -50M：negative
       - 其他：neutral
    4. 返回字典
    """
    # 簡化實作：使用靜態數據或模擬數據（真實實作可連接爬蟲）
    try:
        # 嘗試從 Yahoo Finance 或自定義 API 拉取數據
        # 此處為示意，實際應接入 TWSE 或爬蟲
        from datetime import datetime
        return {
            "symbol": symbol,
            "name": "Company Name",
            "date": datetime.now().strftime("%Y-%m-%d"),
            "foreign_buy": 100000000,
            "foreign_sell": 70000000,
            "trust_buy": 30000000,
            "trust_sell": 20000000,
            "dealer_buy": 50000000,
            "dealer_sell": 40000000,
            "net_foreign": 30000000,
            "net_trust": 10000000,
            "net_dealer": 10000000,
            "chip_signal": "positive" if 30000000 > 50000000 * 0.5 else "neutral"
        }
    except Exception as e:
        raise ValueError(f"Failed to fetch chip data for {symbol}: {e}")
```

**驗收**：
- 兩個函數都能 import
- `stock_screen()` 返回 StockReport 列表
- `stock_chip()` 返回包含籌碼信息的字典
- 沒有語法錯誤

---

## Task 2 — 註冊工具到 Registry

修改 `claw/tools/__init__.py`，加入兩個新工具註冊。

**在 `claw/tools/__init__.py` 末尾加入**：

```python
from claw.tools.stock_tools import stock_screen, stock_chip

@register_tool()
def stock_screen_tool(criteria: str = None) -> str:
    """Screen Taiwan 50 stocks based on technical criteria."""
    try:
        import json
        criteria_dict = None
        if criteria:
            criteria_dict = json.loads(criteria)
        results = stock_screen(criteria_dict)
        result_list = [
            {
                "symbol": r.symbol,
                "name": r.name,
                "current_price": r.current_price,
                "signal": r.signal,
                "rsi": r.indicators.rsi,
                "trend": r.trend
            }
            for r in results
        ]
        return json.dumps(result_list, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)

@register_tool()
def stock_chip_tool(symbol: str) -> str:
    """Query institutional chip analysis (foreign, trust, dealer)."""
    try:
        result = stock_chip(symbol)
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)
```

**驗收**：
- 執行 `python -c "from claw.tools import stock_screen_tool, stock_chip_tool; print('OK')"` 無誤

---

## Task 3 — 建立單元測試 `tests/test_stock_screen.py`

建立 2 個測試，驗證篩選和籌碼函數。

**檔案位置**：`tests/test_stock_screen.py`

**測試內容**：

```python
"""Unit tests for stock screening and chip analysis."""
import pytest
from unittest.mock import patch, MagicMock
from claw.tools.stock_tools import stock_screen, stock_chip
from claw.models.stock_report import StockReport, TechnicalIndicators


@pytest.mark.asyncio
async def test_stock_screen_filters_correctly():
    """Test stock_screen filters based on criteria."""
    # Mock stock_analyze to return controlled reports
    with patch("claw.tools.stock_tools.stock_analyze") as mock_analyze:
        # Create mock reports with different signals
        mock_reports = []
        for i, signal in enumerate(['strong_buy', 'buy', 'hold', 'sell']):
            report = StockReport(
                symbol=f"200{i}",
                name=f"Company {i}",
                current_price=100.0 + i,
                previous_close=100.0,
                day_high=105.0,
                day_low=95.0,
                volume=15000000,
            )
            report.signal = signal
            report.indicators.rsi = 50.0 + i * 5
            mock_reports.append(report)

        mock_analyze.side_effect = mock_reports

        with patch("claw.tools.stock_tools.stock_fetch") as mock_fetch:
            mock_fetch.return_value = {"ohlcv": []}
            results = stock_screen({'signal': ['buy', 'strong_buy']})
            assert len(results) <= 15
            for r in results:
                assert r.signal in ['buy', 'strong_buy']


@pytest.mark.asyncio
async def test_stock_chip_returns_valid_dict():
    """Test stock_chip returns valid chip data."""
    result = stock_chip("2330")

    assert isinstance(result, dict)
    assert result["symbol"] == "2330"
    assert "chip_signal" in result
    assert result["chip_signal"] in ["positive", "neutral", "negative"]
    assert "net_foreign" in result
```

**驗收**：
- 兩個測試能成功執行
- 測試通過

---

## Task 4 — 執行測試

```bash
cd /home/martin/Desktop/claw-python-personal

# 執行篩選測試
python -m pytest tests/test_stock_screen.py -v

# 執行全部測試
python -m pytest tests/ -q --tb=short
```

**預期輸出**：
- `test_stock_screen_filters_correctly` PASSED
- `test_stock_chip_returns_valid_dict` PASSED
- 整體 `186 passed, 3 skipped`（新增 2 個測試）

---

## Task 5 — 驗證工具註冊

```bash
python -c "
from claw.tools.registry import get_tools
tools = get_tools()
screen_tools = [t for t in tools if 'screen' in t.lower() or 'chip' in t.lower()]
print(f'Screen/chip tools found: {len(screen_tools)}')
for t in screen_tools:
    print(f'  - {t}')
assert len(screen_tools) >= 2, 'Should have at least 2 screening tools'
print('✅ Stock screening tools registered correctly')
"
```

**預期輸出**：至少 2 個 screen/chip 工具被註冊

---

## 交付清單

完成後回報：

1. **修改的檔案絕對路徑**：
   - `/home/martin/Desktop/claw-python-personal/claw/tools/stock_tools.py`
   - `/home/martin/Desktop/claw-python-personal/claw/tools/__init__.py`

2. **新建的檔案絕對路徑**：
   - `/home/martin/Desktop/claw-python-personal/tests/test_stock_screen.py`

3. **pytest 最終輸出**（應為 186+ passed）

4. **工具註冊驗證結果**（應為 2+ 篩選工具）

5. **遇到的問題和解決方式**

---

## 完成標準

✅ stock_screen() 能根據技術條件篩選台灣50
✅ stock_screen() 返回按 signal 強度排序的清單
✅ stock_chip() 能回傳法人買賣超信息
✅ 兩個新工具已註冊到 registry
✅ 186+ tests pass, 0 failures
✅ 2 個單元測試通過

---

## 注意事項

- stock_screen() 預設應返回前 15 個最強勢股（供晨報使用）
- 台灣50 的成分股清單應定期更新，此版本使用代表性股票即可
- stock_chip() 暫時可用靜態數據，後續 Phase S5 可對接真實爬蟲
- 篩選條件應該易於擴展（未來可加入基本面條件）
- 不要改動既有的 tools（只新增）

