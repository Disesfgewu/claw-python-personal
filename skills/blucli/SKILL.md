---
name: blucli
description: "A command-line interface for BluOS that handles discovery, playback, grouping, and volume control."
homepage: https://blucli.sh
metadata:
  {
    "openclaw":
      {
        "emoji": "🫐",
        "requires": { "bins": ["blu"] },
        "install":
          [
            {
              "id": "go",
              "kind": "go",
              "module": "github.com/steipete/blucli/cmd/blu@latest",
              "bins": ["blu"],
              "label": "Install blucli (go)",
            },
          ],
      },
  }
---

# BluOS CLI

This skill provides a command-line interface to control BluOS-enabled devices, such as those from Bluesound and NAD. It allows you to manage playback, adjust volume, and group speakers.

## When to use
- Use this skill to discover all BluOS devices on your network.
- It is ideal for controlling playback, including play, pause, and stop commands.
- You can also use it to manage speaker groups and adjust the volume of individual devices.

## Usage

The `blucli` skill uses the `blu` command to interact with your BluOS devices.

### Discovering Devices

To see a list of all available devices on your network, use the `devices` command.

```bash
blu devices
```

### Controlling Playback

Once you have selected a device, you can control its playback.

```bash
blu --device <device-id> play
blu --device <device-id> pause
```

### Adjusting Volume

You can set the volume of a device to a specific level.

```bash
blu --device <device-id> volume set 20
```
