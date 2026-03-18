---
name: discord
description: "Handles Discord operations, such as sending messages, using the 'message' tool."
metadata: { "openclaw": { "emoji": "🎮", "requires": { "config": ["channels.discord.token"] } } }
allowed-tools: ["message"]
---

# Discord

This skill provides the ability to interact with Discord, allowing you to send messages, react to posts, and manage conversations. It is designed to be used with the `message` tool, which acts as a gateway to the Discord API.

## When to use
- Use this skill to send messages to a specific Discord channel or user.
- It is ideal for creating rich messages with embeds or other components.
- You can also use it to react to messages, create threads, and search for content within a server.

## Usage

All Discord operations are performed through the `message` tool. You will need to specify `discord` as the channel.

### Sending a Message

To send a simple text message to a Discord channel, you can use the `send` action.

```json
{
  "action": "send",
  "channel": "discord",
  "to": "channel:1234567890",
  "message": "Hello, from the command line!"
}
```

### Reacting to a Message

You can react to an existing message using the `react` action.

```json
{
  "action": "react",
  "channel": "discord",
  "channelId": "1234567890",
  "messageId": "0987654321",
  "emoji": "👍"
}
```

### Reading Channel History

To read the most recent messages from a channel, use the `read` action.

```json
{
  "action": "read",
  "channel": "discord",
  "to": "channel:1234567890",
  "limit": 10
}
```
