---
name: notion
description: "Provides access to the Notion API for creating and managing pages, databases, and blocks."
homepage: https://developers.notion.com
metadata:
  {
    "openclaw":
      { "emoji": "📝", "requires": { "env": ["NOTION_API_KEY"] }, "primaryEnv": "NOTION_API_KEY" },
  }
---

# Notion

This skill provides a direct interface to the Notion API, allowing you to create, read, and update pages, databases, and blocks. It is a powerful tool for automating your workflows and integrating Notion with other services.

## When to use
- Use this skill to create new pages or add entries to a database.
- It is ideal for querying your databases to retrieve specific information based on filters and sorts.
- You can also use it to update existing pages, either by modifying their properties or by adding new content blocks.

## Usage

All interactions with the Notion API are done through `curl` requests. You will need to have your Notion API key available.

### Creating a Page in a Database

To add a new entry to a database, you need to send a `POST` request to the `/v1/pages` endpoint.

```bash
curl -X POST "https://api.notion.com/v1/pages" \
  -H "Authorization: Bearer $NOTION_API_KEY" \
  -H "Notion-Version: 2022-06-28" \
  -H "Content-Type: application/json" \
  --data '{
    "parent": { "database_id": "your_database_id" },
    "properties": {
      "Name": {
        "title": [
          { "text": { "content": "New Task" } }
        ]
      }
    }
  }'
```

### Querying a Database

To retrieve data from a database, you can send a `POST` request to the `/v1/databases/{database_id}/query` endpoint.

```bash
curl -X POST "https://api.notion.com/v1/databases/your_database_id/query" \
  -H "Authorization: Bearer $NOTION_API_KEY" \
  -H "Notion-Version: 2022-06-28" \
  -H "Content-Type: application/json" \
  --data '{
    "filter": {
      "property": "Status",
      "select": { "equals": "In Progress" }
    }
  }'
```

### Appending Blocks to a Page

To add content to a page, you can append new blocks to its children.

```bash
curl -X PATCH "https://api.notion.com/v1/blocks/your_page_id/children" \
  -H "Authorization: Bearer $NOTION_API_KEY" \
  -H "Notion-Version: 2022-06-28" \
  -H "Content-Type: application/json" \
  --data '{
    "children": [
      {
        "object": "block",
        "type": "paragraph",
        "paragraph": {
          "rich_text": [
            { "text": { "content": "This is a new paragraph." } }
          ]
        }
      }
    ]
  }'
```
