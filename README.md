# hawk-hooks

![hawk banner](docs/hawk_banner.png)

[![PyPI version](https://img.shields.io/pypi/v/hawk-hooks)](https://pypi.org/project/hawk-hooks/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Part of NDD](https://img.shields.io/badge/NDD-minimum%20viable%20workflow-blue)](https://github.com/pkronstrom/nest-driven-development)

**Drop a file. Get a hook. No JSON required.**

Part of [**Nest-Driven Development**](https://github.com/pkronstrom/nest-driven-development) — the minimum viable workflow.

---

## The Problem

Claude Code hooks are one of its most powerful features. They're also one of the most annoying to set up — open a JSON config, find the right schema, add an entry, pray you didn't break anything, restart. For something that should take 30 seconds, it reliably takes 10 minutes.

## The Solution

hawk makes hooks first-class citizens. Drop a `.py`, `.sh`, `.js`, or `.ts` file into the right directory and it's live — no restart, no config editing, no schema hunting. hawk watches your hook directories and wires everything automatically.

Sharp by design: hooks execute in ~5ms and get out of the way.

---

## Quick Start

```bash
# Install
uv tool install git+https://github.com/pkronstrom/hawk-hooks.git

# First-time setup (wizard)
hawk

# Drop a hook and it's live
echo '#!/usr/bin/env python3
import json, sys
data = json.load(sys.stdin)
print("hook fired")' > ~/.config/hawk-hooks/hooks/pre_tool_use/my-hook.py

hawk toggle  # Enable it
```

---

## Features

- **Drop a file, get a hook** — any script in `~/.config/hawk-hooks/hooks/{event}/` is live immediately
- **Write in whatever language you think in** — Python, JavaScript, TypeScript, and shell all work
- **Inject context directly into Claude's view** — `.stdout.md` files surface output right where Claude reads it
- **Let Haiku make the call** — `.prompt.json` hooks use a fast LLM for nuanced allow/block decisions
- **Override per project, keep globals clean** — project-level configs layer on top without touching your global setup

---

## Hook Directory Layout

```
~/.config/hawk-hooks/hooks/
├── pre_tool_use/       # Before tool execution (can block)
├── post_tool_use/      # After tool execution
├── stop/               # When Claude stops
├── subagent_stop/      # When a subagent completes
├── notification/       # On notifications
├── user_prompt_submit/ # Before user prompt is sent
├── session_start/      # At session start/resume
├── session_end/        # When session ends
├── pre_compact/        # Before context compaction
└── permission_request/ # When permission is requested
```

---

## Hook Types

| Pattern | Type | What it does |
|---------|------|--------------|
| `name.py` | Command | Python script, receives JSON on stdin |
| `name.sh` | Command | Shell script, receives JSON on stdin |
| `name.js` | Command | Node.js script, receives JSON on stdin |
| `name.ts` | Command | TypeScript (bun), receives JSON on stdin |
| `name.stdout.md` | Stdout | Content injected directly into Claude's context |
| `name.stdout.txt` | Stdout | Same, plain text |
| `name.prompt.json` | Native Prompt | LLM-evaluated — Haiku decides allow/block |

### Command hook example

```python
#!/usr/bin/env python3
# Description: Lint Python files with ruff
# Deps: ruff

import json, sys

data = json.load(sys.stdin)
# Block by returning: {"decision": "block", "reason": "..."}
# Or exit with code 2 to block
```

### Context injection example

```markdown
<!-- reminder.stdout.md -->
# Description: Remind about documentation

Remember to update README.md if you change CLI commands.
```

### LLM-evaluated hook example

```json
{
  "prompt": "Evaluate if Claude should stop: $ARGUMENTS. Check if all tasks are complete and tests pass.",
  "timeout": 30
}
```

Supported events for prompt hooks: `Stop`, `SubagentStop`, `UserPromptSubmit`, `PreToolUse`.

---

## Blocking Hooks

Command hooks can block execution:

```json
{"decision": "block", "reason": "Why it was blocked"}
```

Or exit with code `2`.

---

## Configuration

Global config: `~/.config/hawk-hooks/config.json`

```json
{
  "enabled": {
    "pre_tool_use": ["file-guard", "dangerous-cmd"],
    "post_tool_use": ["python-lint"],
    "stop": ["notify"]
  }
}
```

### Project overrides

```bash
hawk toggle  # Choose "This project" scope
```

Pick "Personal" (added to `.git/info/exclude`) or "Shared" (committable).

---

## Events

| Event | When | Can block |
|-------|------|-----------|
| `pre_tool_use` | Before tool runs | ✅ |
| `post_tool_use` | After tool completes | ❌ |
| `stop` | Claude stops responding | ✅ |
| `subagent_stop` | Subagent finishes | ✅ |
| `notification` | On notification | ❌ |
| `user_prompt_submit` | Before prompt sent | ✅ |
| `session_start` | Session starts/resumes | ❌ |
| `session_end` | Session ends | ❌ |
| `pre_compact` | Before context compaction | ❌ |
| `permission_request` | When permission requested | ❌ |

---

## Example Hooks

Copy the included examples to get started fast:

```bash
cp -r examples/hooks/* ~/.config/hawk-hooks/hooks/
hawk toggle  # Enable the ones you want
```

**pre_tool_use/**
- `file-guard.py` — block sensitive file modifications
- `dangerous-cmd.sh` — block dangerous shell commands
- `shell-lint.sh` — shellcheck linting
- `loop-detector-cli.py` — detect repetitive tool calls
- `scope-creep-detector-cli.py` — detect scope creep

**post_tool_use/**
- `python-lint.py` — ruff linting
- `python-format.py` — ruff auto-formatting

**stop/**
- `notify.py` — desktop + ntfy.sh notifications
- `completion-validator-cli.py` — validate task completion

The `examples/prompts/` and `examples/agents/` directories contain Claude Code skills and agent definitions.

---

## CLI Reference

```bash
hawk                    # Interactive menu (wizard on first run)
hawk status             # Show installation status
hawk toggle             # Enable/disable hooks (interactive)
hawk enable <hook>      # Enable by name
hawk disable <hook>     # Disable by name
hawk list [--enabled]   # List hooks (scriptable)
hawk install            # Install to Claude settings
hawk uninstall          # Remove from Claude settings
hawk install-deps       # Install Python dependencies
```

Hook names can be short (`file-guard`) or explicit (`pre_tool_use/file-guard`).

---

## Installation

```bash
# Using uv (recommended)
uv tool install git+https://github.com/pkronstrom/hawk-hooks.git

# Using pipx
pipx install git+https://github.com/pkronstrom/hawk-hooks.git

# Development (editable install)
git clone https://github.com/pkronstrom/hawk-hooks.git
cd hawk-hooks
uv tool install --editable .
```

---

## License

MIT
