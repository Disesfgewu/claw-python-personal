---
name: ordercli
description: "A command-line interface for checking past and active food orders, currently supporting Foodora."
homepage: https://ordercli.sh
metadata:
  {
    "openclaw":
      {
        "emoji": "🛵",
        "requires": { "bins": ["ordercli"] },
        "install":
          [
            {
              "id": "brew",
              "kind": "brew",
              "formula": "steipete/tap/ordercli",
              "bins": ["ordercli"],
              "label": "Install ordercli (brew)",
            },
            {
              "id": "go",
              "kind": "go",
              "module": "github.com/steipete/ordercli/cmd/ordercli@latest",
              "bins": ["ordercli"],
              "label": "Install ordercli (go)",
            },
          ],
      },
  }
---

# Order CLI

This skill provides a command-line interface for managing your food delivery orders. It currently supports Foodora, with plans to add support for other services in the future.

## When to use
- Use this skill to check the status of your active Foodora orders.
- It is ideal for viewing your order history and seeing details of past orders.
- You can also use it to reorder a previous meal, adding it directly to your cart.

## Usage

The `ordercli` skill offers a set of commands for interacting with your Foodora account.

### Viewing Active Orders

To see a list of your current orders and their status, use the `orders` command.

```bash
ordercli foodora orders
```

### Viewing Order History

You can view a list of your past orders with the `history` command.

```bash
ordercli foodora history --limit 10
```

### Reordering a Meal

To reorder a meal from your history, you will need the order code.

```bash
ordercli foodora reorder <order-code> --confirm
```
