# Command Guide

Commands are markdown files that define slash-command prompts (e.g., `/commit`, `/review`). When a user invokes the command, the tool loads the markdown content as instructions.

## Format

- Single `.md` file
- YAML frontmatter with `name` and `description` (required)
- Body contains the instructions the agent follows when the command is invoked
- Placed in `commands/` (or `prompts/`) directory

## Frontmatter Fields

| Field | Required | Description |
|-------|----------|-------------|
| `name` | yes | Command name (used as `/name` slash command) |
| `description` | yes | One-line summary shown in command listings |

## Tips

- Write instructions in imperative mood — tell the agent what to do
- Include specific steps, not vague guidance
- Reference bash commands with `!command` syntax if the agent should run them
- Keep it focused — one command, one job
- Commands map to: Claude `/slash-commands`, Gemini TOML commands, Codex custom prompts

## Template

```markdown
---
name: my-command
description: Brief description of what this command does
---

# My Command

Description of what this command accomplishes.

## Steps

1. First, gather context:

!relevant-command --here

2. Then do the main work
3. Present results to the user
```
