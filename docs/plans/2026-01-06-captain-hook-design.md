# hawk-hooks Design Document

**Date:** 2026-01-06
**Status:** Approved

## Overview

**hawk-hooks** is a modular Claude Code hooks manager that:
- Installs a single dispatcher to Claude's settings per event type
- Routes events to enabled handlers based on config
- Supports both command hooks (deterministic) and prompt hooks (LLM-evaluated)
- Installable via `pipx install hawk-hooks`

## Architecture

### Core Flow

```
Claude event (PostToolUse, Stop, etc.)
    → hawk-hooks dispatcher (lightweight, fast startup)
    → reads ~/.config/hawk-hooks/config.yaml
    → lazy-imports only enabled handlers for that event
    → runs handlers in sequence
    → returns appropriate exit code / JSON response
```

### Key Design Choices

- One registration per event in Claude settings (clean)
- Handler granularity controlled via hawk-hooks's own config
- Project-specific handler selection via CLI flags in Claude's settings
- Prompts stored as editable `.md` files in `~/.config/hawk-hooks/prompts/`

## Handlers

### Command Handlers (8)

| Handler | Event | Tool/Action | Trigger |
|---------|-------|-------------|---------|
| `python-lint` | PostToolUse | `ruff check --fix` | `.py` files |
| `python-format` | PostToolUse | `ruff format` | `.py` files |
| `ts-lint` | PostToolUse | `eslint --fix` | `.ts/.tsx` files |
| `ts-format` | PostToolUse | `prettier --write` | `.ts/.tsx/.js/.json` files |
| `file-guard` | PreToolUse | Block edit | Sensitive files |
| `dangerous-cmd-block` | PreToolUse | Block command | Dangerous patterns |
| `notify` | Notification, Stop | ntfy.sh + desktop | User attention needed |

### Prompt Handlers (7)

| Handler | Event | Purpose |
|---------|-------|---------|
| `completion-check` | Stop | Verify all tasks actually done |
| `security-review` | PreToolUse | Catch subtle security issues |
| `code-quality-gate` | PostToolUse | Check for bugs/issues |
| `test-coverage-check` | Stop | Verify tests written |
| `scope-guard` | UserPromptSubmit | Keep requests in scope |
| `commit-suggestion` | Stop | Suggest commit if sensible chunk |
| `context-injector` | UserPromptSubmit | Add relevant context |

## Configuration

### Location

- `~/.config/hawk-hooks/config.yaml` - Main config
- `~/.config/hawk-hooks/prompts/*.md` - Prompt templates

### Config Format

```yaml
handlers:
  post_tool_use:
    python-lint:
      enabled: true
      tool: ruff
    python-format:
      enabled: true
    ts-lint:
      enabled: true
    ts-format:
      enabled: true

  pre_tool_use:
    file-guard:
      enabled: true
      patterns: [".env*", ".git/*", "*-lock.json", "*.pem", "*.key"]
    dangerous-cmd-block:
      enabled: true

  stop:
    notify:
      enabled: true
    completion-check:
      enabled: true
    commit-suggestion:
      enabled: true
    test-coverage-check:
      enabled: false

  notification:
    notify:
      enabled: true

  user_prompt_submit:
    scope-guard:
      enabled: false
    context-injector:
      enabled: false

notify:
  desktop: true
  ntfy:
    enabled: false
    server: "https://ntfy.sh"
    topic: ""
```

## CLI Interface

```bash
hawk-hooks                  # Interactive menu
hawk-hooks status           # Show all hooks (user + project)
hawk-hooks install          # Install to Claude settings
hawk-hooks uninstall        # Remove from Claude settings
hawk-hooks enable <handler> # Enable a handler
hawk-hooks disable <handler># Disable a handler
hawk-hooks list             # List available handlers
```

### Interactive Menu

```
hawk-hooks

[1] Status        - Show all registered hooks (user + project)
[2] Install       - Add hooks to Claude config
[3] Uninstall     - Remove hooks from Claude config
[4] Enable/Disable - Toggle handlers without uninstalling
[5] Handlers      - List available handlers, add custom ones
[6] Config        - Edit global settings

Select option:
```

## Project Structure

```
hawk-hooks/
├── pyproject.toml              # pipx installable
├── README.md
├── src/hawk_hooks/
│   ├── __init__.py
│   ├── cli.py                  # Entry point, interactive menu
│   ├── config.py               # Load/save ~/.config/hawk-hooks/
│   ├── installer.py            # Read/write Claude settings.json
│   ├── dispatcher.py           # Main hook entry, lazy-loads handlers
│   │
│   ├── handlers/               # Command-based handlers
│   │   ├── __init__.py
│   │   ├── base.py             # Base handler class
│   │   ├── python_lint.py
│   │   ├── python_format.py
│   │   ├── ts_lint.py
│   │   ├── ts_format.py
│   │   ├── file_guard.py
│   │   ├── dangerous_cmd_block.py
│   │   └── notify.py
│   │
│   └── prompt_hooks/           # Prompt hook loader
│       ├── __init__.py
│       └── loader.py           # Load .md, format JSON response
│
└── prompts/                    # Default prompts (copied to ~/.config on init)
    ├── completion-check.md
    ├── security-review.md
    ├── code-quality-gate.md
    ├── test-coverage-check.md
    ├── scope-guard.md
    ├── commit-suggestion.md
    └── context-injector.md
```

## Claude Integration

### Dispatcher Invocation

```bash
# How Claude calls it (registered in settings.json):
hawk-hooks --event post_tool_use --handlers python-lint,python-format
```

### Claude settings.json After Install

```json
{
  "hooks": {
    "PreToolUse": [{
      "matcher": "Edit|Write",
      "hooks": [{"type": "command", "command": "hawk-hooks --event pre_tool_use"}]
    }, {
      "matcher": "Bash",
      "hooks": [{"type": "command", "command": "hawk-hooks --event pre_tool_use"}]
    }],
    "PostToolUse": [{
      "matcher": "Edit|Write",
      "hooks": [{"type": "command", "command": "hawk-hooks --event post_tool_use"}]
    }],
    "Stop": [{
      "hooks": [{"type": "command", "command": "hawk-hooks --event stop"}]
    }],
    "Notification": [{
      "hooks": [{"type": "command", "command": "hawk-hooks --event notification"}]
    }],
    "UserPromptSubmit": [{
      "hooks": [{"type": "command", "command": "hawk-hooks --event user_prompt_submit"}]
    }]
  }
}
```

### Hook Identification

To identify hooks managed by hawk-hooks:

```python
def is_ours(hook):
    if hook.get("type") == "command":
        return hook.get("command", "").startswith("hawk-hooks")
    if hook.get("type") == "prompt":
        return hook.get("prompt", "").startswith("[hawk-hooks:")
    return False
```

Prompt hooks include marker: `[hawk-hooks:completion-check] Your prompt here...`

## Default Patterns

### file-guard (Block Edits)

```
.env, .env.*
.git/*
*-lock.json, *.lock
*.pem, *.key
credentials.*, secrets.*
id_rsa*, *.pub
```

### dangerous-cmd-block (Block Commands)

```
rm -rf /
rm -rf ~
rm -rf .
git push --force (to main/master)
DROP TABLE, DROP DATABASE
:(){ :|:& };:  (fork bomb)
> /dev/sda
chmod -R 777 /
curl | sh, wget | sh (pipe to shell)
```

## Tech Stack

- Python 3.10+
- questionary + rich (CLI/menus)
- pyyaml (config)
- No heavy deps in dispatcher path (lazy imports for fast startup)

## Installation Levels

- **User-level:** `~/.claude/settings.json` - applies to all projects
- **Project-level:** `.claude/settings.json` - project-specific

Duplicate detection prevents installing same hook at both levels.
