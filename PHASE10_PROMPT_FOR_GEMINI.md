# Phase 10 Worker Prompt — MCP Bridge

你是實作 claw-python Phase 10 的 worker。工作目錄：`/home/martin/Desktop/claw-python-personal/`。
當前狀態：145 tests 通過，0 failures。**嚴格按照順序，每步驗證後再繼續。**

> ⚠️ 注意：Phase 9b 也在同步進行中（不同 worker）。
> Phase 10 不碰 `claw/research/` 和 `claw/agent/loop.py`，不會衝突。

---

## 背景

MCP（Model Context Protocol）是連接外部工具伺服器的標準協定。
目標：讓 claw 能載入外部 MCP server，自動映射其工具到 claw 的 tool registry，
讓 agent（包括 ResearchLoop）能透明地呼叫外部工具。

### MCP JSON-RPC 2.0 通訊協定

MCP 使用 JSON-RPC 2.0，支援兩種 transport：

**stdio transport**（subprocess）：
```
stdin/stdout 雙向 JSON-RPC 串流
每行一個 JSON 物件，以 \n 結尾
```

**SSE transport**（HTTP）：
```
POST /messages  →  送出請求
GET  /sse       →  接收 SSE 事件串流
```

**三個核心方法**：
```json
// 1. Initialize
{"jsonrpc":"2.0","method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"claw","version":"1.0"}},"id":1}
// 回應：{"jsonrpc":"2.0","result":{"protocolVersion":"2024-11-05","capabilities":{},"serverInfo":{...}},"id":1}

// 2. List tools
{"jsonrpc":"2.0","method":"tools/list","params":{},"id":2}
// 回應：{"jsonrpc":"2.0","result":{"tools":[{"name":"...","description":"...","inputSchema":{...}}]},"id":2}

// 3. Call tool
{"jsonrpc":"2.0","method":"tools/call","params":{"name":"tool_name","arguments":{...}},"id":3}
// 回應：{"jsonrpc":"2.0","result":{"content":[{"type":"text","text":"..."}]},"id":3}
```

---

## 閱讀清單（開始前必讀）

- `claw/tools/registry.py`：@tool decorator 和 ToolRegistry class，了解如何動態新增工具
- `claw/tools/web_fetch.py`：tool function 的寫法模式（參數、回傳格式）
- `claw/tools/__init__.py`：目前的 import 清單
- `config/default.yaml`：yaml 結構，了解如何加 mcp_servers 段落
- `tests/test_tools.py`：tool 測試的寫法模式

---

## Task 1 — 閱讀 `claw/tools/registry.py`

在開始前，閱讀 registry.py 了解：
- `@tool` decorator 的完整 signature
- `ToolRegistry` 的 `register()` 方法（或動態加入工具的方式）
- tool function 的呼叫慣例（特別是 `session_id` 參數如何傳入）

---

## Task 2 — 建立 `claw/tools/mcp_bridge.py`

```python
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class MCPServerConfig:
    name: str                       # e.g. "filesystem"
    transport: str                  # "stdio" | "sse"
    command: list[str] = field(default_factory=list)  # stdio: ["npx", "-y", "@mcp/filesystem", "/tmp"]
    url: str = ""                   # sse: "http://localhost:3001"
    enabled: bool = True


@dataclass
class MCPTool:
    server_name: str
    name: str                       # tool name as reported by MCP server
    description: str
    input_schema: dict              # JSON Schema for parameters


# ---------------------------------------------------------------------------
# MCPClient — handles one MCP server connection
# ---------------------------------------------------------------------------

class MCPClient:
    """Manages a single MCP server connection (stdio or SSE)."""

    def __init__(self, config: MCPServerConfig):
        self.config = config
        self._req_id = 0
        # stdio state
        self._proc: asyncio.subprocess.Process | None = None
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None

    def _next_id(self) -> int:
        self._req_id += 1
        return self._req_id

    async def connect(self) -> None:
        """Connect to the MCP server and perform initialize handshake."""
        if self.config.transport == "stdio":
            await self._connect_stdio()
        elif self.config.transport == "sse":
            await self._connect_sse()
        else:
            raise ValueError(f"Unknown transport: {self.config.transport}")

        await self._initialize()

    async def _connect_stdio(self) -> None:
        self._proc = await asyncio.create_subprocess_exec(
            *self.config.command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        self._reader = self._proc.stdout  # type: ignore[assignment]
        self._writer = self._proc.stdin   # type: ignore[assignment]

    async def _connect_sse(self) -> None:
        # SSE transport: stateless HTTP, no persistent connection needed
        # _call_sse handles each request independently
        pass

    async def _initialize(self) -> None:
        resp = await self._call({
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "claw", "version": "1.0"},
            },
        })
        logger.info(
            f"mcp.connected server={self.config.name} "
            f"info={resp.get('result', {}).get('serverInfo', {})}"
        )

    async def list_tools(self) -> list[MCPTool]:
        resp = await self._call({"method": "tools/list", "params": {}})
        tools_data = resp.get("result", {}).get("tools", [])
        return [
            MCPTool(
                server_name=self.config.name,
                name=t["name"],
                description=t.get("description", ""),
                input_schema=t.get("inputSchema", {"type": "object", "properties": {}}),
            )
            for t in tools_data
        ]

    async def call_tool(self, tool_name: str, arguments: dict) -> str:
        resp = await self._call({
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
        })
        if "error" in resp:
            return f"Error: {resp['error'].get('message', str(resp['error']))}"
        content = resp.get("result", {}).get("content", [])
        parts = [c.get("text", "") for c in content if c.get("type") == "text"]
        return "\n".join(parts) or "(empty response)"

    async def _call(self, payload: dict) -> dict:
        req = {"jsonrpc": "2.0", "id": self._next_id(), **payload}
        if self.config.transport == "stdio":
            return await self._call_stdio(req)
        return await self._call_sse(req)

    async def _call_stdio(self, req: dict) -> dict:
        if self._proc is None or self._writer is None or self._reader is None:
            raise RuntimeError("stdio transport not connected")
        line = json.dumps(req) + "\n"
        self._writer.write(line.encode())
        await self._writer.drain()
        raw = await asyncio.wait_for(self._reader.readline(), timeout=30)
        return json.loads(raw.decode().strip())

    async def _call_sse(self, req: dict) -> dict:
        try:
            import httpx
        except ImportError:
            return {"error": {"message": "httpx not installed"}}
        url = self.config.url.rstrip("/") + "/messages"
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(url, json=req, headers={"Content-Type": "application/json"})
            r.raise_for_status()
            return r.json()

    async def close(self) -> None:
        if self._proc is not None:
            try:
                self._proc.terminate()
                await asyncio.wait_for(self._proc.wait(), timeout=5)
            except Exception:
                pass
            self._proc = None


# ---------------------------------------------------------------------------
# MCPBridge — manages multiple MCP servers, registers tools into claw registry
# ---------------------------------------------------------------------------

class MCPBridge:
    """
    Loads MCP servers from config, discovers their tools,
    and registers them as callable claw tools.
    """

    def __init__(self):
        self._clients: dict[str, MCPClient] = {}
        self._registered_tools: list[str] = []

    async def load_servers(self, server_configs: list[MCPServerConfig]) -> int:
        """Connect to all enabled servers and register their tools. Returns tool count."""
        total = 0
        for cfg in server_configs:
            if not cfg.enabled:
                continue
            try:
                client = MCPClient(cfg)
                await client.connect()
                tools = await client.list_tools()
                self._clients[cfg.name] = client
                for mcp_tool in tools:
                    self._register_tool(mcp_tool, client)
                    total += 1
                logger.info(f"mcp.loaded server={cfg.name} tools={len(tools)}")
            except Exception as e:
                logger.error(f"mcp.load_failed server={cfg.name} error={e}")
        return total

    def _register_tool(self, mcp_tool: MCPTool, client: MCPClient) -> None:
        """Dynamically register an MCP tool into claw's tool registry."""
        from claw.tools.registry import get_registry

        tool_name = f"mcp_{mcp_tool.server_name}_{mcp_tool.name}"
        description = f"[MCP:{mcp_tool.server_name}] {mcp_tool.description}"

        # Build an async callable for this tool
        async def _mcp_caller(session_id: str = "agent:main", **kwargs: Any) -> str:
            return await client.call_tool(mcp_tool.name, kwargs)

        _mcp_caller.__name__ = tool_name

        registry = get_registry()
        registry.register_dynamic(
            name=tool_name,
            description=description,
            parameters=mcp_tool.input_schema,
            fn=_mcp_caller,
        )
        self._registered_tools.append(tool_name)

    def registered_tool_names(self) -> list[str]:
        return list(self._registered_tools)

    async def close_all(self) -> None:
        for client in self._clients.values():
            await client.close()
        self._clients.clear()


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_bridge: MCPBridge | None = None


def get_mcp_bridge() -> MCPBridge | None:
    return _bridge


def set_mcp_bridge(bridge: MCPBridge) -> None:
    global _bridge
    _bridge = bridge
```

---

## Task 3 — 修改 `claw/tools/registry.py`

閱讀 registry.py 後，如果 `ToolRegistry` 沒有 `register_dynamic()` 方法，需要新增一個。

在 `ToolRegistry` class 中加入：

```python
def register_dynamic(
    self,
    name: str,
    description: str,
    parameters: dict,
    fn,
) -> None:
    """Register a dynamically-created tool function (e.g. from MCP bridge)."""
    # Wrap fn as a tool entry in the same format as @tool decorator
    # Read the existing register() method to follow the exact same pattern
    # This method should add the tool to self._tools (or whatever the internal dict is called)
    pass  # REPLACE with actual implementation based on reading registry.py
```

> **重要**：閱讀 registry.py 的 `register()` 或 `@tool` decorator 的實際實作，
> 完全匹配現有的工具儲存格式。不要猜測。

---

## Task 4 — 更新 `config/default.yaml`

在 `logging:` 段落之後加入：

```yaml

mcp:
  servers: []
  # 範例（取消註解以啟用）：
  # - name: filesystem
  #   transport: stdio
  #   command: ["npx", "-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
  #   enabled: true
  # - name: my-sse-server
  #   transport: sse
  #   url: "http://localhost:3001"
  #   enabled: true
```

---

## Task 5 — 更新 `claw/tools/__init__.py`

在現有的最後一行後加入（**注意末尾換行**）：

```python
from claw.tools import mcp_bridge as _mcp_bridge  # noqa: F401
```

---

## Task 6 — 建立 `tests/test_mcp_bridge.py`（3 tests）

```python
from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from claw.tools.mcp_bridge import MCPBridge, MCPClient, MCPServerConfig, MCPTool


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_stdio_config(name="test_server"):
    return MCPServerConfig(
        name=name,
        transport="stdio",
        command=["echo", "{}"],
        enabled=True,
    )


async def _fake_call(payload: dict) -> dict:
    method = payload.get("method", "")
    if method == "initialize":
        return {"jsonrpc": "2.0", "result": {"protocolVersion": "2024-11-05", "serverInfo": {"name": "test"}}, "id": payload["id"]}
    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "result": {
                "tools": [
                    {"name": "read_file", "description": "Read a file", "inputSchema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}},
                ]
            },
            "id": payload["id"],
        }
    if method == "tools/call":
        return {"jsonrpc": "2.0", "result": {"content": [{"type": "text", "text": "file contents here"}]}, "id": payload["id"]}
    return {"jsonrpc": "2.0", "result": {}, "id": payload["id"]}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_mcp_client_list_tools():
    """MCPClient.list_tools() returns MCPTool objects from server response."""
    config = _make_stdio_config()
    client = MCPClient(config)
    client._call = AsyncMock(side_effect=_fake_call)

    # Manually call _initialize (bypasses real subprocess)
    await client._initialize()
    tools = await client.list_tools()

    assert len(tools) == 1
    assert tools[0].name == "read_file"
    assert tools[0].server_name == "test_server"
    assert "path" in tools[0].input_schema.get("properties", {})


@pytest.mark.asyncio
async def test_mcp_client_call_tool():
    """MCPClient.call_tool() returns text content from server response."""
    config = _make_stdio_config()
    client = MCPClient(config)
    client._call = AsyncMock(side_effect=_fake_call)

    result = await client.call_tool("read_file", {"path": "/tmp/test.txt"})
    assert "file contents here" in result


@pytest.mark.asyncio
async def test_mcp_bridge_load_and_register(tmp_path):
    """MCPBridge.load_servers() connects, discovers tools, and registers them."""
    from claw.tools.registry import get_registry

    config = _make_stdio_config("myserver")
    bridge = MCPBridge()

    # Mock the client so no real subprocess is spawned
    mock_client = AsyncMock(spec=MCPClient)
    mock_client.config = config
    mock_tool = MCPTool(
        server_name="myserver",
        name="list_dir",
        description="List directory contents",
        input_schema={"type": "object", "properties": {"path": {"type": "string"}}},
    )
    mock_client.list_tools = AsyncMock(return_value=[mock_tool])

    with patch("claw.tools.mcp_bridge.MCPClient", return_value=mock_client):
        count = await bridge.load_servers([config])

    assert count == 1
    assert "mcp_myserver_list_dir" in bridge.registered_tool_names()
    # Verify it's actually in the registry
    registry = get_registry()
    registered_names = [t.name for t in registry.list_tools()]
    assert "mcp_myserver_list_dir" in registered_names
```

---

## Task 7 — 執行測試

```bash
cd /home/martin/Desktop/claw-python-personal
python -m pytest tests/ -x --tb=short
```

預期：**148 tests 通過，0 failures**（145 + 3 新增）

> 注意：Phase 9b 的 worker 也在加 3 個 tests，如果 9b 已先完成則這裡基礎是 148，
> 目標變成 151。只要最後全數通過即可。

---

## 交付清單

完成後回報：
1. 修改的檔案絕對路徑 + 改了什麼
2. 新建的檔案絕對路徑
3. pytest 最終輸出最後 5 行
4. `get_registry()` 的方法名稱是什麼（register 動態工具用的）
5. 遇到的問題和解決方式

---

## 預期測試計數

| 來源 | 數量 |
|---|---|
| Phase 9 (existing) | 145 |
| test_mcp_bridge.py | +3 |
| **目標** | **148** |
