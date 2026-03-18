---
name: gemini
description: "A command-line interface for Gemini, used for one-shot Q&A, summaries, and content generation."
homepage: https://ai.google.dev/
metadata:
  {
    "openclaw":
      {
        "emoji": "✨",
        "requires": { "bins": ["gemini"] },
        "install":
          [
            {
              "id": "brew",
              "kind": "brew",
              "formula": "gemini-cli",
              "bins": ["gemini"],
              "label": "Install Gemini CLI (brew)",
            },
          ],
      },
  }
---

# Gemini CLI

This skill provides a command-line interface to the Gemini family of models. It is designed for quick, one-shot interactions, such as asking questions, summarizing text, or generating creative content.

## When to use
- Use this skill to get quick answers to questions on a wide range of topics.
- It is ideal for summarizing articles, documents, or other pieces of text.
- You can also use it to generate code, write stories, or perform other creative tasks.

## Usage

The `gemini` skill is simple to use, with a focus on single-shot commands.

### Asking a Question

To ask a question, simply provide it as a string to the `gemini` command.

```bash
gemini "What is the capital of France?"
```

### Specifying a Model

You can choose a specific Gemini model to use for your query.

```bash
gemini --model gemini-pro "Translate 'hello' to Spanish"
```

### Getting JSON Output

For scripting and automation, you can request the output in JSON format.

```bash
gemini --output-format json "List three benefits of using a command-line interface."
```
