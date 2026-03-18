---
name: openai-whisper
description: "Performs local speech-to-text transcription using the Whisper CLI."
homepage: https://openai.com/research/whisper
metadata:
  {
    "openclaw":
      {
        "emoji": "🎤",
        "requires": { "bins": ["whisper"] },
        "install":
          [
            {
              "id": "brew",
              "kind": "brew",
              "formula": "openai-whisper",
              "bins": ["whisper"],
              "label": "Install OpenAI Whisper (brew)",
            },
          ],
      },
  }
---

# Whisper CLI

This skill provides local speech-to-text transcription capabilities using the Whisper command-line tool. It allows you to convert audio files into written text without needing an internet connection or API key.

## When to use
- Use this skill to transcribe audio from a variety of formats, such as MP3, M4A, and WAV.
- It is ideal for situations where you need to quickly get a text version of a spoken recording.
- You can also use it to translate spoken audio from another language into English.

## Usage

The `openai-whisper` skill is straightforward to use. You provide an audio file and specify the desired output format.

### Transcribing an Audio File

To transcribe an audio file, use the `whisper` command, followed by the path to the file.

```bash
whisper audio.mp3 --model medium --output_format txt
```

### Translating an Audio File

To translate a foreign language audio file into English, use the `translate` task.

```bash
whisper audio.m4a --task translate
```
