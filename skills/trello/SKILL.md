---
name: trello
description: "Manage Trello boards, lists, and cards via the Trello REST API. Use when: listing boards or cards, creating or moving cards, adding comments, or archiving cards. Requires TRELLO_API_KEY and TRELLO_TOKEN env vars."
homepage: https://developer.atlassian.com/cloud/trello/rest/
metadata:
  {
    "openclaw":
      { "emoji": "📋", "requires": { "bins": ["jq"], "env": ["TRELLO_API_KEY", "TRELLO_TOKEN"] } },
  }
---

# Trello

Interact with Trello boards, lists, and cards using the REST API via `curl` and `jq`.

## Auth setup

Get your credentials at <https://trello.com/app-key> then set:

```bash
export TRELLO_API_KEY="your-api-key"
export TRELLO_TOKEN="your-token"
Common operations
List boards

curl -s "https://api.trello.com/1/members/me/boards?key=$TRELLO_API_KEY&token=$TRELLO_TOKEN&fields=name,id" | jq '.[] | {name, id}'
Lists in a board

curl -s "https://api.trello.com/1/boards/{boardId}/lists?key=$TRELLO_API_KEY&token=$TRELLO_TOKEN" | jq '.[] | {name, id}'
Cards in a list

curl -s "https://api.trello.com/1/lists/{listId}/cards?key=$TRELLO_API_KEY&token=$TRELLO_TOKEN" | jq '.[] | {name, id, desc}'
Create a card

curl -s -X POST "https://api.trello.com/1/cards?key=$TRELLO_API_KEY&token=$TRELLO_TOKEN" \
  -d "idList={listId}" -d "name=Title" -d "desc=Description"
Move a card

curl -s -X PUT "https://api.trello.com/1/cards/{cardId}?key=$TRELLO_API_KEY&token=$TRELLO_TOKEN" \
  -d "idList={newListId}"
Add a comment

curl -s -X POST "https://api.trello.com/1/cards/{cardId}/actions/comments?key=$TRELLO_API_KEY&token=$TRELLO_TOKEN" \
  -d "text=Your comment"
Archive a card

curl -s -X PUT "https://api.trello.com/1/cards/{cardId}?key=$TRELLO_API_KEY&token=$TRELLO_TOKEN" \
  -d "closed=true"
Notes
Board, list, and card IDs appear in Trello URLs or can be retrieved via list commands.
Rate limits: 300 req/10s per API key; 100 req/10s per token.
Keep your API key and token secret.


---
