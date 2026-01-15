---
name: gemini
description: Leverage Google Gemini models for autonomous code implementation via Gemini CLI. Use when the user asks to invoke/call/run Gemini, use gemini CLI, mention gemini-2.5 for implementation, or delegate coding tasks to Gemini. Default model is gemini-2.5-pro (smartest). Other models are gemini-2.5-flash (fast/cheap).
tools: [claude]
---

# Gemini

You are using **Gemini CLI** in non-interactive mode for hands-off task execution.

## Recommended Model

**Default: `gemini-2.5-pro`** - The smartest stable model. When in doubt, use this.

```bash
gemini -m gemini-2.5-pro --approval-mode yolo "your task here"
```

## Model Selection Guide

### Stable Models (Recommended)

| Model | Best For | Trade-offs |
|-------|----------|------------|
| `gemini-2.5-pro` | Complex reasoning, multi-file changes, architecture | Highest capability, slower |
| `gemini-2.5-flash` | Quick tasks, simple features, routine work | Fast and cheap, good for most tasks |

### Preview Models (Experimental)

| Model | Best For | Trade-offs |
|-------|----------|------------|
| `gemini-2.5-pro-preview-06-05` | Latest features, cutting-edge capability | May be unstable |
| `gemini-2.5-flash-preview-05-20` | Fast with latest features | May be unstable |

**When in doubt, use `gemini-2.5-pro`.** It handles the widest range of tasks well.

### When to use each model

**gemini-2.5-pro** (default - use this)
- Complex feature implementation
- Debugging tricky issues
- Code requiring careful reasoning
- Multi-file refactoring
- Any task where you're unsure which model to pick

**gemini-2.5-flash**
- Adding straightforward features
- Fixing obvious bugs
- Writing tests for existing code
- Quick prototyping
- When speed matters more than depth

**Preview models**
- Testing new capabilities
- When stable models don't perform well on specific tasks
- Experimental work where instability is acceptable

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
| Default | (none) | Prompts for each action - use for exploration |
| Auto-edit | `--approval-mode auto_edit` | Auto-approves file edits only |
| YOLO | `--approval-mode yolo` or `-y` | Auto-approves everything - use for programming |

### Sandbox Mode

Add `-s` or `--sandbox` to run in a sandboxed environment for safer execution.

## Key Commands

```bash
# Read-only analysis (default mode, will prompt for actions)
gemini -m gemini-2.5-pro "analyze the codebase structure"

# Programming tasks (recommended - auto-approves all actions)
gemini -m gemini-2.5-pro --approval-mode yolo "implement the feature"

# Quick tasks with faster model
gemini -m gemini-2.5-flash -y "add input validation to the form"

# Sandboxed execution (safer)
gemini -m gemini-2.5-pro -y -s "refactor the module"

# JSON output for parsing
gemini -m gemini-2.5-pro -y -o json "run tests and report results"
```

## Prompting Gemini

Gemini runs in isolation - it cannot see the parent conversation or context. Write self-contained prompts that include all necessary information.

### Effective prompts include:

1. **Clear objective**: What should be accomplished
2. **File paths**: Specific files to read/modify (if known)
3. **Constraints**: Technology stack, patterns to follow, things to avoid
4. **Success criteria**: How to verify the task is complete

### Examples

```bash
# Bad - too vague, missing context
gemini -m gemini-2.5-pro -y "fix the bug"

# Good - specific and self-contained
gemini -m gemini-2.5-pro -y "In src/auth/login.ts, the validateToken function throws on expired tokens instead of returning false. Fix it to return false for expired tokens. Run the existing tests to verify."

# Good - includes context and constraints
gemini -m gemini-2.5-pro -y "Add a dark mode toggle to the settings page. Use the existing ThemeContext in src/contexts/. Follow the component patterns in src/components/settings/. The toggle should persist to localStorage."
```

### Piping context

For complex tasks, pipe additional context via stdin using `-p`:

```bash
# Pipe a file as context
cat ARCHITECTURE.md | gemini -m gemini-2.5-pro -y -p "Following the architecture described, add a new UserPreferences service"

# Pipe error output for debugging
npm test 2>&1 | gemini -m gemini-2.5-pro -y -p "Fix the failing tests shown in this output"
```

## Best Practices

- Make reasonable assumptions when minor details are ambiguous
- Focus strictly on the requested task
- Follow existing code patterns and conventions
- Run relevant tests after making changes
- Report any errors or limitations encountered
