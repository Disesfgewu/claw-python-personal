# Phase 10.5 Worker Prompt — Production 接線 + Hotfix

你是實作 claw-python Phase 10.5 的 worker。工作目錄：`/home/martin/Desktop/claw-python-personal/`。
當前狀態：154 tests 通過，0 failures。**嚴格按照順序，每步驗證後再繼續。**

---

## 背景說明

Phase 8a～10 已完成功能實作，但有兩類問題：

1. **Bug**：`router_client.py` 的 embedding model 名稱錯誤，導致 memory 語意搜尋打 Router 時失敗
2. **接線缺失**：`main.py` 從未 import 或初始化 web_fetch / file_tools / research_tools / MCPBridge / ResearchLoop，這些功能在 production 環境中完全不會運作

---

## 閱讀清單（開始前必讀）

- `claw/main.py`：lifespan 函數結構，了解現有的初始化模式
- `claw/tools/__init__.py`：目前的工具 import 清單
- `claw/tools/mcp_bridge.py`：MCPBridge class，`load_servers()`、`set_mcp_bridge()`
- `claw/research/loop.py`：`init_research_loop()`、`set_research_loop()`
- `claw/llm/router_client.py`：`get_embedding()` 第 163-175 行
- `config/default.yaml`：`mcp.servers` 設定結構

---

## Task 1 — 修正 `claw/llm/router_client.py` embedding model 名稱

找到 `get_embedding()` 方法中的這一行：

```python
json={"input": text, "model": "default"},
```

改成：

```python
json={"input": text, "model": "gemini-embedding-2-preview"},
```

只改這一行，不改其他任何內容。

---

## Task 2 — 修改 `claw/main.py` 補齊所有接線

### 2a. 在 import 區塊補齊工具 import

在現有的：
```python
import claw.tools.bash    # 觸發 bash tool 的注冊
import claw.tools.search  # 觸發 search_web tool 的注冊
import claw.tools.memory_tools  # 觸發 memory_save / memory_search 工具注冊
```

後面加入：

```python
import claw.tools.web_fetch      # 觸發 web_fetch tool 的注冊
import claw.tools.file_tools     # 觸發 file_read/write/list/delete 工具注冊
import claw.tools.research_tools  # 觸發 research_start/experiment_record/research_status 工具注冊
```

### 2b. 在 lifespan 函數中初始化 ResearchLoop

在 `_mem_tools.set_memory_manager(memory_manager)` 之後、`gateway_module.storage = storage` 之前加入：

```python
    # ResearchLoop 初始化（AutoResearch 功能）
    from claw.research.loop import init_research_loop
    init_research_loop(llm=llm, storage=storage, memory=memory_manager)
    logger.info("ResearchLoop initialized")
```

### 2c. 在 lifespan 函數中初始化 MCPBridge

在 ResearchLoop 初始化之後加入：

```python
    # MCP Bridge 初始化（連接外部 MCP servers）
    from claw.tools.mcp_bridge import MCPBridge, MCPServerConfig, set_mcp_bridge
    mcp_bridge = MCPBridge()
    if hasattr(cfg, "mcp") and cfg.mcp and hasattr(cfg.mcp, "servers"):
        mcp_server_configs = []
        for s in (cfg.mcp.servers or []):
            if isinstance(s, dict) and s.get("enabled", True):
                mcp_server_configs.append(MCPServerConfig(
                    name=s.get("name", "unknown"),
                    transport=s.get("transport", "stdio"),
                    command=s.get("command", []),
                    url=s.get("url", ""),
                    enabled=s.get("enabled", True),
                ))
        if mcp_server_configs:
            count = await mcp_bridge.load_servers(mcp_server_configs)
            logger.info(f"MCPBridge loaded {count} tools from {len(mcp_server_configs)} servers")
    set_mcp_bridge(mcp_bridge)
```

### 2d. 在 lifespan 的 teardown（yield 之後）加入 MCPBridge 關閉

在 `reaper.stop()` 之後加入：

```python
    await mcp_bridge.close_all()
```

---

## Task 3 — 確認 `config/default.yaml` 有正確的 mcp 設定

確認 `config/default.yaml` 末尾已有（Phase 10 worker 應已加入，確認即可）：

```yaml
mcp:
  servers: []
```

如果沒有則加入。不需要預設啟用任何 server。

---

## Task 4 — 建立測試 `tests/test_main_wiring.py`（3 tests）

```python
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_web_fetch_tool_registered():
    """web_fetch tool is registered after importing claw.tools.web_fetch."""
    import claw.tools.web_fetch  # noqa: F401
    from claw.tools.registry import get_tools
    tools = get_tools()
    assert any(t.name == "web_fetch" for t in tools), "web_fetch not registered"


@pytest.mark.asyncio
async def test_research_tools_registered():
    """research_start, experiment_record, research_status are registered."""
    import claw.tools.research_tools  # noqa: F401
    from claw.tools.registry import get_tools
    tools = get_tools()
    names = {t.name for t in tools}
    assert "research_start" in names
    assert "experiment_record" in names
    assert "research_status" in names


@pytest.mark.asyncio
async def test_file_tools_registered():
    """file_read, file_write, file_list, file_delete are registered."""
    import claw.tools.file_tools  # noqa: F401
    from claw.tools.registry import get_tools
    tools = get_tools()
    names = {t.name for t in tools}
    assert "file_read" in names
    assert "file_write" in names
    assert "file_list" in names
    assert "file_delete" in names
```

---

## Task 5 — 執行測試

```bash
cd /home/martin/Desktop/claw-python-personal
python -m pytest tests/ -x --tb=short
```

預期：**157 tests 通過，0 failures**（154 + 3 新增）

---

## 交付清單

完成後回報：
1. 每個修改的檔案（絕對路徑）+ 改了什麼
2. pytest 最終輸出最後 5 行
3. 遇到的問題和解決方式

---

## 預期測試計數

| 來源 | 數量 |
|---|---|
| Phase 10（現有） | 154 |
| test_main_wiring.py | +3 |
| **目標** | **157** |
