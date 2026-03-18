---
name: songsee
description: "Generate spectrograms and audio feature visualizations from audio files using the songsee CLI. Use when asked to visualize audio, generate a spectrogram, or inspect frequency/rhythm features of a track."
homepage: https://github.com/steipete/songsee
metadata:
  {
    "openclaw":
      {
        "emoji": "🌊",
        "requires": { "bins": ["songsee"] },
        "install":
          [
            {
              "id": "brew",
              "kind": "brew",
              "formula": "steipete/tap/songsee",
              "bins": ["songsee"],
              "label": "Install songsee (brew)",
            },
          ],
      },
  }
---

# songsee

Generate spectrograms and multi-panel audio feature visualizations.

## Basic usage

```bash
# Single spectrogram
songsee track.mp3

# Multi-panel (all features)
songsee track.mp3 --viz spectrogram,mel,chroma,hpss,selfsim,loudness,tempogram,mfcc,flux

# Time slice
songsee track.mp3 --start 12.5 --duration 8 -o slice.jpg

# From stdin
cat track.mp3 | songsee - --format png -o out.png
Key flags
Flag	Description
--viz	Comma-separated list of visualizations to render
--style	Color palette: classic, magma, inferno, viridis, gray
--width / --height	Output image dimensions
--window / --hop	FFT window and hop size
--min-freq / --max-freq	Frequency range
--start / --duration	Time slice
--format	jpg or png
Notes
WAV and MP3 decode natively; other formats require ffmpeg.
Multiple --viz entries render as a grid layout.


---
