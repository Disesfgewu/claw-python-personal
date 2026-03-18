---
name: camsnap
description: "Captures frames or clips from RTSP/ONVIF cameras using the 'camsnap' CLI."
homepage: https://camsnap.ai
metadata:
  {
    "openclaw":
      {
        "emoji": "📸",
        "requires": { "bins": ["camsnap"] },
        "install":
          [
            {
              "id": "brew",
              "kind": "brew",
              "formula": "steipete/tap/camsnap",
              "bins": ["camsnap"],
              "label": "Install camsnap (brew)",
            },
          ],
      },
  }
---

# Camera Snapshot

This skill allows you to capture snapshots and video clips from network cameras that support RTSP or ONVIF protocols. It uses the `camsnap` command-line tool to interact with your cameras.

## When to use
- Use this skill to take a still image from a camera and save it to a file.
- It is ideal for recording short video clips from a camera, with a specified duration.
- You can also discover cameras on your network and add them to your configuration.

## Usage

The `camsnap` skill provides a simple way to interact with your network cameras.

### Taking a Snapshot

To capture a single frame from a camera, use the `snap` command.

```bash
camsnap snap <camera-name> --out snapshot.jpg
```

### Recording a Clip

To record a short video clip, use the `clip` command and specify the duration.

```bash
camsnap clip <camera-name> --dur 10s --out video.mp4
```

### Discovering Cameras

To find cameras on your network, you can use the `discover` command.

```bash
camsnap discover
```
