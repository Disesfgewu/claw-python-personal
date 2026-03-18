---
name: himalaya
description: "A command-line interface for managing emails via IMAP/SMTP. It supports listing, reading, writing, and organizing emails."
homepage: https://github.com/pimalaya/himalaya
metadata:
  {
    "openclaw":
      {
        "emoji": "📧",
        "requires": { "bins": ["himalaya"] },
        "install":
          [
            {
              "id": "brew",
              "kind": "brew",
              "formula": "himalaya",
              "bins": ["himalaya"],
              "label": "Install Himalaya (brew)",
            },
          ],
      },
  }
---

# Himalaya Email CLI

This skill provides a powerful command-line interface for managing your email accounts. It allows you to perform all the essential email operations, such as reading, writing, and organizing your messages, without leaving the terminal.

## When to use
- Use this skill to list and read emails from your inbox or any other folder.
- It is ideal for composing and sending new emails, as well as replying to or forwarding existing ones.
- You can also use it to organize your emails by moving them between folders or adding flags.

## Usage

The `himalaya` skill offers a comprehensive set of commands for email management.

### Listing Emails

To see a list of emails in your inbox, use the `envelope list` command.

```bash
himalaya envelope list
```

### Reading an Email

To read the content of a specific email, you will need its ID.

```bash
himalaya message read <email-id>
```

### Composing and Sending an Email

You can write a new email and send it directly from the command line.

```bash
himalaya message write -H "To: recipient@example.com" -H "Subject: Greetings" "This is the body of the email."
```
