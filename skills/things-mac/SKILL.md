---
name: things-mac
description: "Manage Things 3 on macOS via the 'things' CLI. Use when asked to add tasks, list inbox/today/upcoming, search todos, or inspect projects/areas/tags. Supports read (DB) and write (URL scheme) operations. macOS only."
homepage: https://github.com/ossianhempel/things3-cli
metadata:
  {
    "openclaw":
      {
        "emoji": "✅",
        "os": ["darwin"],
        "requires": { "bins": ["things"] },
        "install":
          [
            {
              "id": "go",
              "kind": "go",
              "module": "github.com/ossianhempel/things3-cli/cmd/things@latest",
              "bins": ["things"],
              "label": "Install things3-cli (go)",
            },
          ],
      },
  }
---

# Things 3 CLI

Read your Things database and write todos via the Things URL scheme.

## Setup

Install: `GOBIN=/opt/homebrew/bin go install github.com/ossianhempel/things3-cli/cmd/things@latest`

If DB reads fail, grant **Full Disk Access** to the calling process in System Settings → Privacy & Security.

Optional env vars:
- `THINGSDB` — path to your `ThingsData-*` folder
- `THINGS_AUTH_TOKEN` — skip passing `--auth-token` on update commands

## Read (database)

```bash
things inbox --limit 50
things today
things upcoming
things search "query"
things projects
things areas
things tags
Write (URL scheme)

# Preview without executing
things --dry-run add "Title"

# Add a todo
things add "Buy milk"
things add "Buy milk" --notes "2% + bananas"
things add "Book flights" --list "Travel"
things add "Pack charger" --list "Travel" --heading "Before"
things add "Call dentist" --tags "health,phone"
things add "Trip prep" --checklist-item "Passport" --checklist-item "Tickets"

# Multi-line from stdin (first line = title, rest = notes)
printf "Title\nLine 1\nLine 2\n" | things add -
Update (requires auth token)

# Find the UUID first
things search "milk" --limit 5

# Update fields
things update --id <UUID> --auth-token <TOKEN> "New title"
things update --id <UUID> --auth-token <TOKEN> --notes "Replacement notes"
things update --id <UUID> --auth-token <TOKEN> --append-notes "Extra line"
things update --id <UUID> --auth-token <TOKEN> --list "Travel" --heading "Before"
things update --id <UUID> --auth-token <TOKEN> --tags "a,b"
things update --id <UUID> --auth-token <TOKEN> --completed
things update --id <UUID> --auth-token <TOKEN> --canceled
Notes
--dry-run prints the URL without opening Things.
Deletion is not supported by the CLI; use Things UI or mark as completed/canceled.


---
