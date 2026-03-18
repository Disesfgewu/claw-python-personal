---
name: peekaboo
description: "A command-line tool for capturing and automating the macOS user interface."
homepage: https://peekaboo.boo
metadata:
  {
    "openclaw":
      {
        "emoji": "👀",
        "os": ["darwin"],
        "requires": { "bins": ["peekaboo"] },
        "install":
          [
            {
              "id": "brew",
              "kind": "brew",
              "formula": "steipete/tap/peekaboo",
              "bins": ["peekaboo"],
              "label": "Install Peekaboo (brew)",
            },
          ],
      },
  }
---

# Peekaboo

This skill provides a powerful command-line interface for automating the macOS user interface. It allows you to capture screenshots, inspect UI elements, and simulate user input, making it an essential tool for UI testing and automation.

## When to use
- Use this skill to capture screenshots of your screen, a specific window, or a region.
- It is ideal for inspecting the UI to identify elements and their properties.
- You can also use it to simulate user actions, such as clicking, typing, and scrolling.

## Usage

The `peekaboo` skill offers a wide range of commands for UI automation.

### Capturing a Screenshot

To take a screenshot of the entire screen, use the `image` command.

```bash
peekaboo image --mode screen --path screenshot.png
```

### Inspecting the UI

To get a visual representation of the UI elements on the screen, use the `see` command.

```bash
peekaboo see --annotate --path ui-map.png
```

### Simulating a Click

Once you have identified a UI element, you can simulate a click on it.

```bash
peekaboo click --on <element-id>
```

### Simulating Typing

You can also simulate typing text into a focused input field.

```bash
peekaboo type "Hello, world!" --return
```
