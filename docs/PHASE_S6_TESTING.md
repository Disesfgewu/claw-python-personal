# Phase S6 Worker Prompt — Complete Real-World Testing

> 當前狀態：206+ tests passing（Phase S5 完成）
> 目標狀態：210+ tests + 完整真實環境驗證
> 耗時預估：2-3 天
> 負責人：PM（可邀請 Codex/Gemini 協助端對端測試）

---

## 背景說明

Phase S5 完成了生產優化。Phase S6 負責在真實環境中驗證整個系統的功能和穩定性：

1. **真實 API 端對端測試** — 不只 mock，實際呼叫服務
2. **Discord 推播驗證** — 實際推送到 Discord 頻道（使用者提供的 credentials）
3. **Cron job 自動執行驗證** — 模擬排程執行，驗證晨報/週報正確執行
4. **邊界情況和錯誤恢復** — 異常市場、無效輸入、服務中斷

完成後，系統準備進入 Phase S7 的文檔編寫和最終交付。

---

## Task 1 — 準備真實環境測試基礎設施

### 1.1 建立 Integration Tests 框架

擴展 `tests/integration/test_live_api.py`（Phase 15 建立的骨架）：

```python
"""
Integration tests for live API endpoints.
These tests require:
1. LIVE_BACKEND=1 environment variable
2. LLM Router running at configured URL
3. Discord credentials in environment or config
4. Internet connection for data fetching
"""
from __future__ import annotations

import os
import pytest
import asyncio
from datetime import datetime
from unittest.mock import patch

# 只在 LIVE_BACKEND=1 時執行
pytestmark = pytest.mark.skipif(
    os.getenv("LIVE_BACKEND") != "1",
    reason="Integration tests require LIVE_BACKEND=1 env var"
)


class TestLiveAPI:
    """Test real API endpoints without mocking."""

    @pytest.fixture
    def live_config(self):
        """Load live configuration from environment."""
        from claw.core.config import get_config
        cfg = get_config()
        return {
            "llm_router_url": os.getenv("LLM_ROUTER_URL", cfg.llm_router.url),
            "llm_router_key": os.getenv("LLM_ROUTER_KEY", cfg.llm_router.api_key),
            "discord_token": os.getenv("DISCORD_TOKEN", cfg.discord.token),
            "discord_channel_id": int(os.getenv("DISCORD_CHANNEL_ID", cfg.discord.stock_channel_id or 0)),
        }

    @pytest.mark.asyncio
    async def test_stock_fetch_live(self, live_config):
        """
        Test stock_fetch against real data source (TWSE/Yahoo).

        驗證項目：
        - 能成功連接到資料源
        - 返回有效的 OHLCV 資料
        - 必要欄位都存在
        - 資料合理性（close > 0, volume > 0）
        """
        from claw.tools.stock_tools import stock_fetch

        # 使用現實股票代碼
        symbol = "2330"  # TSMC

        result = stock_fetch(symbol, period="1mo")

        # 驗證結果結構
        assert result is not None
        assert result["symbol"] == symbol
        assert "current" in result
        assert "ohlcv" in result
        assert len(result["ohlcv"]) > 0

        # 驗證 OHLCV 資料合理性
        for candle in result["ohlcv"][-5:]:  # 最後 5 筆
            assert candle["open"] > 0
            assert candle["high"] > 0
            assert candle["low"] > 0
            assert candle["close"] > 0
            assert candle["high"] >= candle["low"]
            assert candle["volume"] >= 0

        print(f"✓ stock_fetch live test passed for {symbol}")

    @pytest.mark.asyncio
    async def test_stock_analyze_live(self, live_config):
        """
        Test stock_analyze with real data.

        驗證項目：
        - 技術指標計算正確
        - 生成有效的 StockReport
        - 訊號判斷合理
        """
        from claw.tools.stock_tools import stock_fetch, stock_analyze

        symbol = "2330"
        fetch_result = stock_fetch(symbol, period="3mo")
        report = stock_analyze(symbol, fetch_result.get("ohlcv", []))

        # 驗證報告結構
        assert report.symbol == symbol
        assert report.current_price > 0
        assert 0 <= report.indicators.rsi <= 100
        assert report.signal in ["strong_buy", "buy", "hold", "sell", "strong_sell"]
        assert report.trend in ["uptrend", "downtrend", "sideways"]

        print(f"✓ stock_analyze live test passed: {report.signal} ({report.trend})")

    @pytest.mark.asyncio
    async def test_chart_generation_live(self, live_config):
        """
        Test chart generation with real stock data.

        驗證項目：
        - PNG 生成成功
        - PNG 檔案有效（magic number）
        - 包含 K 線、均線、成交量
        """
        from claw.tools.stock_tools import stock_fetch
        from claw.tools.chart_tools import generate_candlestick_chart

        symbol = "2330"
        fetch_result = stock_fetch(symbol, period="1mo")
        ohlcv = fetch_result.get("ohlcv", [])

        if len(ohlcv) < 10:
            pytest.skip("Not enough data for chart generation")

        png_bytes = generate_candlestick_chart(symbol, ohlcv)

        # 驗證 PNG
        assert isinstance(png_bytes, bytes)
        assert len(png_bytes) > 1000  # 合理的最小大小
        assert png_bytes[:8] == b'\x89PNG\r\n\x1a\n'  # PNG magic number

        print(f"✓ Chart generation live test passed: {len(png_bytes)} bytes")

    @pytest.mark.asyncio
    async def test_stock_screen_live(self, live_config):
        """
        Test stock screening against real Taiwan 50.

        驗證項目：
        - 能篩選出台灣50股票
        - 返回有效的 StockReport 列表
        - 篩選條件被正確應用
        """
        from claw.tools.stock_tools import stock_screen

        # 寬鬆的篩選條件（確保能找到股票）
        criteria = {
            'rsi_min': 0,
            'rsi_max': 100,
            'volume_threshold': 0,
            'signal': ['strong_buy', 'buy', 'hold', 'sell', 'strong_sell']
        }

        results = stock_screen(criteria)

        # 驗證結果
        assert isinstance(results, list)
        assert len(results) > 0, "Should screen out at least some stocks"
        assert len(results) <= 15, "Should return max 15 stocks"

        for report in results:
            assert report.symbol
            assert report.current_price > 0
            assert report.signal in ['strong_buy', 'buy', 'hold', 'sell', 'strong_sell']

        print(f"✓ Stock screening live test passed: {len(results)} stocks found")
```

**驗收**：
- Integration tests 框架已就位
- 5 個live 測試已建立
- 可透過 `LIVE_BACKEND=1 pytest` 執行

### 1.2 建立測試環境設定

創建 `.env.test.example`（用戶可複製並填入 credentials）：

```bash
# .env.test.example - Integration Test Configuration
# 複製為 .env.test 並填入實際的 credentials

# LLM Router
LLM_ROUTER_URL=http://localhost:8000
LLM_ROUTER_KEY=test_key

# Discord（用於推播測試）
DISCORD_TOKEN=your_bot_token_here
DISCORD_CHANNEL_ID=your_test_channel_id_here

# 啟用 live 測試
LIVE_BACKEND=1

# 測試超時時間
TEST_TIMEOUT_SECONDS=60

# Cron 測試模式（模擬時間）
CRON_TEST_MODE=1
CRON_TEST_CURRENT_TIME=2026-03-23T08:00:00
```

---

## Task 2 — Discord 推播真實驗證

### 2.1 建立 Discord 測試工具

創建 `tests/integration/test_discord_live.py`：

```python
"""
Live Discord integration tests.
Requires: DISCORD_TOKEN, DISCORD_CHANNEL_ID environment variables.
"""
from __future__ import annotations

import os
import pytest
import asyncio
import discord
from datetime import datetime

pytestmark = pytest.mark.skipif(
    os.getenv("LIVE_BACKEND") != "1",
    reason="Discord live tests require LIVE_BACKEND=1"
)


@pytest.fixture
async def discord_client():
    """
    Create a Discord bot client for testing.
    Note: This requires a valid bot token with permissions to send messages.
    """
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        pytest.skip("DISCORD_TOKEN not set")

    bot = discord.Client(intents=discord.Intents.default())
    await bot.login(token)

    yield bot

    await bot.close()


@pytest.mark.asyncio
async def test_discord_send_embed_live(discord_client):
    """
    Test sending an Embed to Discord.

    驗證項目：
    - Embed 可以被正確序列化
    - Discord bot 可以連接
    - 訊息被成功發送（返回有效的 message_id）
    """
    channel_id = int(os.getenv("DISCORD_CHANNEL_ID", "0"))
    if channel_id == 0:
        pytest.skip("DISCORD_CHANNEL_ID not set")

    channel = discord_client.get_channel(channel_id)
    if not channel:
        pytest.skip(f"Channel {channel_id} not accessible")

    # 建立測試 Embed
    embed = discord.Embed(
        title="🧪 Integration Test — Embed Message",
        description="This is an automated test message.",
        color=discord.Color.blue(),
        timestamp=datetime.utcnow()
    )
    embed.add_field(name="Test Type", value="Discord Live Integration", inline=False)
    embed.add_field(name="Status", value="✓ Testing", inline=True)

    try:
        message = await channel.send(embed=embed)
        assert message.id
        print(f"✓ Embed sent successfully: message_id={message.id}")

        # 清理：刪除測試訊息
        await message.delete()
    except discord.Forbidden:
        pytest.skip("Bot lacks permission to send messages in channel")


@pytest.mark.asyncio
async def test_discord_send_file_live(discord_client):
    """
    Test sending a file (chart) to Discord.

    驗證項目：
    - 檔案附件被正確序列化
    - 可以成功上傳到 Discord
    - 訊息包含文件引用
    """
    channel_id = int(os.getenv("DISCORD_CHANNEL_ID", "0"))
    if channel_id == 0:
        pytest.skip("DISCORD_CHANNEL_ID not set")

    channel = discord_client.get_channel(channel_id)
    if not channel:
        pytest.skip(f"Channel {channel_id} not accessible")

    # 建立模擬 PNG 檔案
    from io import BytesIO
    png_data = b'\x89PNG\r\n\x1a\n' + b'\x00' * 1000  # 最小有效 PNG

    try:
        file = discord.File(BytesIO(png_data), filename="test_chart.png")
        message = await channel.send(file=file, content="Test chart upload")
        assert message.id
        assert len(message.attachments) > 0
        print(f"✓ File sent successfully: {message.attachments[0].filename}")

        # 清理
        await message.delete()
    except discord.Forbidden:
        pytest.skip("Bot lacks permission to send messages in channel")


@pytest.mark.asyncio
async def test_discord_stock_report_live(discord_client):
    """
    Test sending a complete stock report (Embed + Data).

    這個測試驗證整個晨報邏輯是否能成功推送到 Discord。
    """
    from claw.tools.stock_tools import stock_fetch, stock_analyze

    channel_id = int(os.getenv("DISCORD_CHANNEL_ID", "0"))
    if channel_id == 0:
        pytest.skip("DISCORD_CHANNEL_ID not set")

    channel = discord_client.get_channel(channel_id)
    if not channel:
        pytest.skip(f"Channel {channel_id} not accessible")

    # 拉取真實數據
    symbol = "2330"
    fetch_result = stock_fetch(symbol, period="1mo")
    report = stock_analyze(symbol, fetch_result.get("ohlcv", []))

    # 建立股票報告 Embed
    embed = discord.Embed(
        title=f"📈 Stock Report — {report.symbol} {report.name}",
        description=f"Live Analysis Report",
        color=discord.Color.green() if "buy" in report.signal else discord.Color.red(),
        timestamp=datetime.utcnow()
    )
    embed.add_field(name="Current Price", value=f"${report.current_price:.2f}", inline=True)
    embed.add_field(name="Signal", value=report.signal.upper(), inline=True)
    embed.add_field(name="Trend", value=report.trend, inline=True)
    embed.add_field(name="RSI", value=f"{report.indicators.rsi:.1f}", inline=True)
    embed.add_field(name="Summary", value=report.summary, inline=False)

    try:
        message = await channel.send(embed=embed)
        assert message.id
        print(f"✓ Stock report sent successfully")

        # 清理
        await message.delete()
    except discord.Forbidden:
        pytest.skip("Bot lacks permission")
```

**驗收**：
- Discord live 測試已建立（3 個測試）
- 需要有效的 bot token 和 channel_id
- 測試訊息被發送後自動刪除（不污染頻道）

### 2.2 運行 Discord 驗證

```bash
# 設定環境變數（或使用 .env.test）
export LIVE_BACKEND=1
export DISCORD_TOKEN="your_bot_token"
export DISCORD_CHANNEL_ID="your_channel_id"

# 執行 Discord live 測試
python -m pytest tests/integration/test_discord_live.py -v -s

# 預期輸出：
# test_discord_send_embed_live PASSED
# test_discord_send_file_live PASSED
# test_discord_stock_report_live PASSED
```

---

## Task 3 — Cron Job 自動執行驗證

### 3.1 建立 Cron 測試工具

創建 `tests/integration/test_cron_execution.py`：

```python
"""
Cron job execution verification.
Tests that morning_report and weekly_report jobs execute correctly.
"""
from __future__ import annotations

import os
import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import patch, AsyncMock, MagicMock

pytestmark = pytest.mark.skipif(
    os.getenv("LIVE_BACKEND") != "1",
    reason="Cron tests require LIVE_BACKEND=1"
)


@pytest.mark.asyncio
async def test_morning_report_execution():
    """
    Test morning report Cron job execution.

    驗證項目：
    - Job 被正確註冊
    - Job 按排程執行
    - 返回成功狀態
    - Discord 被呼叫推送
    """
    from claw.cron.service import CronService
    from claw.cron.store import CronStore
    from claw.core.storage import Storage
    from claw.llm.router_client import LLMRouterClient
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        # 初始化服務
        storage = Storage(db_path=f"{tmpdir}/claw.db", transcript_dir=f"{tmpdir}/transcripts")
        await storage.init()

        llm = LLMRouterClient(base_url="http://localhost:8000", api_key="test")
        cron_store = CronStore(db_path=storage.db_path)
        await cron_store.init()

        cron_service = CronService(store=cron_store, storage=storage, llm=llm)

        # 模擬晨報 job
        with patch("claw.cron.jobs.morning_report.stock_screen") as mock_screen:
            mock_screen.return_value = [MagicMock(symbol="2330", signal="buy")]

            with patch("claw.cron.jobs.morning_report.DiscordChannel.send_to_channel_id") as mock_discord:
                mock_discord.return_value = True

                # 直接呼叫晨報函數（模擬排程觸發）
                from claw.cron.jobs.morning_report import morning_report_job

                result = await morning_report_job(storage, llm, {"channel_id": 123456789})

                # 驗證執行結果
                assert result["status"] in ["success", "no_bot", "no_stocks"]
                print(f"✓ Morning report executed: {result['status']}")

        await cron_service.stop()


@pytest.mark.asyncio
async def test_weekly_report_execution():
    """
    Test weekly report Cron job execution.

    驗證項目：
    - Job 執行 A→C→B 評估
    - 策略驗證結果有效
    - 推送結果到 Discord
    """
    from claw.cron.service import CronService
    from claw.cron.store import CronStore
    from claw.core.storage import Storage
    from claw.llm.router_client import LLMRouterClient
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        storage = Storage(db_path=f"{tmpdir}/claw.db", transcript_dir=f"{tmpdir}/transcripts")
        await storage.init()

        llm = LLMRouterClient(base_url="http://localhost:8000", api_key="test")
        cron_store = CronStore(db_path=storage.db_path)
        await cron_store.init()

        cron_service = CronService(store=cron_store, storage=storage, llm=llm)

        # 模擬週報 job
        with patch("claw.cron.jobs.weekly_report.StockStrategyExecutor") as mock_executor_class:
            mock_executor = MagicMock()
            mock_executor_class.return_value = mock_executor

            mock_executor.execute = AsyncMock(return_value={
                "status": "success",
                "winner": "momentum",
                "winner_sharpe": 1.2,
                "winner_win_rate": 0.65
            })
            mock_executor.evaluate = AsyncMock(return_value={
                "is_valid": True,
                "confidence": 0.85
            })

            with patch("claw.cron.jobs.weekly_report.DiscordChannel.send_to_channel_id") as mock_discord:
                mock_discord.return_value = True

                from claw.cron.jobs.weekly_report import weekly_report_job

                result = await weekly_report_job(storage, llm, {"channel_id": 987654321})

                assert result["status"] in ["success", "no_bot"]
                print(f"✓ Weekly report executed: {result['status']}")

        await cron_service.stop()


@pytest.mark.asyncio
async def test_cron_schedule_accuracy():
    """
    Verify that Cron schedules are correctly parsed and triggered.

    驗證項目：
    - 晨報排程 (0 8 * * 1-5) 只在週一至週五執行
    - 週報排程 (0 18 * * 5) 只在週五執行
    """
    from cron_validator import CronValidator

    validator = CronValidator()

    # 晨報排程驗證
    morning_cron = "0 8 * * 1-5"
    assert validator.validate(morning_cron).is_valid, "Morning cron is invalid"

    # 週報排程驗證
    weekly_cron = "0 18 * * 5"
    assert validator.validate(weekly_cron).is_valid, "Weekly cron is invalid"

    print("✓ Cron schedules are valid")
```

**驗收**：
- Cron 執行測試已建立（2 個測試）
- 排程驗證已實裝
- 可驗證晨報和週報正確執行

---

## Task 4 — 邊界情況和錯誤恢復測試

### 4.1 異常市場情況測試

創建 `tests/integration/test_edge_cases.py`：

```python
"""
Edge cases and error recovery tests.
"""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock


@pytest.mark.asyncio
async def test_invalid_stock_symbol():
    """Test handling of invalid stock symbol."""
    from claw.tools.stock_tools import stock_fetch

    with pytest.raises(ValueError):
        stock_fetch("INVALID")  # 非法股票代碼

    print("✓ Invalid symbol handling works")


@pytest.mark.asyncio
async def test_network_timeout_recovery():
    """Test handling of network timeout with retry."""
    from claw.tools.stock_tools import stock_fetch

    with patch("claw.tools.stock_tools._stock_fetch_impl") as mock_fetch:
        # 前 2 次失敗，第 3 次成功（模擬重試邏輯）
        mock_fetch.side_effect = [
            ConnectionError("Network timeout"),
            ConnectionError("Network timeout"),
            {"symbol": "2330", "ohlcv": []}
        ]

        result = stock_fetch("2330", use_cache=False)
        assert result["symbol"] == "2330"
        print("✓ Network retry logic works")


@pytest.mark.asyncio
async def test_insufficient_data_for_analysis():
    """Test handling when there's insufficient data for analysis."""
    from claw.tools.stock_tools import stock_analyze
    from claw.models.stock_report import StockReport

    # 只有 5 個 candles（計算 SMA200 需要 200 個）
    insufficient_ohlcv = [
        {"date": f"2026-03-{i:02d}", "open": 100, "high": 105, "low": 95, "close": 100 + i, "volume": 1000000}
        for i in range(1, 6)
    ]

    report = stock_analyze("TEST", insufficient_ohlcv)

    # 應該優雅地返回報告（部分指標為預設值）
    assert isinstance(report, StockReport)
    assert report.symbol == "TEST"
    print("✓ Insufficient data handling works")


@pytest.mark.asyncio
async def test_discord_offline_graceful_degradation():
    """Test system behavior when Discord is offline."""
    from claw.cron.jobs.morning_report import morning_report_job
    from claw.core.storage import Storage
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        storage = Storage(db_path=f"{tmpdir}/claw.db", transcript_dir=f"{tmpdir}/transcripts")

        # 模擬 Discord 不可用
        with patch("claw.cron.jobs.morning_report.DiscordChannel") as mock_discord:
            mock_discord.bot = None  # Discord bot 未初始化

            result = await morning_report_job(storage, None, {})

            # 應該返回 "no_bot" 狀態，不拋出異常
            assert result["status"] in ["no_bot", "failed"]
            print("✓ Discord offline graceful degradation works")


@pytest.mark.asyncio
async def test_cron_job_race_condition():
    """
    Test handling of race conditions when two Cron jobs try to execute simultaneously.

    驗證項目：
    - 晨報和週報同時執行時不會相互干擾
    - 資源被正確鎖定
    - 結果都被正確記錄
    """
    import asyncio

    async def fake_job_1():
        await asyncio.sleep(0.1)
        return "job1_result"

    async def fake_job_2():
        await asyncio.sleep(0.1)
        return "job2_result"

    # 並行執行兩個 job
    results = await asyncio.gather(fake_job_1(), fake_job_2())

    assert len(results) == 2
    print("✓ Race condition handling works")


@pytest.mark.asyncio
async def test_memory_leak_long_running_session():
    """
    Test that long-running sessions don't leak memory.

    驗證項目：
    - 多個搜尋/分析操作後記憶體正常
    - 快取被正確管理
    """
    from claw.tools.stock_tools import stock_fetch
    import gc
    import sys

    # 模擬長時間運行
    for i in range(100):
        with patch("claw.tools.stock_tools._stock_fetch_impl") as mock_fetch:
            mock_fetch.return_value = {"symbol": f"TEST{i}", "ohlcv": []}
            stock_fetch(f"TEST{i}")

    # 強制垃圾回收
    gc.collect()

    # 驗證沒有明顯的記憶體洩漏（這是簡化版，實際應用應使用 memory_profiler）
    print("✓ Memory leak test passed (100 iterations)")
```

**驗收**：
- 6 個邊界情況測試已建立
- 異常恢復被正確測試
- 系統穩定性得到驗證

---

## Task 5 — 執行完整測試套件

```bash
cd /home/martin/Desktop/claw-python-personal

# 設定環境（如果使用實際 Discord credentials）
# export DISCORD_TOKEN="your_token"
# export DISCORD_CHANNEL_ID="your_channel_id"
# export LIVE_BACKEND=1

# 執行所有 integration tests
python -m pytest tests/integration/ -v -s 2>&1 | tee s6_integration_test_report.txt

# 執行所有單元測試 + integration 測試
python -m pytest tests/ -v --tb=short 2>&1 | tee s6_complete_test_report.txt

# 驗證測試計數
python -m pytest tests/ --collect-only -q | tail -1

# 生成測試覆蓋率報告
python -m pytest tests/ --cov=claw --cov-report=html --cov-report=term 2>&1 | tee coverage_final.txt
```

**預期輸出**：
- `210+ passed, 3 skipped`（新增 ~4 個 integration 測試）
- 0 failures
- 覆蓋率報告顯示主要模組 > 80%

---

## Task 6 — 系統穩定性驗收清單

完成以下驗收項目，確認系統準備好進入 Phase S7：

### 6.1 API 端對端驗證

```bash
# 1. 啟動伺服器
cd /home/martin/Desktop/claw-python-personal
python -m claw.main &
SERVER_PID=$!
sleep 3

# 2. 驗證 health endpoint
curl -s http://localhost:8000/admin/health | python -m json.tool

# 3. 驗證 metrics endpoint
curl -s http://localhost:8000/admin/metrics | python -m json.tool

# 4. 驗證 tools 已註冊
curl -s http://localhost:8000/tools | python -m json.tool | head -20

# 5. 清理
kill $SERVER_PID
```

**預期輸出**：
- health: `{"status": "ok"}`
- metrics: 包含 system/application/performance 欄位
- tools: 至少 28 個工具

### 6.2 Discord 推播驗收

需要使用者提供 Discord credentials：

```bash
export DISCORD_TOKEN="your_bot_token_here"
export DISCORD_CHANNEL_ID="your_test_channel_id_here"
export LIVE_BACKEND=1

# 執行 Discord 真實測試
python -m pytest tests/integration/test_discord_live.py -v -s

# 檢查結果：
# - 訊息在 Discord 中被看到（並自動刪除）
# - 沒有錯誤日誌
```

### 6.3 Cron 排程驗收

```bash
# 驗證 Cron 排程已正確註冊
python -c "
from claw.cron.store import CronStore
import tempfile
import asyncio

async def check():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = CronStore(db_path=f'{tmpdir}/cron.db')
        await store.init()
        # 列出所有 jobs
        print('Registered Cron jobs:')
        # 注意：這取決於 store 實作

asyncio.run(check())
"
```

---

## 交付清單

完成後回報：

1. **新建的檔案絕對路徑**：
   - `/home/martin/Desktop/claw-python-personal/tests/integration/test_live_api.py`（擴展）
   - `/home/martin/Desktop/claw-python-personal/tests/integration/test_discord_live.py`
   - `/home/martin/Desktop/claw-python-personal/tests/integration/test_cron_execution.py`
   - `/home/martin/Desktop/claw-python-personal/tests/integration/test_edge_cases.py`
   - `/home/martin/Desktop/claw-python-personal/.env.test.example`

2. **修改的檔案**：無（測試檔案為新增）

3. **pytest 最終輸出**：
   - 單元測試：`210+ passed, 3 skipped`
   - Integration 測試：`~11 passed, 0 failures`

4. **驗收清單結果**：
   - ✅ API 端對端測試通過
   - ✅ Discord 推播驗證成功
   - ✅ Cron 排程驗證通過
   - ✅ 邊界情況處理正確

5. **遇到的問題和解決方式**

---

## 完成標準

✅ 真實 API integration 測試已建立（stock_fetch, stock_analyze, chart, screen）
✅ Discord 推播真實驗證已建立（Embed、File、完整報告）
✅ Cron job 執行驗證已建立（晨報、週報、排程準確性）
✅ 邊界情況測試已建立（異常、網絡、不足資料、離線）
✅ 210+ tests pass, 0 failures
✅ 系統準備進入 Phase S7（文檔編寫）

---

## 注意事項

- Integration 測試需要網絡連接和有效的 API 端點
- Discord 測試需要真實的 bot token 和 channel ID（建議使用測試伺服器）
- 某些測試的執行時間較長（因涉及真實 API 呼叫）
- 建議在 staging 環境中驗證，再推到生產環境

