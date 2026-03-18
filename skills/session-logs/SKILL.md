---
name: session-logs
description: "Searches and analyzes your session logs to retrieve information from past conversations."
metadata: { "openclaw": { "emoji": "📜", "requires": { "bins": ["jq", "rg"] } } }
---

# Session Logs

This skill allows you to search and analyze your conversation history, which is stored in local JSONL files. It is useful when you need to recall information from previous sessions or understand the context of a long-running conversation.

## When to use
- Use this skill to find specific information that was mentioned in a previous conversation.
- It is ideal for analyzing your usage patterns, such as which tools you use most frequently or how much you are spending on different models.
- You can also use it to get a summary of a session, including the number of messages and the total cost.

## Usage

The `session-logs` skill uses command-line tools like `jq` and `rg` to query your session logs. The logs are located in `~/.claw/agents/<agentId>/sessions/`.

### Searching for a Keyword

To search for a keyword across all your session logs, you can use `rg`.

```bash
rg "my-keyword" ~/.claw/agents/<agentId>/sessions/*.jsonl
```

### Extracting User Messages

You can use `jq` to extract all the messages you have sent in a specific session.

```bash
jq -r 'select(.message.role == "user") | .message.content[]? | select(.type == "text") | .text' <session-id>.jsonl
```

### Calculating Session Cost

To calculate the total cost of a session, you can sum up the cost of each message.

```bash
jq -s '[.[] | .message.usage.cost.total // 0] | add' <session-id>.jsonl
```
