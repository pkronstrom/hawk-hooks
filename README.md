# captain-hook

A modular Claude Code hooks manager with auto-discovery, multi-language support, and fast bash runners.

## Features

- **Auto-discovery**: Drop scripts in `~/.config/captain-hook/hooks/{event}/` and they appear automatically
- **Multi-language**: Python, JavaScript, Shell, TypeScript (via bun)
- **Fast execution**: Generated bash runners (~5ms overhead vs ~50ms for Python dispatcher)
- **Prompt hooks**: Markdown files that inject context into Claude's prompts
- **Project overrides**: Per-project hook configurations that override global settings
- **Interactive CLI**: First-run wizard, checkbox toggles, rich formatting

## Installation

```bash
pipx install git+https://github.com/bembu/captain-hook.git
```

Or for development:
```bash
git clone https://github.com/bembu/captain-hook.git
cd captain-hook
pip install -e .
```

## Quick Start

```bash
# Run the first-time wizard
captain-hook

# Or manually:
captain-hook install        # Register hooks in Claude settings
captain-hook toggle         # Enable/disable hooks interactively
captain-hook install-deps   # Install Python dependencies for hooks
captain-hook status         # Show what's installed and enabled
```

## Creating Hooks

Hooks are scripts that run on Claude Code events. Place them in:
```
~/.config/captain-hook/hooks/
├── pre_tool_use/      # Before tool execution (can block)
├── post_tool_use/     # After tool execution
├── stop/              # When Claude stops
├── notification/      # On notifications
└── user_prompt_submit/ # Before user prompt is sent
```

### Script Hooks

Scripts receive JSON on stdin and can output JSON responses. Add metadata comments:

```python
#!/usr/bin/env python3
# Description: Lint Python files with ruff
# Deps: ruff

import json
import sys

data = json.load(sys.stdin)
# Process and optionally output response
```

### Prompt Hooks

Markdown files (`.md`) that inject content into Claude's context:

```markdown
# Description: Add project guidelines

Always follow the project's coding style...
```

### Supported Languages

| Extension | Interpreter |
|-----------|-------------|
| `.py`     | Python (via venv) |
| `.js`     | Node.js |
| `.sh`     | Bash |
| `.ts`     | Bun |
| `.md`     | Prompt hook |

## Configuration

Global config: `~/.config/captain-hook/config.json`

```json
{
  "enabled": {
    "pre_tool_use": ["file-guard", "dangerous-cmd"],
    "post_tool_use": ["python-lint"],
    "stop": ["notify"]
  },
  "notify": {
    "desktop": true,
    "ntfy": {
      "enabled": false,
      "server": "https://ntfy.sh",
      "topic": "my-claude"
    }
  }
}
```

### Project Overrides

Create `.claude/captain-hook/config.json` in a project to override global settings:

```bash
captain-hook toggle  # Choose "This project" scope
```

Choose "Personal" to add to `.git/info/exclude` (not committed), or "Shared" to commit with the project.

## Example Hooks

Copy examples to your hooks directory:

```bash
cp -r examples/hooks/* ~/.config/captain-hook/hooks/
captain-hook toggle  # Enable the ones you want
```

Available examples:
- `python-lint.py` - Ruff linting for Python files
- `python-format.py` - Ruff auto-formatting
- `file-guard.py` - Block modifications to sensitive files (.env, credentials)
- `dangerous-cmd.sh` - Block dangerous shell commands (rm -rf /, etc.)
- `shell-lint.sh` - Shellcheck for shell scripts
- `notify.py` - Desktop + ntfy.sh notifications on stop
- `completion-check.md` - Prompt hook for task verification
- `context-primer.md` - Prompt hook for project context

## How It Works

1. **Install**: Registers bash runners in Claude's `~/.claude/settings.json`
2. **Toggle**: Enables/disables hooks and regenerates runners
3. **Execution**: Claude calls the bash runner, which chains enabled hooks

The bash runners are generated for performance - no Python startup overhead for each hook invocation.

## CLI Reference

```bash
captain-hook              # Interactive menu (or wizard on first run)
captain-hook status       # Show installation status
captain-hook install      # Install to Claude settings (--level user|project)
captain-hook uninstall    # Remove from Claude settings
captain-hook toggle       # Enable/disable hooks (regenerates runners)
captain-hook install-deps # Install Python dependencies
```

## Events

| Event | When | Can Block |
|-------|------|-----------|
| `pre_tool_use` | Before tool runs | Yes (exit 2) |
| `post_tool_use` | After tool completes | No |
| `stop` | Claude stops | No |
| `notification` | On notification | No |
| `user_prompt_submit` | Before prompt sent | No |

### Blocking Hooks

Pre-tool-use hooks can block execution by outputting:
```json
{"decision": "block", "reason": "Why it was blocked"}
```

## Requirements

- Python 3.10+
- For Python hooks: dependencies installed via `captain-hook install-deps`
- For other hooks: Node.js, Bash, Bun (as needed by your hooks)

## License

MIT
