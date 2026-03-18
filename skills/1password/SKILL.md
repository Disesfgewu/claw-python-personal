---
name: 1password
description: "Manages 1Password CLI setup and usage. Handles CLI installation, app integration, sign-in, and securely reading secrets."
homepage: https://developer.1password.com/docs/cli/get-started/
metadata:
  {
    "openclaw":
      {
        "emoji": "🔐",
        "requires": { "bins": ["op"] },
        "install":
          [
            {
              "id": "brew",
              "kind": "brew",
              "formula": "1password-cli",
              "bins": ["op"],
              "label": "Install 1Password CLI (brew)",
            },
          ],
      },
  }
---

# 1Password

This skill provides a secure and efficient way to interact with the 1Password command-line interface (CLI). It helps you manage sensitive information, such as passwords and API keys, directly from your terminal.

## When to use
- Use this skill to install and configure the 1Password CLI on your system.
- It is ideal for signing into your 1Password account, including those with two-factor authentication.
- You can use it to securely access your secrets and inject them into your scripts or applications without exposing them.

## Usage

The `1password` skill simplifies the process of working with the `op` command.

### Signing In

To begin, you need to sign into your 1Password account. This is a one-time setup process.

```bash
op signin
```

### Reading a Secret

You can retrieve a secret from your vault and use it in a command. This is done securely, without printing the secret to the console.

```bash
op read "op://vault/item/field"
```

### Executing with Secrets

For a more secure workflow, you can run a command with secrets injected as environment variables.

```bash
op run -- your-command
```
