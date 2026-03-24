# Phase S1B Worker Prompt — Chart Tools + Taiwan Stock Skill

> 發給：**Gemini**
> 當前狀態：182 tests passing（Phase S1a 完成）
> 目標狀態：184+ tests + K 線圖生成 + Taiwan Stock Skill
> 耗時預估：2 小時
> 依賴：Phase S1a 必須先完成（stock_tools 已就位）

---

## 背景說明

Phase S1b 與 S1a 並行執行。在 S1a 完成股票資料拉取和技術分析後，S1b 負責視覺化層面：

1. **chart_tools.py** — 生成 K 線圖（PNG）供 Discord Embed 附檔使用
2. **Taiwan Stock Skill** — 供使用者透過 Chat 快速執行股票分析

這兩部分獨立於 S1a，但在最終整合時（S2a-S4）會與 stock_tools 一起使用。

---

## Task 1 — 建立 `claw/tools/chart_tools.py`

新建圖表生成工具，使用 `mplfinance` 產生 K 線圖。

**檔案位置**：`claw/tools/chart_tools.py`

**核心函數：generate_candlestick_chart(symbol: str, ohlcv_list: list, output_path: str = None) → bytes**

```python
def generate_candlestick_chart(
    symbol: str,
    ohlcv_list: list,
    output_path: str = None
) -> bytes:
    """
    Generate candlestick chart as PNG bytes.

    Args:
        symbol: Stock code (e.g., "2330")
        ohlcv_list: List of OHLCV dicts with keys:
            - 'date' (str, YYYY-MM-DD format)
            - 'open', 'high', 'low', 'close' (float)
            - 'volume' (int)
        output_path: If provided, save PNG to this path

    Returns:
        PNG binary data as bytes

    圖表特性：
    - K 線（綠色上升，紅色下降）
    - 20-day + 50-day 移動平均線
    - 成交量柱狀圖（下方）
    - 標題："{symbol} Candlestick Chart"
    - 自動 locale 設定為繁體中文
    """
    import pandas as pd
    import mplfinance as mpf
    from io import BytesIO

    # 轉換成 pandas DataFrame（日期為 index）
    df = pd.DataFrame(ohlcv_list)
    df['date'] = pd.to_datetime(df['date'])
    df.set_index('date', inplace=True)
    df = df[['open', 'high', 'low', 'close', 'volume']]

    # 計算移動平均線
    df['sma20'] = df['close'].rolling(20).mean()
    df['sma50'] = df['close'].rolling(50).mean()

    # 組建 mplfinance 樣式
    apds = [
        mpf.make_addplot(df['sma20'], color='orange', width=1.5),
        mpf.make_addplot(df['sma50'], color='purple', width=1.5),
    ]

    # 生成圖表到 BytesIO
    buffer = BytesIO()
    mpf.plot(
        df,
        type='candle',
        style='charles',
        title=f'{symbol} Candlestick Chart',
        ylabel='Price (TWD)',
        volume=True,
        addplot=apds,
        savefig=dict(fname=buffer, dpi=100, bbox_inches='tight'),
    )
    buffer.seek(0)
    png_bytes = buffer.getvalue()

    # 如果指定 output_path，也存一份到檔案
    if output_path:
        with open(output_path, 'wb') as f:
            f.write(png_bytes)

    return png_bytes
```

**驗收**：
- 函數能成功 import
- 給定模擬的 ohlcv_list 能生成 PNG 位元組
- PNG 檔案可被顯示（有 PNG magic number）

---

## Task 2 — 註冊 generate_candlestick_chart 為 Tool

修改 `claw/tools/__init__.py`，加入新工具註冊。

**在 `claw/tools/__init__.py` 末尾加入**：

```python
from claw.tools.chart_tools import generate_candlestick_chart
import base64

@register_tool()
def generate_chart_tool(symbol: str, period: str = "3mo") -> str:
    """Generate K-line candlestick chart for stock analysis."""
    try:
        from claw.tools.stock_tools import stock_fetch
        fetch_result = stock_fetch(symbol, period)
        png_bytes = generate_candlestick_chart(symbol, fetch_result.get("ohlcv", []))
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
```

**驗收**：
- `generate_chart_tool` 能被 import
- Tools registry 能找到該工具

---

## Task 3 — 建立 Taiwan Stock Skill — `skills/taiwan-stock/SKILL.md`

建立 Skill 定義檔，供使用者透過自然語言調用股票分析功能。

**目錄結構**：
```
skills/taiwan-stock/
├── SKILL.md
└── __init__.py  (可為空)
```

**檔案位置**：`skills/taiwan-stock/SKILL.md`

**內容**：

```yaml
---
name: taiwan-stock
display: "台股分析"
description: "Real-time analysis of Taiwan stocks (TWSE symbols)"
author: "Claw AI"
version: "1.0"
---

# 台股分析技能

用於分析台灣股市個股，提供技術面、基本面、圖表三合一服務。

## 觸發方式

用戶可以使用以下自然語言觸發此技能：
- "分析台積電"
- "查詢 2330 股價"
- "給我台灣50強勢股的圖表"
- "分析鴻海（2498）的技術面"

## 系統流程

1. **識別股票代碼** — 從使用者輸入提取股票代碼（例如 2330、2498）或公司名稱
2. **拉取資料** — 調用 `stock_fetch` 工具
3. **技術分析** — 調用 `stock_analyze` 工具
4. **生成圖表** — 調用 `generate_chart` 工具
5. **整合報告** — 組合上述結果成 Discord Embed 或純文字回應

## 可用工具

- `stock_fetch_tool` — 拉取 OHLCV 資料
- `stock_analyze_tool` — 計算技術指標
- `generate_chart_tool` — 生成 K 線圖

## 使用範例

### 範例 1：基本股價查詢
```
用戶：分析台積電
系統：調用 stock_fetch("2330") → stock_analyze("2330") → 返回技術分析報告
```

### 範例 2：帶圖表的完整分析
```
用戶：我想看台積電的 3 個月走勢圖
系統：
  1. stock_fetch("2330", "3mo")
  2. stock_analyze("2330", ohlcv)
  3. generate_chart_tool("2330", "3mo")
  4. 組合成 Discord Embed（圖表作為附檔）
```

## 支援的股票代碼範圍

- **台灣上市公司**：任何在 TWSE 上市的股票（例如 2330, 2498, 1101, 3034 等）
- **資料源優先級**：TWSE → Yahoo Finance

## 預期輸出

```json
{
  "symbol": "2330",
  "name": "台積電",
  "current_price": 600.0,
  "change_percent": 1.5,
  "technical_summary": "RSI 過高，賣壓增加",
  "chart_url": "<base64 PNG>"
}
```

## 技術限制

- 只支援中文台灣股票代碼（4 碼數字）
- 數據延遲可能 15-30 分鐘（取決於資料源）
- 圖表預設顯示最近 3 個月走勢

## 後續整合點

- **Phase S2a**：篩選功能（stock_screen） → 找出台灣50強勢股
- **Phase S3**：新聞追蹤 (stock_news) → 加入新聞事件標記
- **Phase S4**：策略回測 (backtest) → 驗證分析的準確度
```

**驗收**：
- 檔案存在於 `skills/taiwan-stock/SKILL.md`
- YAML 格式正確
- 內容清晰描述技能的功能和使用方式

---

## Task 4 — 建立單元測試 `tests/test_chart_tools.py`

建立 1 個測試，驗證圖表生成。

**檔案位置**：`tests/test_chart_tools.py`

**測試內容**：

```python
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
```

**驗收**：
- 測試能成功執行
- 測試通過（生成有效的 PNG）

---

## Task 5 — 驗證 Skill 載入

確保 taiwan-stock Skill 能被系統正確載入。

```bash
python -c "
from claw.skills.loader import load_skills
skills = load_skills('skills/')
taiwan_skill = [s for s in skills if 'taiwan' in s.lower()]
print(f'Taiwan stock skill found: {len(taiwan_skill) > 0}')
print('✅ Taiwan stock skill loaded')
"
```

**預期輸出**：台灣股票技能被成功載入

---

## Task 6 — 執行測試

```bash
cd /home/martin/Desktop/claw-python-personal

# 執行圖表工具測試
python -m pytest tests/test_chart_tools.py -v

# 執行全部測試
python -m pytest tests/ -q --tb=short
```

**預期輸出**：
- `test_generate_candlestick_chart` PASSED
- 整體 `184 passed, 3 skipped`（新增 1 個測試）

---

## Task 7 — 驗證圖表工具註冊

```bash
python -c "
from claw.tools.registry import get_tools
tools = get_tools()
chart_tools = [t for t in tools if 'chart' in t.lower() or 'generate' in t.lower()]
print(f'Chart tools found: {len(chart_tools)}')
for t in chart_tools:
    print(f'  - {t}')
assert len(chart_tools) >= 1, 'Should have at least 1 chart tool'
print('✅ Chart tools registered correctly')
"
```

**預期輸出**：至少 1 個 chart/generate 工具被註冊

---

## 交付清單

完成後回報：

1. **新建的檔案絕對路徑**：
   - `/home/martin/Desktop/claw-python-personal/claw/tools/chart_tools.py`
   - `/home/martin/Desktop/claw-python-personal/skills/taiwan-stock/SKILL.md`
   - `/home/martin/Desktop/claw-python-personal/tests/test_chart_tools.py`

2. **修改的檔案絕對路徑**：
   - `/home/martin/Desktop/claw-python-personal/claw/tools/__init__.py`

3. **pytest 最終輸出**（應為 184+ passed）

4. **工具和 Skill 驗證結果**

5. **遇到的問題和解決方式**

---

## 完成標準

✅ generate_candlestick_chart() 能生成有效的 PNG（包含 K 線、均線、成交量）
✅ 圖表工具已註冊到 registry
✅ Taiwan Stock Skill 已建立並可被載入
✅ 184+ tests pass, 0 failures
✅ 1 個單元測試通過

---

## 注意事項

- Skill 檔案應該放在 `skills/taiwan-stock/` 目錄中（不是 docs）
- 圖表應包含至少 K 線、20/50-day 均線和成交量
- PNG 生成應該支援錯誤處理（資料不足時優雅降級）
- 不要改動既有的 tools（只新增）
- 可根據需要調整圖表美觀度（顏色、字體、大小）

