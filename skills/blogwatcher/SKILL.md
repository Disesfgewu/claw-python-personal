---
name: blogwatcher
description: "Monitors blogs and RSS/Atom feeds for new posts using the 'blogwatcher' CLI."
homepage: https://github.com/Hyaxia/blogwatcher
metadata:
  {
    "openclaw":
      {
        "emoji": "📰",
        "requires": { "bins": ["blogwatcher"] },
        "install":
          [
            {
              "id": "go",
              "kind": "go",
              "module": "github.com/Hyaxia/blogwatcher/cmd/blogwatcher@latest",
              "bins": ["blogwatcher"],
              "label": "Install blogwatcher (go)",
            },
          ],
      },
  }
---

# Blog Watcher

This skill helps you keep track of your favorite blogs and news feeds by monitoring them for new content. It uses the `blogwatcher` command-line tool to manage your subscriptions and check for updates.

## When to use
- Use this skill to add new blogs or RSS/Atom feeds to your watch list.
- It is ideal for checking all your subscribed feeds at once to see if there are any new posts.
- You can also manage your reading list by marking articles as read or removing blogs you no longer follow.

## Usage

The `blogwatcher` skill provides a simple set of commands for managing your feeds.

### Adding a Blog

To start monitoring a new blog, use the `add` command.

```bash
blogwatcher add "My Favorite Blog" https://example-blog.com/feed
```

### Scanning for New Posts

To check for new articles across all your subscribed blogs, use the `scan` command.

```bash
blogwatcher scan
```

### Listing Articles

You can see a list of all the articles that have been fetched.

```bash
blogwatcher articles
```
