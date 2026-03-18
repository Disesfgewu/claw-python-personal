---
name: xurl
description: "Make authenticated requests to the X (Twitter) API v2 via the xurl CLI. Use when asked to post tweets, reply, quote, search posts, read timelines, manage followers, send DMs, upload media, like/repost, or call any X API v2 endpoint directly."
metadata:
  {
    "openclaw":
      {
        "emoji": "🐦",
        "requires": { "bins": ["xurl"] },
        "install":
          [
            {
              "id": "brew",
              "kind": "brew",
              "formula": "xdevplatform/tap/xurl",
              "bins": ["xurl"],
              "label": "Install xurl (brew)",
            },
            {
              "id": "npm",
              "kind": "npm",
              "package": "@xdevplatform/xurl",
              "bins": ["xurl"],
              "label": "Install xurl (npm)",
            },
          ],
      },
  }
---

# xurl

CLI for the X (Twitter) API v2. Supports shortcut commands and raw curl-style access to any endpoint.

## Security rules (mandatory)

- Never read, print, or pass `~/.xurl` to LLM context.
- Never use `--verbose` / `-v` — it can expose auth headers.
- Never use inline secret flags (`--bearer-token`, `--consumer-key`, etc.) in agent sessions.
- App credentials must be registered manually outside the agent session.
- Run `xurl auth status` to check current authentication.

## Auth

```bash
xurl auth status          # check existing auth
xurl auth oauth2          # authenticate (run manually outside agent)
xurl auth default APP     # set default app
xurl --app dev /2/users/me   # per-request app override
Quick reference
Action	Command
Post	xurl post "Hello world!"
Reply	xurl reply POST_ID "Text"
Quote	xurl quote POST_ID "Text"
Delete	xurl delete POST_ID
Read post	xurl read POST_ID
Search	xurl search "query" -n 10
Who am I	xurl whoami
User info	xurl user @handle
Timeline	xurl timeline -n 20
Mentions	xurl mentions -n 10
Like / unlike	xurl like POST_ID / xurl unlike POST_ID
Repost / undo	xurl repost POST_ID / xurl unrepost POST_ID
Bookmark	xurl bookmark POST_ID / xurl bookmarks -n 10
Follow / unfollow	xurl follow @handle / xurl unfollow @handle
Block / mute	xurl block @handle / xurl mute @handle
Send DM	xurl dm @handle "message"
List DMs	xurl dms -n 10
Upload media	xurl media upload file.jpg
Post with media	xurl media upload file.jpg then xurl post "text" --media-id MEDIA_ID
POST_ID can be a full URL — xurl extracts the ID automatically.

Raw API access

xurl /2/users/me
xurl -X POST /2/tweets -d '{"text":"Hello"}'
xurl -X DELETE /2/tweets/1234567890
xurl -s /2/tweets/search/stream    # streaming
Common flags
--app <name>    use a named app profile
-s              silent output (still returns JSON)
-X <METHOD>     HTTP method override
-d <JSON>       JSON body payload
--query k=v     add query params (repeatable)
Notes
All commands return JSON to stdout.
Rate limits: write endpoints are stricter than read endpoints; back off on 429.
OAuth2 tokens auto-refresh. Re-run xurl auth oauth2 if you get a 403 scope error.
Token storage: ~/.xurl (YAML). Never send this file to LLM context.


---
