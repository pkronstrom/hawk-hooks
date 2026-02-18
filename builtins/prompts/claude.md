---
name: claude
description: Leverage Anthropic Claude models for autonomous code implementation via Claude Code CLI. Use when the user asks to invoke/call/run Claude Code, use claude CLI, mention Claude models for implementation, or delegate coding tasks to Claude.
tools: [gemini, codex]
---

# Claude

You are using **Claude Code CLI** in print mode for non-interactive, scriptable execution.

## Recommended Model

**Default: `sonnet`** - Best default for most coding tasks in Claude Code.

```bash
claude -p --model sonnet --permission-mode acceptEdits "your task here"
```

## Model Selection Guide

Anthropic supports short aliases and full model IDs. Aliases track the latest stable model.

| Alias | Current Stable Version | Best For |
|-------|------------------------|----------|
| `sonnet` | Sonnet 4.5 | Daily coding, implementation, debugging |
| `opus` | Opus 4.6 | Deep reasoning, complex architecture, hardest bugs |
| `haiku` | Haiku 4.5 | Fast/simple tasks, lightweight assistance |

Use full IDs only when you need exact pinning (for reproducibility).

## Prerequisites

Before using this skill, ensure Claude Code CLI is installed and authenticated:

```bash
claude --version
```

If needed, install/update from https://docs.anthropic.com/en/docs/claude-code/overview.

## Key Modes and Flags

### Permission Modes

| Mode | Flag | Typical Use |
|------|------|-------------|
| Default | (no flag) | Normal interactive safety behavior |
| Auto-accept edits | `--permission-mode acceptEdits` | Autonomous coding while still gating risky actions |
| Plan only | `--permission-mode plan` | Read-only planning and analysis |
| Full bypass | `--dangerously-skip-permissions` | No permission prompts (high risk) |

### Common CLI Options

| Option | Flag | Use Case |
|--------|------|----------|
| Non-interactive print mode | `-p, --print` | Scriptable one-shot execution |
| Model selection | `--model <model>` | Pick `sonnet`, `opus`, `haiku`, or full ID |
| Structured output | `--output-format json` | Machine-readable results |
| Streaming JSON | `--output-format stream-json` | Event streaming in automation |
| JSON schema | `--json-schema <file>` | Enforce output structure |
| Conversation limit | `--max-turns <n>` | Bound autonomous loops |
| Add extra directories | `--add-dir <path>` | Multi-directory tasks |
| Resume session | `-r, --resume` / `-c, --continue` | Continue previous work |

## Key Commands

```bash
# Read-only planning/analysis
claude -p --model sonnet --permission-mode plan "analyze the codebase and propose a refactor plan"

# Autonomous implementation (recommended)
claude -p --model sonnet --permission-mode acceptEdits "implement the feature and run relevant tests"

# Hard architectural/debugging task
claude -p --model opus --permission-mode acceptEdits "diagnose the race condition and implement a robust fix"

# Structured JSON output for scripts
claude -p --model sonnet --output-format json "run tests and summarize failures"

# Resume latest session and continue
claude --continue --model sonnet -p "finish the remaining TODOs"
```

## Prompting Claude

Claude runs in isolation from parent chat context. Prompts should be fully self-contained.

### Effective prompts include:

1. **Objective**: Exact task and expected result
2. **Paths**: Relevant files/modules
3. **Constraints**: Patterns, libraries, performance/security requirements
4. **Validation**: Tests or checks required before completion

### Examples

```bash
# Bad - vague
claude -p --model sonnet --permission-mode acceptEdits "fix the bug"

# Good - specific and verifiable
claude -p --model sonnet --permission-mode acceptEdits "In src/auth/login.ts, validateToken throws on expired tokens instead of returning false. Fix it and run existing tests."

# Good - constrained implementation
claude -p --model sonnet --permission-mode acceptEdits "Add a dark mode toggle in settings using ThemeContext from src/contexts/. Follow patterns in src/components/settings/ and persist to localStorage."
```

### Piping context

```bash
# Pipe architecture context
cat ARCHITECTURE.md | claude -p --model sonnet --permission-mode acceptEdits "Using this architecture, add a new UserPreferences service"

# Pipe test output for focused debugging
npm test 2>&1 | claude -p --model sonnet --permission-mode acceptEdits "Fix the failing tests shown in this output"
```

## Best Practices

- Use `sonnet` by default; escalate to `opus` for hardest reasoning tasks
- Prefer `--permission-mode acceptEdits` for practical autonomy with guardrails
- Use `--output-format json` (and `--json-schema`) for automation
- Use `--max-turns` to bound unattended runs
- Run relevant tests before declaring completion
