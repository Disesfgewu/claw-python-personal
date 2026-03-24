from __future__ import annotations

import asyncio
import contextlib
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
    headers: dict[str, str] = field(default_factory=dict)
    sse_mode: str = "post"          # "post" (default) or "stream" (SSE endpoint + JSON-RPC)
    sse_path: str = ""              # post mode: request path; stream mode: SSE path
    protocol_version: str = "2024-11-05"
    client_info: dict[str, str] = field(default_factory=lambda: {"name": "claw", "version": "1.0"})


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
        # sse stream state (stream mode only)
        self._sse_client: Any = None
        self._sse_stream_cm: Any = None
        self._sse_response: Any = None
        self._sse_reader_task: asyncio.Task | None = None
        self._sse_message_queue: asyncio.Queue[dict] | None = None
        self._sse_endpoint: str | None = None
        self._sse_session_id: str | None = None

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
        if self.config.sse_mode != "stream":
            # SSE post mode doesn't need a persistent connection.
            return
        try:
            import httpx
        except ImportError:
            raise RuntimeError("httpx not installed")

        base_url = self.config.url.rstrip("/")
        sse_path = self._resolve_sse_path("/mcp/sse")
        sse_url = self._build_url(base_url, sse_path)

        headers = {"Accept": "text/event-stream", **self.config.headers}
        timeout = httpx.Timeout(connect=10, read=30, write=10, pool=10)
        self._sse_client = httpx.AsyncClient(timeout=timeout)
        self._sse_stream_cm = self._sse_client.stream("GET", sse_url, headers=headers)
        self._sse_response = await self._sse_stream_cm.__aenter__()
        self._sse_response.raise_for_status()

        # Try to capture session id from headers if provided by server.
        self._sse_session_id = self._extract_session_id_from_headers(getattr(self._sse_response, "headers", {}))

        endpoint_future: asyncio.Future[str] = asyncio.get_event_loop().create_future()
        self._sse_message_queue = asyncio.Queue()
        self._sse_reader_task = asyncio.create_task(
            self._consume_sse(self._sse_response, endpoint_future, self._sse_message_queue)
        )

        try:
            endpoint = await asyncio.wait_for(endpoint_future, timeout=10)
            endpoint_url, endpoint_sid = self._parse_endpoint_data(endpoint, base_url)
            self._sse_endpoint = endpoint_url
            if endpoint_sid:
                self._sse_session_id = endpoint_sid
        except asyncio.TimeoutError:
            # Server didn't send endpoint event — cannot POST without session_id.
            raise RuntimeError(
                "MCP SSE: no 'endpoint' event received within 10s. "
                "Cannot obtain session_id; POST would return 400."
            )

    async def _initialize(self) -> None:
        resp = await self._call({
            "method": "initialize",
            "params": {
                "protocolVersion": self.config.protocol_version,
                "capabilities": {},
                "clientInfo": self.config.client_info,
            },
        })
        logger.info(
            f"mcp.connected server={self.config.name} "
            f"info={resp.get('result', {}).get('serverInfo', {})}"
        )
        # Some servers expect the initialized notification after initialize.
        if self.config.transport == "stdio":
            if self._writer is not None:
                await self._notify("notifications/initialized", {})
        elif self.config.sse_mode == "stream":
            await self._notify("notifications/initialized", {})

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
        resp = await self.call_tool_raw(tool_name, arguments)
        if "error" in resp:
            return f"Error: {resp['error'].get('message', str(resp['error']))}"
        content = resp.get("result", {}).get("content", [])
        parts = [c.get("text", "") for c in content if c.get("type") == "text"]
        return "\n".join(parts) or "(empty response)"

    async def call_tool_raw(self, tool_name: str, arguments: dict) -> dict:
        resp = await self._call({
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
        })
        return resp

    async def _call(self, payload: dict) -> dict:
        req = {"jsonrpc": "2.0", "id": self._next_id(), **payload}
        if self.config.transport == "stdio":
            return await self._call_stdio(req)
        return await self._call_sse(req)

    async def _notify(self, method: str, params: dict | None = None) -> None:
        payload: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            payload["params"] = params
        if self.config.transport == "stdio":
            if self._writer is None:
                raise RuntimeError("stdio transport not connected")
            line = json.dumps(payload) + "\n"
            self._writer.write(line.encode())
            await self._writer.drain()
            return
        await self._notify_sse(payload)

    async def _call_stdio(self, req: dict) -> dict:
        if self._proc is None or self._writer is None or self._reader is None:
            raise RuntimeError("stdio transport not connected")
        line = json.dumps(req) + "\n"
        self._writer.write(line.encode())
        await self._writer.drain()
        raw = await asyncio.wait_for(self._reader.readline(), timeout=30)
        return json.loads(raw.decode().strip())

    async def _call_sse(self, req: dict) -> dict:
        if self.config.sse_mode == "stream":
            if self._sse_client is None or self._sse_message_queue is None or self._sse_endpoint is None:
                raise RuntimeError("sse stream not connected")
            headers = {"Content-Type": "application/json", **self.config.headers}
            url = self._with_session_id(self._sse_endpoint)
            headers = self._with_session_headers(headers)
            await self._post_jsonrpc(self._sse_client, url, req, headers)
            return await self._wait_jsonrpc_result(self._sse_message_queue, req["id"])
        return await self._call_sse_post(req)

    async def _call_sse_post(self, req: dict) -> dict:
        try:
            import httpx
        except ImportError:
            return {"error": {"message": "httpx not installed"}}
        path = self._resolve_sse_path("/messages")
        base_url = self.config.url.rstrip("/")
        url = self._build_url(base_url, path)
        headers = {"Content-Type": "application/json", **self.config.headers}
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(url, json=req, headers=headers)
            r.raise_for_status()
            return r.json()

    async def _notify_sse(self, payload: dict) -> None:
        if self.config.sse_mode != "stream":
            return
        if self._sse_client is None or self._sse_endpoint is None:
            raise RuntimeError("sse stream not connected")
        headers = {"Content-Type": "application/json", **self.config.headers}
        url = self._with_session_id(self._sse_endpoint)
        headers = self._with_session_headers(headers)
        await self._post_jsonrpc(self._sse_client, url, payload, headers)

    async def _consume_sse(
        self,
        sse_response: Any,
        endpoint_future: asyncio.Future[str],
        message_queue: asyncio.Queue[dict],
    ) -> None:
        event_type = "message"
        data_lines: list[str] = []

        async for line in sse_response.aiter_lines():
            if line is None:
                continue
            if line == "":
                if data_lines:
                    data = "\n".join(data_lines).strip()
                    if event_type == "endpoint" and data and not endpoint_future.done():
                        endpoint_future.set_result(data)
                    elif event_type == "message" and data:
                        try:
                            message_queue.put_nowait(json.loads(data))
                        except json.JSONDecodeError:
                            logger.debug("Ignored non-JSON SSE message: %s", data[:120])
                event_type = "message"
                data_lines = []
                continue

            if line.startswith(":"):
                continue
            if line.startswith("event:"):
                event_type = line[6:].strip()
                continue
            if line.startswith("data:"):
                data_lines.append(line[5:].lstrip())

    async def _wait_jsonrpc_result(
        self,
        message_queue: asyncio.Queue[dict],
        req_id: int,
        timeout: float = 20.0,
    ) -> dict:
        deadline = asyncio.get_event_loop().time() + timeout
        while True:
            remain = deadline - asyncio.get_event_loop().time()
            if remain <= 0:
                raise TimeoutError(f"Timeout waiting MCP response id={req_id}")
            msg = await asyncio.wait_for(message_queue.get(), timeout=remain)
            if msg.get("id") == req_id:
                return msg

    async def _post_jsonrpc(self, client: Any, url: str, payload: dict, headers: dict) -> None:
        resp = await client.post(url, json=payload, headers=headers)
        if resp.status_code not in (200, 202):
            raise RuntimeError(f"MCP POST failed ({resp.status_code}): {resp.text[:200]}")

    def _resolve_sse_path(self, default_path: str) -> str:
        return self.config.sse_path or default_path

    def _build_url(self, base_url: str, path: str) -> str:
        if path.startswith("http"):
            return path
        if not path.startswith("/"):
            path = "/" + path
        return f"{base_url}{path}"

    def _with_session_id(self, url: str) -> str:
        if not self._sse_session_id:
            return url
        try:
            from urllib.parse import urlparse, urlencode, parse_qsl, urlunparse
            parsed = urlparse(url)
            qs = dict(parse_qsl(parsed.query))
            if "session_id" not in qs:
                qs["session_id"] = self._sse_session_id
            new_query = urlencode(qs)
            return urlunparse(parsed._replace(query=new_query))
        except Exception:
            return url

    def _with_session_headers(self, headers: dict[str, str]) -> dict[str, str]:
        if not self._sse_session_id:
            return headers
        merged = dict(headers)
        merged.setdefault("X-Session-ID", self._sse_session_id)
        merged.setdefault("Session-Id", self._sse_session_id)
        merged.setdefault("session_id", self._sse_session_id)
        return merged

    def _extract_session_id_from_headers(self, headers: Any) -> str | None:
        try:
            for key in ("x-session-id", "session-id", "x-sessionid"):
                val = headers.get(key)
                if val:
                    return str(val)
        except Exception:
            return None
        return None

    def _parse_endpoint_data(self, data: str, base_url: str) -> tuple[str, str | None]:
        endpoint = data.strip()
        session_id: str | None = None

        # Try JSON payload
        try:
            decoded = json.loads(endpoint)
            if isinstance(decoded, dict):
                endpoint = decoded.get("endpoint") or decoded.get("url") or decoded.get("path") or endpoint
                session_id = decoded.get("session_id") or decoded.get("sid") or session_id
        except Exception:
            pass

        # Parse session_id from query if present
        try:
            from urllib.parse import urlparse, parse_qs
            parsed = urlparse(endpoint)
            qs = parse_qs(parsed.query)
            if qs.get("session_id"):
                session_id = qs.get("session_id", [None])[0] or session_id
        except Exception:
            pass

        if not endpoint.startswith("http"):
            endpoint = self._build_url(base_url, endpoint)

        return endpoint, session_id

    async def close(self) -> None:
        if self._sse_reader_task is not None:
            self._sse_reader_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._sse_reader_task
            self._sse_reader_task = None
        if self._sse_stream_cm is not None:
            with contextlib.suppress(Exception):
                await self._sse_stream_cm.__aexit__(None, None, None)
            self._sse_stream_cm = None
        if self._sse_client is not None:
            with contextlib.suppress(Exception):
                await self._sse_client.aclose()
            self._sse_client = None
        if self._proc is not None:
            try:
                self._proc.terminate()
                await asyncio.wait_for(self._proc.wait(), timeout=5)
            except Exception:  # nosec B110
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
