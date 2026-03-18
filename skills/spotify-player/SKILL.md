---
name: spotify-player
description: "Control Spotify playback and search from the terminal using spogo (preferred) or spotify_player. Use when asked to play, pause, skip, search tracks, or switch devices. Requires Spotify Premium."
homepage: https://www.spotify.com
metadata:
  {
    "openclaw":
      {
        "emoji": "🎵",
        "requires": { "anyBins": ["spogo", "spotify_player"] },
        "install":
          [
            {
              "id": "brew",
              "kind": "brew",
              "formula": "spogo",
              "tap": "steipete/tap",
              "bins": ["spogo"],
              "label": "Install spogo (brew)",
            },
            {
              "id": "brew",
              "kind": "brew",
              "formula": "spotify_player",
              "bins": ["spotify_player"],
              "label": "Install spotify_player (brew)",
            },
          ],
      },
  }
---

# Spotify Player

Control Spotify from the terminal. Use `spogo` when available; fall back to `spotify_player`.

**Requires:** Spotify Premium account.

## spogo (preferred)

Auth setup:

```bash
spogo auth import --browser chrome
Common commands:


spogo search track "query"
spogo play
spogo pause
spogo next
spogo prev
spogo status
spogo device list
spogo device set "<name or id>"
spotify_player (fallback)

spotify_player search "query"
spotify_player playback play
spotify_player playback pause
spotify_player playback next
spotify_player playback previous
spotify_player connect
spotify_player like
Notes
Config location: ~/.config/spotify-player/app.toml.
For Spotify Connect, set client_id in the config file.
spogo uses browser cookie auth; spotify_player uses the Spotify Web API.


---
