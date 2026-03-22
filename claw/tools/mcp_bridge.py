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
