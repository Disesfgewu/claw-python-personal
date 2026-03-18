---
name: apple-reminders
description: "Manages Apple Reminders using the 'remindctl' CLI. Handles listing, adding, editing, and completing reminders."
homepage: https://github.com/steipete/remindctl
metadata:
  {
    "openclaw":
      {
        "emoji": "⏰",
        "os": ["darwin"],
        "requires": { "bins": ["remindctl"] },
        "install":
          [
            {
              "id": "brew",
              "kind": "brew",
              "formula": "steipete/tap/remindctl",
              "bins": ["remindctl"],
              "label": "Install remindctl via Homebrew",
            },
          ],
      },
  }
---

# Apple Reminders

This skill provides a command-line interface to Apple Reminders, allowing you to manage your tasks and to-do lists directly from the terminal.

## When to use
- Use this skill to add new reminders to your lists, optionally with due dates.
- It is suitable for viewing your reminders, with options to filter by date or list.
- You can also mark reminders as complete or delete them when they are no longer needed.

## Usage

The `apple-reminders` skill uses the `remindctl` command-line tool to interact with the Reminders app.

### Adding a Reminder

You can add a new reminder with a title and an optional due date.

```bash
remindctl add "Buy groceries" --due today
```

### Viewing Reminders

Listing your reminders is simple, with several filtering options available.

- **View today's reminders:**
  ```bash
  remindctl today
  ```
- **View all reminders:**
  ```bash
  remindctl all
  ```

### Completing a Reminder

Once you have completed a task, you can mark it as done using its ID.

```bash
remindctl complete <reminder-id>
```
