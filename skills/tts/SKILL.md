---
name: tts
description: "Text-to-speech synthesis, local or cloud. Use when: converting text to audio output, reading content aloud, or generating voice narration. Prefer sherpa-onnx for offline/private use; use sag (ElevenLabs) when higher voice quality is needed and API key is available. NOT for: speech recognition (use openai-whisper instead)."
homepage: ""
metadata:
  openclaw:
    emoji: "🔊"
    os: ["darwin", "linux"]
    requires:
      anyBins: ["sag", "sherpa-onnx-tts"]
---

# Text-to-Speech

This skill provides text-to-speech synthesis capabilities through both local and cloud-based backends. It is designed for converting text into spoken audio, which can be used for reading content aloud or generating voice narrations.

## When to use
- Use this skill when you need to convert a piece of text into an audio file.
- It is ideal for situations where you want to listen to an article, document, or any other text-based content.
- You can choose between `sherpa-onnx` for local, offline processing and `sag` for high-quality voice synthesis via the ElevenLabs API.

## Usage

The `tts` skill supports two different backends, each tailored to specific needs.

### `sherpa-onnx` for Local Synthesis

For offline and private text-to-speech synthesis, `sherpa-onnx` is the recommended choice. It runs locally, ensuring that your data remains on your machine.

- **Synthesize text to a file:**
  ```bash
  sherpa-onnx-tts --text "Hello, this is a test." --output-file output.wav
  ```

### `sag` for Cloud-Based Synthesis

When high-quality voice output is a priority, `sag` (ElevenLabs) is the preferred backend. It uses the ElevenLabs API to generate lifelike speech, but it requires an API key.

- **Synthesize text using a specific voice:**
  ```bash
  sag --text "Hello, this is a high-quality voice." --voice "Bella" --output-file output.mp3
  ```
