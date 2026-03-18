---
name: bear-notes
description: "Creates, searches, and manages notes in Bear via the 'grizzly' CLI."
homepage: https://bear.app
metadata:
  {
    "openclaw":
      {
        "emoji": "🐻",
        "os": ["darwin"],
        "requires": { "bins": ["grizzly"] },
        "install":
          [
            {
              "id": "go",
              "kind": "go",
              "module": "github.com/tylerwince/grizzly/cmd/grizzly@latest",
              "bins": ["grizzly"],
              "label": "Install grizzly (go)",
            },
          ],
      },
  }
---

# Bear Notes

This skill allows you to manage your notes in Bear, a popular note-taking app for macOS. It uses the `grizzly` command-line tool to provide a programmatic interface to your notes.

## When to use
- Use this skill to create new notes, complete with titles and tags.
- It is suitable for searching and retrieving your existing notes by their ID or tags.
- You can also append text to your notes, making it easy to update them from the command line.

## Usage

The `bear-notes` skill leverages the `grizzly` CLI to perform various actions in Bear.

### Creating a Note

You can create a new note by piping content to the `grizzly create` command.

```bash
echo "This is the content of my new note." | grizzly create --title "My Note Title" --tag "work"
```

### Opening a Note

To open a specific note, you will need its unique ID.

```bash
grizzly open-note --id "NOTE_ID"
```

### Appending to a Note

You can add more content to an existing note using the `add-text` command.

```bash
echo "This is additional text." | grizzly add-text --id "NOTE_ID" --mode append
```
