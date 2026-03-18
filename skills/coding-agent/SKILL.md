---
name: coding-agent
description: "Delegates coding tasks to AI agents like Codex or Claude. It's used for building features, reviewing code, and refactoring."
metadata:
  {
    "openclaw": { "emoji": "🧩", "requires": { "anyBins": ["claude", "codex", "opencode", "pi"] } },
  }
---

# Coding Agent

This skill allows you to delegate complex coding tasks to a variety of AI-powered agents. It is designed to assist with building new features, refactoring existing code, and performing code reviews.

## When to use
- Use this skill when you need to create a new application or add a significant feature to an existing one.
- It is ideal for refactoring large codebases, where an agent can analyze the code and suggest improvements.
- You can also use it to review pull requests, with the agent providing feedback on code quality and style.

## Usage

The `coding-agent` skill can be used with several different AI agents, each with its own strengths.

### Using with Codex

Codex is a powerful coding agent that can handle a wide range of tasks. For interactive sessions, it is important to use a pseudo-terminal (PTY).

```bash
# In a git repository
bash pty:true workdir:./ command:"codex exec 'Implement a new user authentication flow'"
```

### Using with Claude Code

Claude Code is another capable agent that can be used for coding tasks. It does not require a PTY when used with the `--print` flag.

```bash
bash workdir:./ command:"claude --permission-mode bypassPermissions --print 'Refactor the database module to improve performance'"
```

### Running in the Background

For long-running tasks, you can execute the agent in the background. This allows you to continue working on other things while the agent completes its task.

```bash
bash pty:true workdir:./ background:true command:"codex exec --full-auto 'Build a complete e-commerce application'"
```
