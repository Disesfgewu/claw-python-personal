---
name: wacli
description: "Send WhatsApp messages to other people or search/sync WhatsApp history via the wacli CLI. Use only when the user explicitly asks to message a third party on WhatsApp or to search message history. NOT for: routine user conversations (those are handled automatically)."
homepage: https://wacli.sh
metadata:
  {
    "openclaw":
      {
        "emoji": "📱",
        "requires": { "bins": ["wacli"] },
        "install":
          [
            {
              "id": "brew",
              "kind": "brew",
              "formula": "steipete/tap/wacli",
              "bins": ["wacli"],
              "label": "Install wacli (brew)",
            },
            {
              "id": "go",
              "kind": "go",
              "module": "github.com/steipete/wacli/cmd/wacli@latest",
              "bins": ["wacli"],
              "label": "Install wacli (go)",
            },
          ],
      },
  }
---

# wacli

Use `wacli` only when the user explicitly asks to message someone else on WhatsApp, or to sync or search WhatsApp history. Do not use it for normal user conversations.

**Before sending:** always confirm the recipient and message content with the user.

## Auth and sync

```bash
wacli auth              # QR login + initial sync
wacli sync --follow     # continuous sync
wacli doctor            # connection diagnostics
Find chats and messages

wacli chats list --limit 20 --query "name or number"
wacli messages search "query" --limit 20 --chat <jid>
wacli messages search "invoice" --after 2025-01-01 --before 2025-12-31
History backfill

wacli history backfill --chat <jid> --requests 2 --count 50
Send

# Text to a phone number
wacli send text --to "+14155551212" --message "Hello! Are you free at 3pm?"

# Text to a group (JID format)
wacli send text --to "1234567890-123456789@g.us" --message "Running 5 min late."

# File with caption
wacli send file --to "+14155551212" --file /path/agenda.pdf --caption "Agenda"
Notes
Store directory: ~/.wacli (override with --store).
Add --json for machine-readable output.
JIDs: direct chats = <number>@s.whatsapp.net; groups = <id>@g.us.
History backfill requires the phone to be online; results are best-effort.


---
