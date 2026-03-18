---
name: summarize
description: "Summarize or extract text from URLs, YouTube videos, podcasts, and local files using the summarize CLI. Use when asked to summarize a link or article, transcribe a YouTube video, or extract text from a file. Good fallback when no other transcription tool is available."
homepage: https://summarize.sh
metadata:
  {
    "openclaw":
      {
        "emoji": "🧾",
        "requires": { "bins": ["summarize"] },
        "install":
          [
            {
              "id": "brew",
              "kind": "brew",
              "formula": "steipete/tap/summarize",
              "bins": ["summarize"],
              "label": "Install summarize (brew)",
            },
          ],
      },
  }
---

# Summarize

Extract and summarize content from URLs, YouTube links, and local files.

## Quick start

```bash
summarize "https://example.com"
summarize "/path/to/file.pdf"
summarize "https://youtu.be/dQw4w9WgXcQ" --youtube auto
YouTube: transcript vs summary

# Best-effort transcript extraction (no yt-dlp required)
summarize "https://youtu.be/dQw4w9WgXcQ" --youtube auto --extract-only
If the transcript is very long, return a tight summary first and ask the user which section to expand.

Useful flags
Flag	Description
--length	short / medium / long / xl / xxl / <chars>
--extract-only	Return raw extracted text, no LLM summary (URLs only)
--json	Machine-readable output
--youtube auto	Enable Apify fallback if APIFY_API_TOKEN is set
--firecrawl	auto / off / always (fallback for blocked sites)
--max-output-tokens	Limit output token count
API keys
The default model is google/gemini-3-flash-preview. Set the key for your chosen provider:

Google: GEMINI_API_KEY
OpenAI: OPENAI_API_KEY
Anthropic: ANTHROPIC_API_KEY
xAI: XAI_API_KEY
Optional services: FIRECRAWL_API_KEY (blocked sites), APIFY_API_TOKEN (YouTube fallback).

Config
Optional ~/.summarize/config.json:


{ "model": "openai/gpt-4o" }


---
