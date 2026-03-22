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
        return {"jsonrpc": "2.0", "result": {"protocolVersion": "2024-11-05", "serverInfo": {"name": "test"}}, "id": payload.get("id", 1)}
    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "result": {
                "tools": [
                    {"name": "read_file", "description": "Read a file", "inputSchema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}},
                ]
            },
            "id": payload.get("id", 1),
        }
    if method == "tools/call":
        return {"jsonrpc": "2.0", "result": {"content": [{"type": "text", "text": "file contents here"}]}, "id": payload.get("id", 1)}
    return {"jsonrpc": "2.0", "result": {}, "id": payload.get("id", 1)}


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
