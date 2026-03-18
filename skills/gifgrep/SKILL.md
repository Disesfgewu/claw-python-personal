---
name: gifgrep
description: "Searches GIF providers, downloads results, and extracts stills or sheets using the 'gifgrep' CLI."
homepage: https://gifgrep.com
metadata:
  {
    "openclaw":
      {
        "emoji": "🧲",
        "requires": { "bins": ["gifgrep"] },
        "install":
          [
            {
              "id": "brew",
              "kind": "brew",
              "formula": "steipete/tap/gifgrep",
              "bins": ["gifgrep"],
              "label": "Install gifgrep (brew)",
            },
            {
              "id": "go",
              "kind": "go",
              "module": "github.com/steipete/gifgrep/cmd/gifgrep@latest",
              "bins": ["gifgrep"],
              "label": "Install gifgrep (go)",
            },
          ],
      },
  }
---

# GIF Grep

This skill provides a command-line interface for searching, downloading, and manipulating GIFs. It allows you to find GIFs from various providers and process them for different uses.

## When to use
- Use this skill to search for GIFs on platforms like Tenor and Giphy.
- It is ideal for downloading your favorite GIFs and saving them locally.
- You can also extract still frames or create sprite sheets from a GIF, which is useful for analysis or sharing.

## Usage

The `gifgrep` skill offers a range of commands for working with GIFs.

### Searching for a GIF

To find a GIF, use the `search` command with a query.

```bash
gifgrep search "happy cat"
```

### Downloading a GIF

Once you have found a GIF you like, you can download it.

```bash
gifgrep "happy cat" --download --max 1
```

### Extracting a Still Frame

You can extract a single frame from a GIF at a specific timestamp.

```bash
gifgrep still ./my-cat.gif --at 2.5s -o frame.png
```
