---
name: mcporter
description: "A command-line interface for interacting with MCP servers and tools. It supports listing, configuring, and calling tools."
homepage: http://mcporter.dev
metadata:
  {
    "openclaw":
      {
        "emoji": "📦",
        "requires": { "bins": ["mcporter"] },
        "install":
          [
            {
              "id": "node",
              "kind": "node",
              "package": "mcporter",
              "bins": ["mcporter"],
              "label": "Install mcporter (node)",
            },
          ],
      },
  }
---

# MCPorter

This skill provides a command-line interface for interacting with MCP (Meta-Call Protocol) servers. It allows you to discover, configure, and call tools exposed by these servers.

## When to use
- Use this skill to list all available tools on an MCP server.
- It is ideal for calling a specific tool with a set of arguments.
- You can also manage your authentication and configuration for different MCP servers.

## Usage

The `mcporter` skill provides a straightforward way to work with MCP servers.

### Listing Tools

To see a list of all tools available on a server, use the `list` command.

```bash
mcporter list <server-name>
```

### Calling a Tool

To execute a tool, use the `call` command, followed by the tool's name and any required arguments.

```bash
mcporter call <server-name>.<tool-name> argument1=value1
```

### Authentication

For servers that require authentication, you can use the `auth` command to log in.

```bash
mcporter auth <server-name>
```
