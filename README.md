# hawk-hooks

A modular Claude Code hooks manager with auto-discovery, multi-language support, and fast bash runners.

## Features

- **Auto-discovery**: Drop scripts in `~/.config/hawk-hooks/hooks/{event}/` and they appear automatically
- **Multi-language**: Python, JavaScript, Shell, TypeScript (via bun)
- **Fast execution**: Generated bash runners (~5ms overhead vs ~50ms for Python dispatcher)
- **Context injection**: `.stdout.md` files output content directly to Claude's context
- **Native prompt hooks**: `.prompt.json` files for LLM-evaluated decisions (Haiku)
- **Project overrides**: Per-project hook configurations that override global settings

## Installation

```bash
# Using uv (recommended)
uv tool install git+https://github.com/pkronstrom/hawk-hooks.git

# Or using pipx
pipx install git+https://github.com/pkronstrom/hawk-hooks.git
```

For development (editable install):
```bash
git clone https://github.com/pkronstrom/hawk-hooks.git
cd hawk-hooks

# Using uv (recommended)
uv tool install --editable .

# Or using pip
pip install -e .
```

### Installing uv

If you don't have uv installed, it's the modern Python package manager (10-100x faster than pip):

```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Or with Homebrew
brew install uv
```

hawk-hooks will automatically use uv for installing hook dependencies if available, falling back to pip otherwise.

## Quick Start

```bash
hawk-hooks  # First-time wizard (or just `hawk`)
```

The wizard will:
1. Register hawk-hooks runners in Claude's settings
2. Let you enable/disable hooks
3. Install Python dependencies for enabled hooks

After setup, add hooks to `~/.config/hawk-hooks/hooks/{event}/` and run `hawk-hooks toggle` to enable them.

## Creating Hooks

Place hooks in event directories:
```
~/.config/hawk-hooks/hooks/
├── pre_tool_use/      # Before tool execution (can block)
├── post_tool_use/     # After tool execution
├── stop/              # When Claude stops
├── notification/      # On notifications
└── user_prompt_submit/ # Before user prompt is sent
```

### Hook Types

| Pattern | Type | Description |
|---------|------|-------------|
| `name.py` | Command | Python script, receives JSON stdin |
| `name.sh` | Command | Shell script, receives JSON stdin |
| `name.js` | Command | Node.js script, receives JSON stdin |
| `name.ts` | Command | TypeScript (bun), receives JSON stdin |
| `name.stdout.md` | Stdout | Content output directly to Claude's context |
| `name.stdout.txt` | Stdout | Content output directly to Claude's context |
| `name.prompt.json` | Native Prompt | LLM-evaluated hook (Haiku decides) |

### Command Hooks

Scripts receive JSON on stdin and can output JSON responses:

```python
#!/usr/bin/env python3
# Description: Lint Python files with ruff
# Deps: ruff

import json
import sys

data = json.load(sys.stdin)
# Process and optionally output response
```

### Stdout Hooks (Context Injection)

Files named `*.stdout.md` or `*.stdout.txt` have their content output directly to Claude:

```markdown
<!-- reminder.stdout.md -->
# Description: Remind about documentation

Remember to update README.md if you change CLI commands.
```

### Native Prompt Hooks (LLM-Evaluated)

Files named `*.prompt.json` are registered as Claude's native `type: "prompt"` hooks. Haiku evaluates them and decides whether to approve/block:

```json
{
  "prompt": "Evaluate if Claude should stop: $ARGUMENTS. Check if all tasks are complete and tests pass.",
  "timeout": 30
}
```

Supported events for prompt hooks: Stop, SubagentStop, UserPromptSubmit, PreToolUse.

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

### Project Overrides

```bash
hawk-hooks toggle  # Choose "This project" scope
```

Choose "Personal" (added to `.git/info/exclude`) or "Shared" (committable).

## Example Hooks

Copy examples to your hooks directory:

```bash
cp -r examples/hooks/* ~/.config/hawk-hooks/hooks/
hawk-hooks toggle  # Enable the ones you want
```

Available examples:
- `python-lint.py` - Ruff linting
- `python-format.py` - Ruff auto-formatting
- `file-guard.py` - Block sensitive file modifications
- `dangerous-cmd.sh` - Block dangerous commands
- `shell-lint.sh` - Shellcheck linting
- `git-commit-guide.sh` - Git commit best practices
- `notify.py` - Desktop + ntfy.sh notifications
- `docs-update.sh` - Remind to update documentation

## CLI Reference

```bash
hawk-hooks              # Interactive menu (wizard on first run)
hawk-hooks status       # Show installation status
hawk-hooks toggle       # Enable/disable hooks (interactive)
hawk-hooks enable <hook> [<hook>...]   # Enable hooks by name
hawk-hooks disable <hook> [<hook>...]  # Disable hooks by name
hawk-hooks list [--enabled|--disabled] # List hooks (scriptable)
hawk-hooks install      # Install to Claude settings
hawk-hooks uninstall    # Remove from Claude settings
hawk-hooks install-deps # Install Python dependencies
```

Hook names can be short (`file-guard`) or explicit (`pre_tool_use/file-guard`).

## Events

| Event | When | Can Block |
|-------|------|-----------|
| `pre_tool_use` | Before tool runs | Yes |
| `post_tool_use` | After tool completes | No |
| `stop` | Claude stops responding | Yes |
| `subagent_stop` | Subagent finishes | Yes |
| `notification` | On notification | No |
| `user_prompt_submit` | Before prompt sent | Yes |
| `session_start` | Session starts/resumes | No |
| `session_end` | Session ends | No |
| `pre_compact` | Before context compaction | No |

### Blocking Hooks

Command hooks can block by outputting:
```json
{"decision": "block", "reason": "Why it was blocked"}
```

Or exit with code 2.

## License

MIT
