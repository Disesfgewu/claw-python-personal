---
name: github
description: "Handles various GitHub operations including issue tracking, pull requests, CI runs, and code reviews. It can fetch a list of issues, spawn a sub-agent to implement a fix, and open a pull request."
homepage: ""
metadata:
  openclaw:
    emoji: "🐙"
    os: ["darwin", "linux"]
    requires:
      bins: ["gh"]
---

# GitHub

This skill provides comprehensive integration with GitHub, allowing for a wide range of repository interactions directly from the command line. It streamlines workflows related to issues, pull requests, and continuous integration.

## When to use
- Use this skill to manage the full lifecycle of issues, from creation to resolution.
- It is ideal for automating the process of fixing bugs, where it can fetch an issue, apply a code fix, and submit a pull request.
- Utilize it for monitoring CI/CD pipelines, checking the status of builds, and reviewing logs.
- It is also suitable for general pull request management, such as creating, reviewing, and merging PRs.

## Usage

The `github` skill is a versatile tool for interacting with GitHub repositories. Below are some examples of how to use it.

### General Commands

- **List Issues:** `gh issue list`
- **Create an Issue:** `gh issue create --title "New Feature" --body "Details about the new feature."`
- **List Pull Requests:** `gh pr list`
- **Check CI Status:** `gh pr checks <pr-number>`

### Automated Issue Fixing

The skill can automate the process of fixing an issue and creating a pull request.

1.  **Fetch an Issue:**
    To get the details of a specific issue, you can use the following command, which will retrieve the title, body, and other relevant information.
    ```bash
    gh issue view <issue-number> --json title,body
    ```

2.  **Spawn a Sub-agent for a Fix:**
    After identifying an issue, you can spawn a sub-agent to work on a fix. The agent will operate in a separate environment to develop and test the solution.
    ```bash
    # This is a conceptual example. The actual implementation will be handled by the agent.
    # The agent will receive the issue details and start working on a fix.
    ```

3.  **Create a Pull Request:**
    Once the fix is ready, the agent will create a new pull request. The PR will include a summary of the changes and a reference to the issue it resolves.
    ```bash
    gh pr create --title "Fix: resolves #<issue-number>" --body "Description of the fix."
    ```
