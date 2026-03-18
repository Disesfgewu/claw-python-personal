---
name: gog
description: "A command-line interface for Google Workspace, supporting Gmail, Calendar, Drive, Contacts, Sheets, and Docs."
homepage: https://gogcli.sh
metadata:
  {
    "openclaw":
      {
        "emoji": "🎮",
        "requires": { "bins": ["gog"] },
        "install":
          [
            {
              "id": "brew",
              "kind": "brew",
              "formula": "steipete/tap/gogcli",
              "bins": ["gog"],
              "label": "Install gog (brew)",
            },
          ],
      },
  }
---

# Google Workspace CLI

This skill provides a command-line interface to various Google Workspace services, including Gmail, Google Calendar, and Google Drive. It allows you to manage your data and automate tasks without leaving the terminal.

## When to use
- Use this skill to send and search for emails in your Gmail account.
- It is ideal for managing your Google Calendar, including creating and listing events.
- You can also use it to interact with Google Drive, Sheets, and Docs for file management and data manipulation.

## Usage

The `gog` skill offers a wide range of commands for different Google Workspace services.

### Sending an Email

To send an email from your Gmail account, use the `gmail send` command.

```bash
gog gmail send --to "recipient@example.com" --subject "Hello from the CLI" --body "This is a test message."
```

### Listing Calendar Events

You can list your upcoming calendar events for a specific date range.

```bash
gog calendar events "primary" --from "2024-01-01T00:00:00Z" --to "2024-01-07T23:59:59Z"
```

### Searching Google Drive

To search for files in your Google Drive, use the `drive search` command.

```bash
gog drive search "name contains 'report'"
```
