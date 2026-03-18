---
name: search
description: "Search the web via DDGS through LLM-Router. Use when: (1) user asks about current events or recent news, (2) looking up factual information that may have changed after training cutoff, (3) finding URLs, documentation, or reference pages, (4) researching a topic that needs up-to-date sources. NOT for: questions answerable from training data alone, code generation, math, or reasoning tasks that don't require live information."
homepage: ""
metadata:
  openclaw:
    emoji: "🔍"
    requires: {}
    install: []
---

# Web Search

Use the `search_web` tool to retrieve live results from the web via DDGS.

## When to search

- User explicitly asks to search or look something up
- Question involves current events, prices, software versions, or anything time-sensitive
- You are unsure whether your training data is recent enough to answer reliably

## How to use

Call `search_web` with a concise, specific query. Prefer precise queries over broad ones.

Good: `search_web("Python 3.13 release date")`
Bad: `search_web("python")`

## Citing sources

Always cite your sources. For each fact drawn from search results, include the title and URL:

> According to **Title** (url): ...

If multiple results contradict each other, note the discrepancy and prefer the most authoritative or recent source.
