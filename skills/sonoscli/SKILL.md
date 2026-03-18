---
name: sonoscli
description: "Control Sonos speakers on the local network via the 'sonos' CLI. Use when asked to play/pause/stop music, adjust volume, group speakers, open favorites, or manage the queue."
homepage: https://sonoscli.sh
metadata:
  {
    "openclaw":
      {
        "emoji": "🔊",
        "requires": { "bins": ["sonos"] },
        "install":
          [
            {
              "id": "go",
              "kind": "go",
              "module": "github.com/steipete/sonoscli/cmd/sonos@latest",
              "bins": ["sonos"],
              "label": "Install sonoscli (go)",
            },
          ],
      },
  }
---

# Sonos CLI

Control Sonos speakers on the local network with the `sonos` command.

## Quick start

```bash
sonos discover
sonos status --name "Kitchen"
sonos play   --name "Kitchen"
sonos pause  --name "Kitchen"
sonos volume set 15 --name "Kitchen"
Common tasks

# Grouping
sonos group status
sonos group join   --name "Bedroom" --to "Kitchen"
sonos group unjoin --name "Bedroom"
sonos group party   # all speakers join
sonos group solo --name "Kitchen"

# Favorites
sonos favorites list
sonos favorites open "Chill Mix"

# Queue
sonos queue list
sonos queue play
sonos queue clear

# Spotify search via SMAPI
sonos smapi search --service "Spotify" --category tracks "query"
Troubleshooting
no route to host on sonos discover
SSDP multicast is blocked. On macOS, grant Local Network access to the parent process (Terminal, VS Code, etc.) in System Settings → Privacy & Security. Alternatively, pass --ip <speaker-ip> to skip discovery.

bind: operation not permitted
The process is running inside a sandbox that blocks UDP. Either run outside the sandbox or enable network access for it.

Notes
Spotify SMAPI search optionally uses SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET.
If SSDP discovery fails, use --ip <speaker-ip> to target a specific speaker directly.


---
