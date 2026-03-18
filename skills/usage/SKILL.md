---
name: usage
description: "Summarize AI agent model usage and cost breakdown. Use when checking how many tokens or credits have been consumed across models."
metadata:
  {
    "openclaw":
      {
        "emoji": "📊",
        "os": ["darwin", "linux"],
        "requires": { "bins": [] },
        "install": []
      },
  }
---

# Model Usage

This skill provides a summary of AI agent model usage and cost breakdown. It is useful for monitoring token consumption and expenses across different models.

## When to use
- Use this skill when you need to check how many tokens or credits have been consumed by the AI agent.
- It is ideal for getting a cost breakdown per model, which helps in managing expenses.
- You can also use it to track usage over time to understand your consumption patterns.

## Usage

The `usage` skill is straightforward to use. The primary script for this skill is `model_usage.py`, located in the `scripts` directory.

### Summarize a Model

To get a summary of a specific model, you can run the following command. This will provide you with a breakdown of the model's usage and cost.

```bash
python {baseDir}/scripts/model_usage.py --provider <provider-name> --mode current
```

### Get a Full Report

If you need a comprehensive report of all models, you can run the script with the `all` mode. The output can be formatted as JSON for easier parsing.

```bash
python {baseDir}/scripts/model_usage.py --provider <provider-name> --mode all --format json --pretty
```
