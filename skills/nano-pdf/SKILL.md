---
name: nano-pdf
description: "Edits PDFs using natural language instructions via the 'nano-pdf' CLI."
homepage: https://pypi.org/project/nano-pdf/
metadata:
  {
    "openclaw":
      {
        "emoji": "📄",
        "requires": { "bins": ["nano-pdf"] },
        "install":
          [
            {
              "id": "uv",
              "kind": "uv",
              "package": "nano-pdf",
              "bins": ["nano-pdf"],
              "label": "Install nano-pdf (uv)",
            },
          ],
      },
  }
---

# Nano PDF

This skill provides a unique way to edit PDF documents using natural language. Instead of complex commands or graphical interfaces, you can simply describe the changes you want to make.

## When to use
- Use this skill to make quick edits to a PDF, such as changing text or correcting typos.
- It is ideal for situations where you need to make a small change without opening a full-fledged PDF editor.
- You can specify the page number and provide a clear instruction for the desired modification.

## Usage

The `nano-pdf` skill is designed for simplicity. You provide the PDF file, the page number, and a description of the edit.

### Editing a Page

To edit a specific page in a PDF, use the `edit` command.

```bash
nano-pdf edit "my-document.pdf" 1 "Change the main heading to 'Project Proposal'"
```
