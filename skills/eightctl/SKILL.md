---
name: eightctl
description: "Controls Eight Sleep pods, allowing you to manage status, temperature, alarms, and schedules."
homepage: https://eightctl.sh
metadata:
  {
    "openclaw":
      {
        "emoji": "🛌",
        "requires": { "bins": ["eightctl"] },
        "install":
          [
            {
              "id": "go",
              "kind": "go",
              "module": "github.com/steipete/eightctl/cmd/eightctl@latest",
              "bins": ["eightctl"],
              "label": "Install eightctl (go)",
            },
          ],
      },
  }
---

# Eight Sleep Control

This skill provides a command-line interface for controlling your Eight Sleep pod. It allows you to manage the pod's temperature, alarms, and schedules directly from your terminal.

## When to use
- Use this skill to check the current status of your pod, including its temperature and other metrics.
- It is ideal for turning the pod on or off, as well as setting a target temperature.
- You can also manage your alarms and schedules, making it a convenient way to automate your sleep routine.

## Usage

The `eightctl` skill provides a set of commands for interacting with your Eight Sleep pod.

### Checking Status

To get the current status of your pod, use the `status` command.

```bash
eightctl status
```

### Turning the Pod On or Off

You can easily turn the pod on or off.

```bash
eightctl on
eightctl off
```

### Setting the Temperature

To set a new target temperature for your pod, use the `temp` command.

```bash
eightctl temp 25
```
