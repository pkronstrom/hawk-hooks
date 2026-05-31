# Agent Guide

Agents are markdown files that define specialized roles with tool access and optional hook triggers. Unlike commands (user-invoked), agents are typically dispatched by the tool itself (e.g., Claude's Agent tool, Codex multi-agent mode).

## Format

- Single `.md` file
- YAML frontmatter with `name`, `description`, and optional `tools` and `hooks`
- Body is the agent's system prompt / role definition
- Placed in `agents/` directory

## Frontmatter Fields

| Field | Required | Description |
|-------|----------|-------------|
| `name` | yes | Agent identifier |
| `description` | yes | One-line summary of the agent's role |
| `tools` | no | List of tools this agent is available for: `[claude, gemini, codex]` |
| `hooks` | no | List of hook triggers: `[{event: <event>, matchers: [Tool1, Tool2]}]` |

## Hook Triggers

Agents can be triggered automatically by hook events. The `matchers` field filters which tool invocations activate the agent:

```yaml
hooks:
  - event: pre_tool
    matchers: [Edit, Write]
```

This means the agent activates whenever `Edit` or `Write` tools are used.

## Tips

- Write the body as a system prompt — define the agent's role, expertise, and behavior
- Be specific about output format so results are consistent
- Include a review process or checklist the agent should follow
- Keep the scope narrow — one agent, one specialty

## Template

```markdown
---
name: my-agent
description: Brief description of this agent's specialty
tools: [claude, gemini, codex]
hooks:
  - event: pre_tool
    matchers: [Edit, Write]
---

You are a [role] with expertise in [domain].

## Your Role

[What this agent does and when it activates]

## Process

1. [Step one]
2. [Step two]
3. [Step three]

## Output Format

[How the agent should present its results]

## Guidelines

- [Key principle 1]
- [Key principle 2]
```
