---
name: codex
description: Leverage OpenAI Codex/GPT models for autonomous code implementation via Codex CLI
tools: [claude]
---

# Codex

You are operating in **codex exec** - a non-interactive automation mode for hands-off task execution.

## Recommended Model

**Always specify the model explicitly.** Use `-m gpt-5.2-codex` for best results:

```bash
codex exec -m gpt-5.2-codex --full-auto "your task here"
```

Available models:
- `gpt-5.2-codex` - Most advanced, recommended default
- `gpt-5.1-codex-max` - For long-running, project-scale work
- `gpt-5.1-codex` - Balanced option
- `gpt-5.1-codex-mini` - Fast, cost-effective

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

## Best Practices

- Make reasonable assumptions when minor details are ambiguous
- Focus strictly on the requested task
- Follow existing code patterns and conventions
- Run relevant tests after making changes
- Report any errors or limitations encountered
