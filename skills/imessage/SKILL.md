---
name: imessage
description: "Send and manage iMessages via available backend. Use when: user asks to send iMessage/SMS, read chat history, or list conversations. Prefer imsg on macOS direct install; use BlueBubbles when running on a remote server or non-darwin host. NOT for: group FaceTime, non-iMessage SMS on non-Apple platforms."
homepage: ""
metadata:
  openclaw:
    emoji: "💬"
    os: ["darwin"]
    requires:
      anyBins: ["imsg", "bluebubbles"]
---

# iMessage

This skill enables you to send and manage iMessages through different backend services. It is designed to integrate seamlessly with your existing messaging workflow, whether you're on a Mac or a remote server.

## When to use
- Use this skill when you need to send iMessages or SMS messages to your contacts.
- It is suitable for reading your chat history or listing all active conversations.
- You can choose between `imsg` for direct messaging on macOS and `BlueBubbles` for remote or non-macOS environments.

## Usage

The `imessage` skill supports two primary backends, each with its own advantages.

### `imsg` for macOS

If you are running on macOS, `imsg` is the preferred backend. It provides a direct interface to the Messages app, allowing for fast and reliable communication.

- **Send a message:**
  ```bash
  imsg "Hello, this is a test message." --to <contact-name>
  ```
- **List conversations:**
  ```bash
  imsg --list-chats
  ```
- **Read messages from a conversation:**
  ```bash
  imsg --read-chat <contact-name>
  ```

### `BlueBubbles` for Remote Servers

When you are on a remote server or a non-macOS host, `BlueBubbles` is the recommended backend. It connects to a BlueBubbles server to relay your messages.

- **Send a message:**
  ```bash
  bluebubbles --to <contact-name> --text "Hello from BlueBubbles!"
  ```
- **List conversations:**
  ```bash
  bluebubbles --list-conversations
  ```
- **Read messages from a conversation:**
  ```bash
  bluebubbles --read-conversation <conversation-id>
  ```
