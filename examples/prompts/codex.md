---
name: codex
description: Leverage OpenAI Codex/GPT models for autonomous code implementation via Codex CLI
tools: [claude]
---

# Codex

You are operating in **codex exec** - a non-interactive automation mode for hands-off task execution.

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
codex exec -s read-only "analyze the codebase structure"

# Programming tasks (recommended)
codex exec --full-auto "implement the feature"

# With specific model
codex exec -m gpt-5.2 --full-auto "refactor the module"

# JSON output
codex exec --json "run tests and report results"
```

## Best Practices

- Make reasonable assumptions when minor details are ambiguous
- Focus strictly on the requested task
- Follow existing code patterns and conventions
- Run relevant tests after making changes
- Report any errors or limitations encountered
