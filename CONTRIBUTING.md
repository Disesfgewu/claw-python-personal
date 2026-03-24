# Contributing to claw-python

> **感謝您對 claw-python 的貢獻！**本指南說明如何參與項目開發。

---

## 開發環境設置

### 前置要求

- Python 3.8+
- Docker CE（用於工具隔離測試）
- Git
- pip / poetry（推薦）

### 快速開始

```bash
# 複製項目
git clone https://github.com/yourusername/claw-python.git
cd claw-python

# 建立虛擬環境
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 安裝開發依賴
pip install -e ".[dev]"

# 執行測試驗證環境
pytest tests/ -v
```

---

## 開發流程

### 1. 建立 Feature Branch

```bash
git checkout -b feature/你的功能名稱
# 或
git checkout -b fix/你的修復名稱
```

Branch 命名規範：
- 新功能：`feature/description`（例如 `feature/stock-screening`）
- 修復：`fix/description`（例如 `fix/memory-search-timeout`）
- 文檔：`docs/description`（例如 `docs/api-reference`）
- 性能：`perf/description`（例如 `perf/vector-cache-optimization`）

### 2. 編碼風格

#### Python 程式碼規範

```python
# 使用 type hints
from typing import Optional, Dict, List

def fetch_stock_data(
    symbol: str,
    period: str = "1y",
) -> Dict[str, any]:
    """
    擷取股票資料。

    Args:
        symbol: 股票代碼（例如 "2330"）
        period: 時間週期（"1mo", "3mo", "1y"）

    Returns:
        包含 OHLCV 資料的字典
    """
    pass
```

#### 關鍵規範

- 使用 4 空格縮進（不用 tab）
- 行長度上限 100 字元
- 函數文檔必須包含 Args, Returns, Raises（如適用）
- 使用 f-string 進行字符串格式化
- 常數使用大寫（`MAX_RETRIES = 3`）
- 私有函數/變數以單下劃線開頭（`_private_func`）

#### Pylance 安全標準

所有代碼必須通過 Pylance 檢查（類型安全）：
- 無 `type: ignore` 註釋（除非有充分理由）
- 無未定義的變數使用
- 無無用的導入
- 無可達性問題

### 3. 測試

#### 單元測試

```bash
# 執行所有測試
pytest tests/ -v

# 執行特定測試檔案
pytest tests/unit/test_memory.py -v

# 執行測試並顯示覆蓋率
pytest tests/ --cov=claw --cov-report=html
```

#### 集成測試

```bash
# 需要 LIVE_BACKEND 環境變數
export LIVE_BACKEND=1
pytest tests/integration/ -v
```

#### 測試編寫指南

```python
import pytest
from claw.tools.stock_tools import stock_fetch_data

@pytest.mark.asyncio
async def test_stock_fetch_real_data():
    """驗證實際股票資料拉取"""
    result = await stock_fetch_data("2330", period="1mo")

    assert result is not None
    assert "ohlcv" in result
    assert len(result["ohlcv"]) > 0
    assert result["symbol"] == "2330"
```

最小測試要求：
- 新功能必須包含相應測試（單元 + 集成）
- 修復必須包含重現原 bug 的測試
- 所有測試必須通過（無 skip 除非有充分理由）
- 目標覆蓋率 > 80%

### 4. Commit 和 PR

#### Commit 訊息格式

```
type(scope): subject

body

footer
```

範例：

```
feat(stock): add Ichimoku indicator to technical analysis

- Implement Ichimoku calculation with cloud, signal lines
- Add to stock_analyze() return value
- Update stock_tools.py

Fixes #123
```

Types：
- `feat` — 新功能
- `fix` — 修復 bug
- `docs` — 文檔
- `style` — 程式碼格式（不改邏輯）
- `refactor` — 重構（不改行為）
- `perf` — 性能改進
- `test` — 測試相關
- `chore` — 工具/依賴更新

#### Pull Request

1. Push 到你的 fork

```bash
git push origin feature/你的功能名稱
```

2. 在 GitHub 上建立 PR，包含：
   - 清晰的標題和描述
   - 關聯的 issue 編號（`Fixes #123`）
   - 測試覆蓋說明
   - 任何破壞性改動的遷移指南

3. PR 檢查清單：
   - [ ] 所有測試通過（`pytest`）
   - [ ] Pylance 檢查通過（無 errors）
   - [ ] 代碼已 review（自己先檢查）
   - [ ] 文檔已更新（如需要）
   - [ ] CHANGELOG 已更新（如適用）

---

## 常見的貢獻場景

### 添加新工具

1. 在 `claw/tools/` 中建立新檔案（例如 `my_tool.py`）：

```python
# claw/tools/my_tool.py
from typing import Optional
from claw.core.registry import register_tool

@register_tool(
    name="my_tool",
    description="我的自訂工具",
)
async def my_tool(param1: str, param2: int = 10) -> str:
    """
    執行我的工具。

    Args:
        param1: 輸入參數
        param2: 數值參數

    Returns:
        結果字符串
    """
    # 實作邏輯
    return f"Result: {param1}, {param2}"
```

2. 在 `claw/tools/__init__.py` 中註冊：

```python
from .my_tool import my_tool

__all__ = ["my_tool"]
```

3. 添加測試（`tests/unit/test_my_tool.py`）：

```python
@pytest.mark.asyncio
async def test_my_tool():
    result = await my_tool("test", param2=20)
    assert "test" in result
    assert "20" in result
```

4. 在文檔中添加（`docs/API_REFERENCE.md`）

### 添加新頻道

1. 在 `claw/channels/` 中建立新檔案：

```python
# claw/channels/my_channel.py
from claw.channels.base import BaseChannel

class MyChannel(BaseChannel):
    async def start(self):
        """啟動頻道"""
        pass

    async def stop(self):
        """停止頻道"""
        pass

    async def send(self, message: str):
        """發送訊息"""
        pass
```

2. 在 `claw/main.py` 中初始化

3. 添加測試和文檔

### 改進性能

1. 使用 `cProfile` 或 `py-spy` 識別瓶頸

```bash
python -m cProfile -s cumulative claw/main.py
```

2. 提交 PR 時包含基準測試結果：

```python
def test_performance_stock_fetch(benchmark):
    """股票資料拉取性能基準"""
    result = benchmark(stock_fetch_data, "2330", "1mo")
    assert result is not None
```

---

## 安全性指南

### EgressPolicy（出站規則）

所有外網存取必須通過 `EgressPolicy` 白名單：

```python
# config/egress_policy.yaml
default: deny

whitelist:
  - domain: "*.twse.com.tw"
    ports: [80, 443]
  - domain: "finance.yahoo.com"
    ports: [443]
```

### 工具隔離

Bash 工具必須在 Docker 沙盒中執行：

```python
# ✅ 正確
result = await sandbox.run_command("ls -la")

# ❌ 錯誤
os.system("ls -la")  # 直接執行！
```

### 敏感資料

- **絕不提交** API keys, tokens, 密碼
- 使用環境變數（`os.getenv("TOKEN")`）
- `.env` 已加入 `.gitignore`
- 使用 `config/secrets.example.yaml` 作為範本

---

## 文檔貢獻

### 文檔檔案

- `README.md` — 項目概述
- `docs/ARCHITECTURE.md` — 系統架構
- `docs/DEPLOYMENT_GUIDE.md` — 部署指南
- `docs/API_REFERENCE.md` — API 文檔
- `docs/FAQ.md` — 常見問題
- `ROADMAP.md` — 開發路線圖
- `CONTRIBUTING.md` — 本檔案

### 文檔標準

- 使用 Markdown 格式
- 包含程式碼示例
- 保持最新（與實現同步）
- 中英混用時，標點符號遵循：中文用全寬，英文用半寬

---

## 故障排除

### 常見問題

#### "pytest: command not found"

```bash
pip install pytest pytest-asyncio
```

#### Docker 沙盒錯誤

```bash
# 確認 Docker 執行中
docker ps

# 檢查權限
sudo usermod -aG docker $USER
newgrp docker
```

#### 記憶體搜尋很慢

- 執行 `python -m claw.memory.manager --rebuild-index`
- 檢查 `~/.claw/memory.db` 大小

---

## 社群溝通

### 報告 Bug

使用 GitHub Issues，包含：
- 重現步驟
- 預期行為
- 實際行為
- 環境資訊（OS, Python 版本, Jetson model 等）
- 錯誤日誌

### 提議功能

- 使用 GitHub Discussions
- 說明用途和期望的行為
- 提供範例或使用案例

### 聯繫

- Issues: https://github.com/yourusername/claw-python/issues
- Discussions: https://github.com/yourusername/claw-python/discussions
- Email: your.email@example.com

---

## 授權

所有貢獻均視為接受 MIT 授權。重大改動請先開 Issue 討論。

---

感謝您的貢獻！🚀
