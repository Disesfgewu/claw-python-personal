---
name: openhue
description: "Controls Philips Hue lights and scenes via the OpenHue CLI."
homepage: https://www.openhue.io/cli
metadata:
  {
    "openclaw":
      {
        "emoji": "💡",
        "requires": { "bins": ["openhue"] },
        "install":
          [
            {
              "id": "brew",
              "kind": "brew",
              "formula": "openhue/cli/openhue-cli",
              "bins": ["openhue"],
              "label": "Install OpenHue CLI (brew)",
            },
          ],
      },
  }
---

# OpenHue CLI

This skill provides a command-line interface for controlling your Philips Hue smart lights. It allows you to manage individual lights, rooms, and scenes directly from your terminal.

## When to use
- Use this skill to turn your lights on or off, and to adjust their brightness.
- It is ideal for changing the color or color temperature of your lights to create the perfect ambiance.
- You can also activate pre-configured scenes for a specific room or zone.

## Usage

The `openhue` skill offers a variety of commands for managing your Philips Hue lighting system.

### Controlling a Light

You can control a single light by its name.

```bash
# Turn a light on
openhue set light "Living Room Lamp" --on

# Set the brightness
openhue set light "Living Room Lamp" --on --brightness 75

# Set the color
openhue set light "Living Room Lamp" --on --color blue
```

### Controlling a Room

You can also control all the lights in a room at once.

```bash
# Turn off all lights in a room
openhue set room "Bedroom" --off

# Set the brightness for a room
openhue set room "Bedroom" --on --brightness 50
```

### Activating a Scene

To activate a scene, you need to specify both the scene name and the room.

```bash
openhue set scene "Movie Time" --room "Living Room"
```
