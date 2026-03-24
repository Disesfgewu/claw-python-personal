# Phase S5 Worker Prompt — Production Optimization

> 當前狀態：185 tests passing（Phase S0-S4 完成）
> 目標狀態：206+ tests + 生產級別優化完成
> 耗時預估：3-4 天
> 負責人：PM（可分配部分任務給 Codex/Gemini）

---

## 背景說明

Phase S0-S4 完成了台股分析系統的全功能實現。Phase S5 負責生產級別的優化和準備：

1. **性能優化** — 減少延遲、優化記憶體、加快查詢
2. **Bug 修復** — 修復已知問題
3. **Jetson 部署優化** — 針對 Jetson Orin Nano Super 的特定調整
4. **Monitoring 完整化** — 完整的性能指標和日誌記錄

完成後，系統準備進入 Phase S6 的真實環境測試。

---

## Task 1 — 性能優化：記憶體和快取

### 1.1 評估現狀

執行以下命令，取得系統當前性能基線：

```bash
cd /home/martin/Desktop/claw-python-personal

# 檢查 memory 搜尋效能
python -c "
import time
from claw.memory.manager import MemoryManager
from claw.llm.router_client import LLMRouterClient

async def test_memory_search():
    llm = LLMRouterClient(base_url='http://localhost:8000', api_key='test')
    from claw.memory.sqlite_store import MemoryStore
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        store = MemoryStore(db_path=f'{tmpdir}/memory.db')
        await store.init()
        mgr = MemoryManager(store=store, llm=llm)

        # 存儲 100 筆記憶
        for i in range(100):
            await mgr.save(f'test_key_{i}', f'This is test memory number {i}')

        # 測試搜尋速度
        start = time.time()
        results = await mgr.search('test', limit=5)
        elapsed = time.time() - start

        print(f'Memory search (100 items): {elapsed:.3f}s')
        print(f'Results returned: {len(results)}')

import asyncio
asyncio.run(test_memory_search())
"

# 檢查 Cron job 執行效能
python -c "
from claw.cron.service import CronService
from claw.cron.store import CronStore
import tempfile
import time

async def test_cron_perf():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = CronStore(db_path=f'{tmpdir}/cron.db')
        await store.init()
        service = CronService(store=store, storage=None, llm=None)

        # 添加 10 個 jobs
        start = time.time()
        for i in range(10):
            job_data = {
                'name': f'test_job_{i}',
                'schedule': '0 8 * * 1-5',
                'prompt': 'Test'
            }
            # 模擬添加（實際執行時取決於 store 實作）
        elapsed = time.time() - start
        print(f'Cron job registration (10 jobs): {elapsed:.3f}s')

import asyncio
asyncio.run(test_cron_perf())
"

# 檢查工具註冊和分派速度
python -c "
import time
from claw.tools.registry import get_tools

start = time.time()
tools = get_tools()
elapsed = time.time() - start

print(f'Tool registry lookup: {elapsed:.3f}s')
print(f'Total tools registered: {len(tools)}')
"
```

**預期輸出**：基線性能指標（memory search、cron job、tool registry 各項耗時）

### 1.2 優化記憶體搜尋（sqlite-vec + FTS5）

在 `claw/memory/sqlite_store.py` 中加入快取層：

```python
# 在 MemoryStore 類中加入快取
from functools import lru_cache
from datetime import datetime, timedelta

class MemoryStore:
    # ... 現有代碼 ...

    def __init__(self, db_path: str):
        # ... 現有代碼 ...
        self.search_cache = {}  # Dict[str, (datetime, List[Dict])]
        self.cache_ttl_seconds = 300  # 5 分鐘 TTL

    async def search(self, query: str, limit: int = 5, use_cache: bool = True):
        """
        Search with optional caching.

        Caching strategy:
        - Cache key: f"{query}:{limit}"
        - TTL: 5 minutes
        - Invalidate on save()
        """
        if use_cache:
            cache_key = f"{query}:{limit}"
            if cache_key in self.search_cache:
                cached_time, cached_results = self.search_cache[cache_key]
                if datetime.now() - cached_time < timedelta(seconds=self.cache_ttl_seconds):
                    return cached_results

        # 執行搜尋（現有邏輯）
        results = await self._search_impl(query, limit)

        # 更新快取
        if use_cache:
            self.search_cache[cache_key] = (datetime.now(), results)

        return results

    async def save(self, key: str, value: str, **metadata):
        """Invalidate cache on save."""
        self.search_cache.clear()  # 清除所有快取
        # 執行存儲（現有邏輯）
        return await self._save_impl(key, value, **metadata)
```

**驗收**：
- 記憶體搜尋快取已實裝
- 快取 TTL 設為 5 分鐘
- save() 時自動清除快取

### 1.3 優化股票資料快取

在 `claw/tools/stock_tools.py` 中加入股票資料快取：

```python
from functools import lru_cache
from datetime import datetime, timedelta

# 全局快取（每股票保留最近一次拉取的資料）
_stock_data_cache = {}  # Dict[str, (datetime, dict)]
STOCK_DATA_CACHE_TTL = 3600  # 1 小時

def stock_fetch(symbol: str, period: str = "1y", source: str = "auto", use_cache: bool = True) -> dict:
    """
    Fetch stock data with caching.

    Caching:
    - Cache 當日 OHLCV 資料（避免重複拉取）
    - TTL: 1 小時
    """
    cache_key = f"{symbol}:{period}"

    if use_cache and cache_key in _stock_data_cache:
        cache_time, cached_data = _stock_data_cache[cache_key]
        if datetime.now() - cache_time < timedelta(seconds=STOCK_DATA_CACHE_TTL):
            logger.debug(f"Stock data cache hit for {symbol}")
            return cached_data

    # 執行拉取（現有邏輯）
    result = _stock_fetch_impl(symbol, period, source)

    # 更新快取
    _stock_data_cache[cache_key] = (datetime.now(), result)

    return result
```

**驗收**：
- 股票資料快取已實裝（TTL 1 小時）
- 快取命中時返回快取資料
- logger.debug 記錄快取命中

### 1.4 優化 Cron job 批次執行

在 `claw/cron/service.py` 中加入批次執行和優先級：

```python
class CronService:
    # ... 現有代碼 ...

    async def _execute_batch(self, jobs: list) -> list:
        """
        Execute multiple jobs in parallel (up to 3 concurrent).

        優化策略：
        - 限制並發數（避免過載 Jetson）
        - 優先執行高優先級 job（如晨報）
        - 記錄執行時間用於 monitoring
        """
        import asyncio
        from concurrent.futures import Semaphore

        semaphore = asyncio.Semaphore(3)  # 最多 3 個並發

        async def run_with_semaphore(job):
            async with semaphore:
                start_time = datetime.now()
                try:
                    result = await self._execute_job(job)
                    elapsed = (datetime.now() - start_time).total_seconds()
                    logger.info(f"Job {job['name']} completed in {elapsed:.2f}s")
                    return result
                except Exception as e:
                    logger.error(f"Job {job['name']} failed: {e}")
                    return None

        return await asyncio.gather(*[run_with_semaphore(job) for job in jobs])
```

**驗收**：
- Cron 批次執行已實裝
- 並發限制為 3
- 執行時間被記錄

---

## Task 2 — Bug 修復和穩定性改進

### 2.1 檢查並修復已知問題

執行詳細的測試掃描：

```bash
# 執行所有測試並捕捉任何失敗
python -m pytest tests/ -v --tb=short 2>&1 | tee test_report.txt

# 檢查 asyncio 警告
python -m pytest tests/ -W error::RuntimeWarning -v 2>&1 | tee asyncio_warnings.txt

# 檢查 FTS5 相關測試（已知的潛在問題）
python -m pytest tests/ -k "memory" -v 2>&1 | tee memory_tests.txt

# 檢查 search 相關測試
python -m pytest tests/ -k "search" -v 2>&1 | tee search_tests.txt
```

### 2.2 修復異步資源洩漏

在 `claw/core/gateway.py` 中改進 lifespan 清理：

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # ... 現有初始化代碼 ...

    logger.info("All services started successfully")

    yield

    # === 改進的關閉邏輯 ===
    logger.info("Starting graceful shutdown...")

    try:
        # 1. 停止 Cron service（防止新 job 啟動）
        if hasattr(gateway_module, 'cron_service') and gateway_module.cron_service:
            await gateway_module.cron_service.stop()
            logger.info("CronService stopped")
    except Exception as e:
        logger.error(f"Error stopping CronService: {e}")

    try:
        # 2. 關閉 MCP bridge
        if hasattr(gateway_module, 'mcp_bridge') and gateway_module.mcp_bridge:
            await gateway_module.mcp_bridge.close_all()
            logger.info("MCPBridge closed")
    except Exception as e:
        logger.error(f"Error closing MCPBridge: {e}")

    try:
        # 3. 關閉所有 channels
        for channel in channels:
            await channel.stop()
        logger.info(f"All channels stopped ({len(channels)} channels)")
    except Exception as e:
        logger.error(f"Error stopping channels: {e}")

    try:
        # 4. 銷毀所有 Docker 容器
        await get_runner().destroy_all()
        logger.info("Docker containers destroyed")
    except Exception as e:
        logger.error(f"Error destroying Docker containers: {e}")

    try:
        # 5. 關閉 LLM 客戶端
        if hasattr(gateway_module, 'llm') and gateway_module.llm:
            await gateway_module.llm.close()
            logger.info("LLM client closed")
    except Exception as e:
        logger.error(f"Error closing LLM client: {e}")

    # 停止 session reaper
    reaper.stop()

    logger.info("Graceful shutdown completed")
```

**驗收**：
- Lifespan cleanup 邏輯改進
- 所有資源都被正確釋放
- 日誌記錄完整

### 2.3 改進錯誤處理

在主要工具和 Cron job 中加入更好的錯誤恢復：

```python
# 在 claw/tools/stock_tools.py 中改進 stock_fetch 的錯誤處理

def stock_fetch(symbol: str, period: str = "1y", source: str = "auto", use_cache: bool = True, max_retries: int = 3) -> dict:
    """
    Fetch with retry logic.
    """
    import time

    for attempt in range(max_retries):
        try:
            # ... 現有 fetch 邏輯 ...
            return result
        except ConnectionError as e:
            logger.warning(f"Connection error (attempt {attempt+1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # exponential backoff: 1s, 2s, 4s
                time.sleep(wait_time)
            else:
                raise
        except ValueError as e:
            logger.error(f"Invalid symbol or data: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error: {e}", exc_info=True)
            raise
```

**驗收**：
- 重試邏輯已實裝（exponential backoff）
- 不同錯誤類型被妥善處理
- 日誌記錄清晰

---

## Task 3 — Jetson JetPack 6 部署優化

### 3.1 檢查 Jetson 特定設定

創建 `scripts/jetson_check.py`：

```python
#!/usr/bin/env python3
"""
Jetson Orin Nano Super diagnostic and optimization script.
"""
import os
import sys
import subprocess
from pathlib import Path

def check_jetpack_version():
    """Check JetPack version."""
    try:
        result = subprocess.run(['cat', '/etc/nv_tegra_release'], capture_output=True, text=True)
        print("=== JetPack Version ===")
        print(result.stdout)
    except Exception as e:
        print(f"Could not determine JetPack version: {e}")

def check_memory():
    """Check memory usage."""
    print("\n=== Memory Status ===")
    try:
        with open('/proc/meminfo', 'r') as f:
            lines = f.readlines()
            for line in lines[:10]:
                print(line.strip())
    except Exception as e:
        print(f"Could not read memory info: {e}")

def check_disk():
    """Check disk usage."""
    print("\n=== Disk Usage ===")
    try:
        result = subprocess.run(['df', '-h'], capture_output=True, text=True)
        print(result.stdout)
    except Exception as e:
        print(f"Could not check disk: {e}")

def check_docker():
    """Check Docker installation and status."""
    print("\n=== Docker Status ===")
    try:
        result = subprocess.run(['docker', 'ps'], capture_output=True, text=True)
        print(f"Docker available: ✓")
        print(f"Running containers: {len(result.stdout.split(chr(10)))-2}")
    except Exception as e:
        print(f"Docker status: ✗ ({e})")

def check_python_dependencies():
    """Check critical Python dependencies."""
    print("\n=== Python Dependencies ===")
    required = ['fastapi', 'uvicorn', 'pydantic', 'sqlalchemy', 'yfinance', 'ta', 'mplfinance']
    for pkg in required:
        try:
            __import__(pkg)
            print(f"✓ {pkg}")
        except ImportError:
            print(f"✗ {pkg} (MISSING)")

if __name__ == '__main__':
    check_jetpack_version()
    check_memory()
    check_disk()
    check_docker()
    check_python_dependencies()
    print("\n=== Diagnostics Complete ===")
```

**執行**：
```bash
python scripts/jetson_check.py
```

### 3.2 優化 Docker 容器設定

在 `claw/sandbox/docker_runner.py` 中調整 Jetson 參數：

```python
class DockerRunner:
    def _create_container(self, ...):
        """Create container with Jetson-optimized settings."""

        # Jetson Orin Nano 特定優化
        host_config = docker.types.HostConfig(
            # 限制 CPU（Jetson Orin Nano 有 8 核，避免全部占用）
            cpuset_cpus="0-3",  # 只用前 4 核

            # 限制記憶體（8GB unified memory）
            mem_limit="1g",  # 每個容器最多 1GB

            # 網絡隔離
            network_mode="none",

            # 讀寫設定
            read_only=True,

            # tmpfs（避免 SSD 頻繁寫入）
            tmpfs={"/tmp": {"size": "100M", "mode": "1777"}},

            # 日誌驅動（避免日誌填滿磁盤）
            log_config=docker.types.LogConfig(
                type=docker.types.LogConfig.types.JSON,
                config={"max-size": "10m", "max-file": "3"}
            ),
        )

        # 建立容器
        container = self.client.containers.create(
            image=image,
            command=cmd,
            host_config=host_config,
            # ... 其他設定 ...
        )

        return container
```

**驗收**：
- CPU 限制已設定（4 核）
- 記憶體限制已設定（1GB/容器）
- 日誌管理已優化

### 3.3 調整 Jetson 系統設定

創建 `scripts/jetson_optimize.sh`：

```bash
#!/bin/bash
# Jetson Orin Nano Super optimization script

echo "=== Jetson Orin Nano Optimization ==="

# 1. 設定 CPU governor 為 performance（交易所數據實時性）
echo "Setting CPU governor to performance..."
echo performance | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor

# 2. 禁用某些不必要的系統服務（釋放記憶體）
echo "Disabling unnecessary services..."
sudo systemctl disable --now cups.service 2>/dev/null || true
sudo systemctl disable --now bluetooth.service 2>/dev/null || true

# 3. 設定 swap（防止 OOM）
if [ ! -f /swapfile ]; then
    echo "Creating swap file..."
    sudo fallocate -l 2G /swapfile
    sudo chmod 600 /swapfile
    sudo mkswap /swapfile
    sudo swapon /swapfile
    echo "/swapfile none swap sw 0 0" | sudo tee -a /etc/fstab
fi

# 4. 最大化 inotify watches（用於 file system 監控）
echo "Increasing inotify watches..."
echo "fs.inotify.max_user_watches=524288" | sudo tee /etc/sysctl.d/40-inotify.conf
sudo sysctl -p /etc/sysctl.d/40-inotify.conf

# 5. 時區設定（確保 Cron job 在正確時間執行）
echo "Setting timezone to Asia/Taipei..."
sudo timedatectl set-timezone Asia/Taipei

echo "=== Optimization Complete ==="
```

**執行**：
```bash
chmod +x scripts/jetson_optimize.sh
./scripts/jetson_optimize.sh
```

---

## Task 4 — Monitoring 和 Logging 完整化

### 4.1 擴充 Metrics endpoint

在 `claw/core/gateway.py` 中改進 `/admin/metrics` endpoint：

```python
@app.get("/admin/metrics")
async def get_metrics():
    """
    Return comprehensive system metrics.

    Returns:
        {
            "timestamp": "2026-03-23T10:30:00Z",
            "system": {
                "uptime_seconds": 3600,
                "memory_mb": {"used": 1024, "free": 7000, "percent": 14.6},
                "cpu_percent": 45.2,
                "disk_mb": {"used": 20480, "free": 500000, "percent": 4.1}
            },
            "application": {
                "active_sessions": 5,
                "tools_registered": 28,
                "memory_cache_size": 256,
                "cron_jobs_active": 2
            },
            "performance": {
                "avg_request_latency_ms": 125.3,
                "p95_latency_ms": 450.2,
                "requests_per_second": 12.5,
                "errors_per_minute": 0.1
            },
            "database": {
                "memory_items": 1523,
                "session_count": 5,
                "last_backup": "2026-03-23T08:00:00Z"
            }
        }
    """
    import psutil
    from datetime import datetime

    process = psutil.Process()

    return {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "system": {
            "uptime_seconds": int(time.time() - process.create_time()),
            "memory_mb": {
                "used": int(psutil.virtual_memory().used / 1024 / 1024),
                "free": int(psutil.virtual_memory().available / 1024 / 1024),
                "percent": psutil.virtual_memory().percent
            },
            "cpu_percent": psutil.cpu_percent(interval=0.1),
            "disk_mb": {
                "used": int(psutil.disk_usage('/').used / 1024 / 1024),
                "free": int(psutil.disk_usage('/').free / 1024 / 1024),
                "percent": psutil.disk_usage('/').percent
            }
        },
        "application": {
            "active_sessions": len(gateway_module.storage._sessions) if hasattr(gateway_module.storage, '_sessions') else 0,
            "tools_registered": len(get_tools()),
            "memory_cache_size": len(gateway_module.memory.store.search_cache) if hasattr(gateway_module.memory.store, 'search_cache') else 0,
            "cron_jobs_active": len(gateway_module.cron_service.jobs) if hasattr(gateway_module, 'cron_service') else 0
        }
    }
```

### 4.2 增強結構化日誌

在 `claw/core/logger.py` 中加入更多日誌級別：

```python
import logging
import json
from datetime import datetime

class StructuredFormatter(logging.Formatter):
    """Structured JSON logging for better log analysis."""

    def format(self, record):
        log_obj = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno
        }

        # 如果有異常，加入 traceback
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)

        # 如果有額外欄位，加入
        if hasattr(record, 'session_id'):
            log_obj["session_id"] = record.session_id
        if hasattr(record, 'tool_name'):
            log_obj["tool_name"] = record.tool_name
        if hasattr(record, 'duration_ms'):
            log_obj["duration_ms"] = record.duration_ms

        return json.dumps(log_obj, ensure_ascii=False)

def configure_logging(level: str = "INFO", fmt: str = "json"):
    """
    Configure structured logging.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        fmt: Format ("json" for structured, "text" for human-readable)
    """
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, level.upper()))

    # Console handler
    handler = logging.StreamHandler()

    if fmt == "json":
        formatter = StructuredFormatter()
    else:
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )

    handler.setFormatter(formatter)
    logger.addHandler(handler)
```

**驗收**：
- `/admin/metrics` endpoint 返回完整指標
- 結構化日誌已實裝
- 支援 JSON 和文字兩種格式

---

## Task 5 — 建立效能基準測試

建立 `tests/test_performance.py`：

```python
"""Performance benchmarks for critical paths."""
import pytest
import time
import asyncio
from unittest.mock import patch, MagicMock

@pytest.mark.asyncio
async def test_memory_search_performance():
    """Memory search should complete in < 100ms."""
    from claw.memory.manager import MemoryManager

    mock_llm = MagicMock()
    mock_store = MagicMock()
    mgr = MemoryManager(store=mock_store, llm=mock_llm)

    start = time.time()
    # 模擬搜尋 100 筆記錄
    for _ in range(100):
        await mgr.search("test")
    elapsed = time.time() - start

    # 應該在 100ms 以內（平均每筆 < 1ms）
    assert elapsed < 0.1, f"Memory search too slow: {elapsed:.3f}s"


@pytest.mark.asyncio
async def test_stock_fetch_performance():
    """Stock fetch with cache should complete in < 500ms."""
    from claw.tools.stock_tools import stock_fetch

    with patch("claw.tools.stock_tools._stock_fetch_impl") as mock_fetch:
        mock_fetch.return_value = {"ohlcv": []}

        start = time.time()
        result = stock_fetch("2330", use_cache=True)
        elapsed = time.time() - start

        # 無快取：< 1s，有快取：< 10ms
        assert elapsed < 0.5, f"Stock fetch too slow: {elapsed:.3f}s"


@pytest.mark.asyncio
async def test_tool_dispatch_performance():
    """Tool dispatch should complete in < 50ms."""
    from claw.tools.registry import get_tools

    start = time.time()
    tools = get_tools()
    elapsed = time.time() - start

    assert elapsed < 0.05, f"Tool lookup too slow: {elapsed:.3f}s"
    assert len(tools) >= 28, f"Expected 28+ tools, got {len(tools)}"
```

**驗收**：
- 3 個效能測試已建立
- 測試通過（效能指標達成）

---

## Task 6 — 執行完整測試和驗收

```bash
cd /home/martin/Desktop/claw-python-personal

# 清除快取和舊資料
python -c "
import shutil
from pathlib import Path
for p in ['.pytest_cache', '__pycache__', '.mypy_cache']:
    for d in Path('.').rglob(p):
        shutil.rmtree(d, ignore_errors=True)
print('Cache cleaned')
"

# 執行所有測試（包含新增的效能測試）
python -m pytest tests/ -v --tb=short 2>&1 | tee s5_test_report.txt

# 檢查覆蓋率
python -m pytest tests/ --cov=claw --cov-report=html 2>&1 | tee coverage_report.txt

# 執行 Jetson 診斷
python scripts/jetson_check.py 2>&1 | tee jetson_diagnostic.txt

# 檢查 Metrics endpoint
python -c "
from claw.core.gateway import app
from fastapi.testclient import TestClient

client = TestClient(app)
response = client.get('/admin/metrics')
print('Metrics endpoint test:')
print(f'Status: {response.status_code}')
if response.status_code == 200:
    import json
    metrics = response.json()
    print(json.dumps(metrics, indent=2))
else:
    print(f'Error: {response.text}')
" 2>&1 | tee metrics_test.txt
```

**預期輸出**：
- `206+ passed, 3 skipped`（新增 21+ 個效能和優化測試）
- 0 failures
- 所有 metrics 返回有效數據

---

## 交付清單

完成後回報：

1. **修改的檔案絕對路徑**（性能優化）：
   - `/home/martin/Desktop/claw-python-personal/claw/memory/sqlite_store.py`
   - `/home/martin/Desktop/claw-python-personal/claw/tools/stock_tools.py`
   - `/home/martin/Desktop/claw-python-personal/claw/cron/service.py`
   - `/home/martin/Desktop/claw-python-personal/claw/core/gateway.py`
   - `/home/martin/Desktop/claw-python-personal/claw/core/logger.py`
   - `/home/martin/Desktop/claw-python-personal/claw/sandbox/docker_runner.py`

2. **新建的檔案絕對路徑**：
   - `/home/martin/Desktop/claw-python-personal/scripts/jetson_check.py`
   - `/home/martin/Desktop/claw-python-personal/scripts/jetson_optimize.sh`
   - `/home/martin/Desktop/claw-python-personal/tests/test_performance.py`

3. **pytest 最終輸出**（應為 206+ passed）

4. **效能基準**（執行 jetson_check.py、metrics 測試結果）

5. **遇到的問題和解決方式**

---

## 完成標準

✅ 記憶體搜尋快取已實裝（TTL 5 分鐘）
✅ 股票資料快取已實裝（TTL 1 小時）
✅ Cron job 批次執行已實裝（並發限制 3）
✅ Lifespan cleanup 邏輯改進（無資源洩漏）
✅ 重試邏輯已實裝（exponential backoff）
✅ Jetson 特定優化已完成（CPU/記憶體限制）
✅ `/admin/metrics` endpoint 完整化
✅ 結構化 JSON 日誌已實裝
✅ 效能基準測試已建立並通過
✅ 206+ tests pass, 0 failures

---

## 注意事項

- 快取 TTL 設定應根據實際使用調整
- Jetson CPU governor 設定需要 root 權限
- 監控指標應定期檢查以發現性能瓶頸
- 日誌格式變更後要確保下游日誌分析工具相容

