---
name: slack
description: "Send and manage Slack messages, reactions, and pins via the slack tool. Use when: sending messages to channels or users, reacting to messages, pinning/unpinning items, reading recent messages, or fetching member info. NOT for: creating channels or workspace administration."
metadata: { "openclaw": { "emoji": "💬", "requires": { "config": ["channels.slack"] } } }
---

# Slack

Use the `slack` tool to interact with Slack channels and DMs.

## Required inputs

- `channelId` — Slack channel ID (e.g. `C123`)
- `messageId` — message timestamp (e.g. `1712023032.1234`)
- For reactions: `emoji` (Unicode or `:name:`)
- For sending: `to` as `channel:<id>` or `user:<id>`, plus `content`

Message context lines include `slack message id` and `channel` fields you can reuse directly.

## Actions

### Send a message

```json
{ "action": "sendMessage", "to": "channel:C123", "content": "Hello!" }
React to a message

{ "action": "react", "channelId": "C123", "messageId": "1712023032.1234", "emoji": "✅" }
List reactions on a message

{ "action": "reactions", "channelId": "C123", "messageId": "1712023032.1234" }
Read recent messages

{ "action": "readMessages", "channelId": "C123", "limit": 20 }
Edit a message

{ "action": "editMessage", "channelId": "C123", "messageId": "1712023032.1234", "content": "Updated text" }
Delete a message

{ "action": "deleteMessage", "channelId": "C123", "messageId": "1712023032.1234" }
Pin / unpin / list pins

{ "action": "pinMessage",   "channelId": "C123", "messageId": "1712023032.1234" }
{ "action": "unpinMessage", "channelId": "C123", "messageId": "1712023032.1234" }
{ "action": "listPins",     "channelId": "C123" }
Member info

{ "action": "memberInfo", "userId": "U123" }
Custom emoji list

{ "action": "emojiList" }


---
