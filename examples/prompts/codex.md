---
name: codex
description: Leverage OpenAI GPT models for autonomous code implementation via Codex CLI. Use when the user asks to invoke/call/run Codex, use codex CLI or codex exec, mention gpt-5/gpt-5.1/gpt-5.2 for implementation, or delegate coding tasks to Codex. Default model is gpt-5.2-codex (smartest). Other models are gpt-5.1-codex-max (large refactors), gpt-5.1-codex (routine), gpt-5.1-codex-mini (quick).
tools: [claude]
---

# Codex

You are operating in **codex exec** - a non-interactive automation mode for hands-off task execution.

## Recommended Model

**Default: `gpt-5.2-codex`** - The smartest available model. When in doubt, use this.

```bash
codex exec -m gpt-5.2-codex --full-auto "your task here"
```

## Model Selection Guide

| Model | Best For | Trade-offs |
|-------|----------|------------|
| `gpt-5.2-codex` | General coding, complex logic, debugging | Highest capability, moderate cost |
| `gpt-5.1-codex-max` | Large refactors, multi-file changes, project-scale work | Extended context, higher cost, slower |
| `gpt-5.1-codex` | Routine tasks, simple features, quick fixes | Balanced speed/capability |
| `gpt-5.1-codex-mini` | Simple edits, formatting, repetitive tasks | Fast and cheap, less reasoning depth |

**When in doubt, use `gpt-5.2-codex`.** It handles the widest range of tasks well.

### When to use each model

**gpt-5.2-codex** (default - use this)
- Complex feature implementation
- Debugging tricky issues
- Code requiring careful reasoning
- When quality matters more than speed
- Any task where you're unsure which model to pick

**gpt-5.1-codex-max**
- Refactoring entire modules
- Cross-file architectural changes
- Tasks requiring extensive context
- Long-running background tasks

**gpt-5.1-codex**
- Adding straightforward features
- Fixing obvious bugs
- Writing tests for existing code
- General day-to-day coding

**gpt-5.1-codex-mini**
- Renaming variables/functions
- Formatting or linting fixes
- Adding simple boilerplate
- Quick prototyping

## Prerequisites

Before using this skill, ensure Codex CLI is installed and configured:

```bash
codex --version
```

If not installed: `npm i -g @openai/codex` or `brew install codex`.

## Core Principles

### Autonomous Execution

- Execute tasks from start to finish without seeking approval for each action
- Make confident decisions based on best practices and task requirements
- Only ask questions if critical information is genuinely missing

### Operating Modes

**Read-Only Mode (Default)**
- Analyze code, search files, read documentation
- Safe for exploration and analysis tasks

**Workspace-Write Mode (Recommended for Programming)**
- Read and write files within the workspace
- **Use `--full-auto` or `-s workspace-write` to enable file editing**

**Danger-Full-Access Mode**
- Network access for fetching dependencies
- System-level operations outside workspace
- **Use only when explicitly requested and necessary**

## Key Commands

```bash
# Read-only analysis
codex exec -m gpt-5.2-codex -s read-only "analyze the codebase structure"

# Programming tasks (recommended)
codex exec -m gpt-5.2-codex --full-auto "implement the feature"

# Long-running project work
codex exec -m gpt-5.1-codex-max --full-auto "refactor the module"

# JSON output
codex exec -m gpt-5.2-codex --json "run tests and report results"
```

## Prompting Codex

Codex runs in isolation - it cannot see the parent conversation or context. Write self-contained prompts that include all necessary information.

### Effective prompts include:

1. **Clear objective**: What should be accomplished
2. **File paths**: Specific files to read/modify (if known)
3. **Constraints**: Technology stack, patterns to follow, things to avoid
4. **Success criteria**: How to verify the task is complete

### Examples

```bash
# Bad - too vague, missing context
codex exec -m gpt-5.2-codex --full-auto "fix the bug"

# Good - specific and self-contained
codex exec -m gpt-5.2-codex --full-auto "In src/auth/login.ts, the validateToken function throws on expired tokens instead of returning false. Fix it to return false for expired tokens. Run the existing tests to verify."

# Good - includes context and constraints
codex exec -m gpt-5.2-codex --full-auto "Add a dark mode toggle to the settings page. Use the existing ThemeContext in src/contexts/. Follow the component patterns in src/components/settings/. The toggle should persist to localStorage."
```

### Piping context

For complex tasks, pipe additional context via stdin:

```bash
# Pipe a file as context
cat ARCHITECTURE.md | codex exec -m gpt-5.2-codex --full-auto "Following the architecture described, add a new UserPreferences service"

# Pipe multiple files
cat src/types.ts src/api/client.ts | codex exec -m gpt-5.2-codex --full-auto "Add a new API endpoint for user settings using the existing patterns"
```

## Best Practices

- Make reasonable assumptions when minor details are ambiguous
- Focus strictly on the requested task
- Follow existing code patterns and conventions
- Run relevant tests after making changes
- Report any errors or limitations encountered
