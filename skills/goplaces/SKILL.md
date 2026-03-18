---
name: goplaces
description: "Queries the Google Places API via the 'goplaces' CLI for text search, place details, and reviews."
homepage: https://github.com/steipete/goplaces
metadata:
  {
    "openclaw":
      {
        "emoji": "📍",
        "requires": { "bins": ["goplaces"], "env": ["GOOGLE_PLACES_API_KEY"] },
        "primaryEnv": "GOOGLE_PLACES_API_KEY",
        "install":
          [
            {
              "id": "brew",
              "kind": "brew",
              "formula": "steipete/tap/goplaces",
              "bins": ["goplaces"],
              "label": "Install goplaces (brew)",
            },
          ],
      },
  }
---

# Google Places

This skill provides a command-line interface to the Google Places API, allowing you to search for places, get details about them, and read reviews.

## When to use
- Use this skill to find places based on a text query, such as "coffee shops near me."
- It is ideal for getting detailed information about a specific place, including its address, phone number, and user reviews.
- You can also use it to resolve place names to geographic coordinates.

## Usage

The `goplaces` skill offers a variety of commands for interacting with the Google Places API.

### Searching for Places

To search for places, use the `search` command with a query. You can also add filters to narrow down the results.

```bash
goplaces search "restaurants in New York" --open-now --min-rating 4.0
```

### Getting Place Details

Once you have a place ID, you can get more detailed information about it.

```bash
goplaces details <place-id> --reviews
```

### Resolving a Place

To convert a place name or address into coordinates, use the `resolve` command.

```bash
goplaces resolve "Eiffel Tower, Paris"
```
