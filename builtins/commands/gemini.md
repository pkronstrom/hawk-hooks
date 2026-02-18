---
name: gemini
description: Leverage Google Gemini models for autonomous code implementation via Gemini CLI. Use when the user asks to invoke/call/run Gemini, use gemini CLI, mention Gemini for implementation, or delegate coding tasks to Gemini. Default model routing is auto; with preview enabled this can use Gemini 3 models.
tools: [claude, codex]
---

# Gemini

You are using **Gemini CLI** in non-interactive mode for hands-off task execution.

## Recommended Model

**Default: `--model auto`** - Recommended by Gemini CLI for most tasks.

- With preview features enabled, `auto` can route to Gemini 3 models.
- For stable fallback, `auto` routes to Gemini 2.5 models.

```bash
gemini --model auto --approval-mode yolo "your task here"
```

## Model Selection Guide

### Alias-Based Selection (Recommended)

| Model Alias | Resolves To | Best For |
|-------------|-------------|----------|
| `auto` | `gemini-3-pro-preview` or `gemini-2.5-pro` | Default, best overall quality/cost routing |
| `pro` | `gemini-3-pro-preview` or `gemini-2.5-pro` | Deep reasoning, architecture, complex debugging |
| `flash` | `gemini-2.5-flash` | Faster day-to-day implementation |
| `flash-lite` | `gemini-2.5-flash-lite` | Fastest/simple tasks |

### Manual Models

| Model | Best For | Notes |
|-------|----------|-------|
| `gemini-3-pro-preview` | Most complex reasoning | Requires preview features |
| `gemini-3-flash-preview` | Fast + capable coding loops | Requires preview features |
| `gemini-2.5-pro` | Stable complex work | Reliable fallback |
| `gemini-2.5-flash` | Quick implementation tasks | Lower latency/cost |

To enable Gemini 3 preview models:
1. Upgrade Gemini CLI (`npm install -g @google/gemini-cli@latest`)
2. Use `/settings` and set Preview Features to `true`
3. Use `/model` and pick Auto (Gemini 3), or pass a Gemini 3 model via `--model`

## Prerequisites

Before using this skill, ensure Gemini CLI is installed and configured:

```bash
gemini --version
```

If not installed, see the [Gemini CLI documentation](https://github.com/google-gemini/gemini-cli).

## Operating Modes

### Approval Modes

| Mode | Flag | Use Case |
|------|------|----------|
| `default` | `--approval-mode default` | Prompt on tool calls (safest default) |
| `auto_edit` | `--approval-mode auto_edit` | Auto-approve file edits only |
| `yolo` | `--approval-mode yolo` | Auto-approve all actions |
| `plan` | `--approval-mode plan` | Read-only planning mode (experimental) |

`--yolo` / `-y` still works but is deprecated; prefer `--approval-mode yolo`.

### Sandboxing

Use `-s` / `--sandbox` to run in a sandboxed environment.

```bash
gemini -s --model auto --approval-mode auto_edit "analyze and suggest safe changes"
```

## Key Commands

```bash
# Read-only-style analysis with default approvals
gemini --model auto "analyze the codebase structure"

# Full implementation (auto-approve all tools)
gemini --model auto --approval-mode yolo "implement the feature"

# Faster implementation loop with a specific model
gemini --model gemini-3-flash-preview --approval-mode yolo "refactor the module"

# JSON output for scripting
gemini --model auto --approval-mode auto_edit --output-format json "run tests and summarize failures"

# Streaming JSON events for monitoring
gemini --model auto --output-format stream-json "triage repository risks"
```

## Prompting Gemini

Gemini runs in isolation. Write self-contained prompts that include all necessary context.

### Effective prompts include:

1. **Clear objective**: What should be accomplished
2. **File paths**: Specific files to read/modify (if known)
3. **Constraints**: Tech stack, patterns, things to avoid
4. **Success criteria**: How to verify completion

### Examples

```bash
# Bad - too vague
gemini --model auto --approval-mode yolo "fix the bug"

# Good - specific and testable
gemini --model auto --approval-mode yolo "In src/auth/login.ts, validateToken throws on expired tokens instead of returning false. Fix it to return false for expired tokens and run existing tests."

# Good - includes architecture constraints
gemini --model auto --approval-mode yolo "Add a dark mode toggle to the settings page. Use ThemeContext in src/contexts/ and follow existing patterns in src/components/settings/. Persist to localStorage."
```

### Piping context

```bash
# Pipe architecture context
cat ARCHITECTURE.md | gemini --model auto --approval-mode yolo "Using this architecture, add a new UserPreferences service"

# Pipe test output for targeted debugging
npm test 2>&1 | gemini --model auto --approval-mode yolo "Fix the failing tests shown in this output"
```

## Best Practices

- Default to `--model auto` unless you have a strong reason to pin
- Use `--output-format json` or `stream-json` for automation
- Prefer `--approval-mode auto_edit` for safer unattended runs
- Use `--approval-mode yolo` only in controlled environments
- Run relevant tests after making changes
