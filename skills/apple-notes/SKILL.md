---
name: apple-notes
description: "Manages Apple Notes on macOS using the 'memo' CLI. Handles note creation, viewing, editing, and organization."
homepage: https://github.com/antoniorodr/memo
metadata:
  {
    "openclaw":
      {
        "emoji": "📝",
        "os": ["darwin"],
        "requires": { "bins": ["memo"] },
        "install":
          [
            {
              "id": "brew",
              "kind": "brew",
              "formula": "antoniorodr/memo/memo",
              "bins": ["memo"],
              "label": "Install memo via Homebrew",
            },
          ],
      },
  }
---

# Apple Notes

This skill allows you to interact with Apple Notes from the command line. It provides a convenient way to manage your notes without leaving the terminal.

## When to use
- Use this skill to create new notes, either with a predefined title or through an interactive editor.
- It is suitable for viewing and searching your existing notes, with options to filter by folder.
- You can also edit, delete, and move notes between different folders.

## Usage

The `apple-notes` skill uses the `memo` command-line tool to interact with Apple Notes.

### Creating a Note

You can create a new note in a couple of ways.

- **Interactive creation:**
  ```bash
  memo notes -a
  ```
- **With a title:**
  ```bash
  memo notes -a "My New Note"
  ```

### Viewing and Searching

Listing and finding your notes is simple.

- **List all notes:**
  ```bash
  memo notes
  ```
- **Search for a note:**
  ```bash
  memo notes -s "search term"
  ```

### Editing a Note

To edit an existing note, you can use the following command, which will open an interactive selection prompt.

```bash
memo notes -e
```
