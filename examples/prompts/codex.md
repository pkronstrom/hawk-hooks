---
name: codex
description: Leverage OpenAI GPT models for autonomous code implementation via Codex CLI. Use when the user asks to invoke/call/run Codex, use codex CLI or codex exec, mention GPT-5 for implementation, or delegate coding tasks to Codex. Default model is gpt-5.3-codex.
tools: [claude, gemini]
---

# Codex

You are operating in **codex exec** - a non-interactive automation mode for hands-off task execution.

## Recommended Model

**Default: `gpt-5.3-codex`** - Recommended by OpenAI for most coding tasks.

```bash
codex exec -m gpt-5.3-codex --full-auto "your task here"
```

## Model Selection Guide

| Model | Best For | Trade-offs |
|-------|----------|------------|
| `gpt-5.3-codex` | Most coding tasks, complex implementation, debugging | Best overall quality |
| `gpt-5.3-codex-spark` | Very fast iterative coding loops | Lower latency, preview-style workflow |
| `gpt-5.2-codex` | Strong fallback for agentic coding | Slightly older than 5.3 |
| `gpt-5.2` | Mixed coding + broader reasoning tasks | General-purpose model |
| `gpt-5.1-codex-max` | Long-running, project-scale refactors | Higher latency/cost, large context |

When in doubt, use `gpt-5.3-codex`.

To check for new models: https://developers.openai.com/codex/models/

## Prerequisites

Before using this skill, ensure Codex CLI is installed and configured:

```bash
codex --version
```

If not installed: `npm i -g @openai/codex` or `brew install codex`.

## Core Modes and Flags

### Approval and Sandbox

| Setting | Flag | Typical Use |
|---------|------|-------------|
| Full auto | `--full-auto` | Workspace-write + on-request approval for autonomous coding |
| Sandbox | `-s, --sandbox` | Choose `read-only`, `workspace-write`, or `danger-full-access` |
| Approval policy | `-a, --ask-for-approval` | `untrusted`, `on-failure`, `on-request`, `never` |
| YOLO bypass | `--dangerously-bypass-approvals-and-sandbox` | No approval/sandbox checks (high risk) |

### Output for Automation

| Output | Flag | Typical Use |
|--------|------|-------------|
| Event stream JSON | `--json` | Automation and machine parsing |
| Final message only | `-o, --output-last-message` | Capture clean final text in scripts |
| Enforce JSON schema | `--output-schema <file>` | Reliable structured output |

### Session/Runtime Controls

| Control | Flag | Typical Use |
|---------|------|-------------|
| Resume prior session | `resume --last` / `resume <id>` | Continue previous run |
| One-off state | `--ephemeral` | Skip loading/saving session state |
| Extra working dirs | `--add-dir <path>` | Multi-repo tasks |
| Skip repo check | `--skip-git-repo-check` | Non-git or CI workspaces |

## Key Commands

```bash
# Read-only analysis
codex exec -m gpt-5.3-codex -s read-only "analyze the codebase structure"

# Standard autonomous implementation
codex exec -m gpt-5.3-codex --full-auto "implement the feature"

# Large refactor with bigger-context model
codex exec -m gpt-5.1-codex-max --full-auto "refactor the module"

# Structured output for CI
action_schema=./schema.json
codex exec -m gpt-5.3-codex --json --output-schema "$action_schema" "run tests and summarize failures"

# Resume the latest session
codex resume --last "continue and finish remaining TODOs"
```

## Prompting Codex

Codex runs in isolation. Write self-contained prompts with all required context.

### Effective prompts include:

1. **Clear objective**: What to implement/fix
2. **Concrete paths**: Files/modules involved
3. **Constraints**: Patterns, stack, compatibility requirements
4. **Validation**: Tests/checks to run

### Examples

```bash
# Bad - vague
codex exec -m gpt-5.3-codex --full-auto "fix the bug"

# Good - specific + verifiable
codex exec -m gpt-5.3-codex --full-auto "In src/auth/login.ts, validateToken throws on expired tokens instead of returning false. Fix it and run existing tests."

# Good - constrained feature request
codex exec -m gpt-5.3-codex --full-auto "Add a dark mode toggle in settings. Use ThemeContext from src/contexts/, follow patterns in src/components/settings/, and persist to localStorage."
```

### Piping context

```bash
# Pipe architecture context
cat ARCHITECTURE.md | codex exec -m gpt-5.3-codex --full-auto "Following this architecture, add a new UserPreferences service"

# Pipe multiple code files
cat src/types.ts src/api/client.ts | codex exec -m gpt-5.3-codex --full-auto "Add a user settings API endpoint using existing patterns"
```

## Best Practices

- Use `gpt-5.3-codex` by default
- Start with `-s read-only` for investigation tasks
- Use `--json` + `--output-schema` for CI integrations
- Use `--dangerously-bypass-approvals-and-sandbox` only in isolated environments
- Run relevant tests after changes
