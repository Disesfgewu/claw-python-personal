---
name: oracle
description: "A tool for using large language models with local file context. It supports different engines, prompt bundling, and session management."
homepage: https://askoracle.dev
metadata:
  {
    "openclaw":
      {
        "emoji": "🧿",
        "requires": { "bins": ["oracle"] },
        "install":
          [
            {
              "id": "node",
              "kind": "node",
              "package": "@steipete/oracle",
              "bins": ["oracle"],
              "label": "Install oracle (node)",
            },
          ],
      },
  }
---

# Oracle

This skill allows you to run large language models with the context of your local files. It is designed to help you with tasks that require an understanding of your project's codebase, such as answering questions, generating code, or debugging issues.

## When to use
- Use this skill to ask questions about your code and get answers that are informed by the actual files in your project.
- It is ideal for generating new code or modifying existing code, with the model having access to the relevant context.
- You can also use it to debug problems, with the model helping you to identify the root cause of an issue.

## Usage

The `oracle` skill provides a flexible way to interact with large language models.

### Running a Query

To run a query, you provide a prompt and specify the files that should be included as context.

```bash
oracle -p "How does the authentication middleware work?" --file "src/middleware/auth.ts"
```

### Using a Different Engine

You can choose from different engines to run your query, such as the browser or the API.

```bash
oracle --engine browser -p "Generate a new component for the user profile page." --file "src/components/**"
```

### Managing Sessions

For long-running tasks, you can use sessions to keep track of your work.

```bash
# List recent sessions
oracle status

# Re-attach to a session
oracle session <session-id>
```
