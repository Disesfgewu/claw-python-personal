---
name: obsidian
description: "Works with Obsidian vaults and automates tasks using 'obsidian-cli'."
homepage: https://help.obsidian.md
metadata:
  {
    "openclaw":
      {
        "emoji": "💎",
        "requires": { "bins": ["obsidian-cli"] },
        "install":
          [
            {
              "id": "brew",
              "kind": "brew",
              "formula": "yakitrak/yakitrak/obsidian-cli",
              "bins": ["obsidian-cli"],
              "label": "Install obsidian-cli (brew)",
            },
          ],
      },
  }
---

# Obsidian

This skill provides a command-line interface to your Obsidian vaults, allowing you to manage your notes and automate your workflows. It uses the `obsidian-cli` tool to interact with your vault's Markdown files.

## When to use
- Use this skill to search for notes within your vault, either by title or by content.
- It is ideal for creating new notes, with the option to add content and open them in Obsidian.
- You can also move, rename, or delete notes, with the tool automatically updating any links.

## Usage

The `obsidian` skill simplifies the process of working with your notes from the command line.

### Searching for a Note

To find a note in your vault, you can use the `search` command.

```bash
obsidian-cli search "My Note Title"
```

To search within the content of your notes, use the `search-content` command.

```bash
obsidian-cli search-content "a specific phrase"
```

### Creating a Note

You can create a new note and add content to it with a single command.

```bash
obsidian-cli create "My New Note" --content "This is the initial content of the note."
```

### Moving a Note

To move a note to a different folder or rename it, use the `move` command. This will also update any links to the note.

```bash
obsidian-cli move "old/path/to/note.md" "new/path/to/note.md"
```
