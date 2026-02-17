# hawk-hooks

![hawk banner](docs/hawk_banner.png)

**Drop-in Claude Code hooks for developers who want to extend the AI without touching JSON.**

Part of [**Nest-Driven Development**](https://github.com/pkronstrom/nest-driven-development) — the minimum vibable workflow.

Claude Code hooks are powerful, but adding one means editing a JSON config and hoping you got the schema right. hawk makes hooks first-class citizens: drop a file in the right folder, and it's live.

No restart. No config editing. hawk watches your hook directories and wires everything automatically, whether you're writing a quick shell guard or a full LLM-evaluated decision. Sharp by design — hooks execute in ~5ms and get out of the way.

## Features

- **Drop a file, get a hook** — auto-discovery means any script in `~/.config/hawk-hooks/hooks/{event}/` is live immediately
- **Write hooks in whatever language you think in** — Python, JavaScript, TypeScript, or shell all work
- **Inject context directly into Claude's view** — `.stdout.md` files surface output right where Claude sees it
- **Let Haiku make the call** — `.prompt.json` hooks use a fast LLM for nuanced allow/block decisions
- **Override per project, keep globals clean** — project-level hook configs layer on top without polluting your global setup

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
hawk  # First-time wizard (or `hawk-hooks`)
```

The wizard will:
1. Register hawk-hooks runners in Claude's settings
2. Let you enable/disable hooks
3. Install Python dependencies for enabled hooks

After setup, add hooks to `~/.config/hawk-hooks/hooks/{event}/` and run `hawk toggle` to enable them.

## Creating Hooks

Place hooks in event directories:
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
hawk toggle  # Choose "This project" scope
```

Choose "Personal" (added to `.git/info/exclude`) or "Shared" (committable).

## Examples

Copy examples to your hooks directory:

```bash
cp -r examples/hooks/* ~/.config/hawk-hooks/hooks/
hawk toggle  # Enable the ones you want
```

### Example Hooks

**pre_tool_use/**
- `file-guard.py` - Block sensitive file modifications
- `dangerous-cmd.sh` - Block dangerous commands
- `shell-lint.sh` - Shellcheck linting
- `git-commit-guide.sh` - Git commit best practices
- `loop-detector-cli.py` - Detect repetitive tool calls
- `scope-creep-detector-cli.py` - Detect scope creep
- `confidence-checker-cli.py` - Check confidence levels

**post_tool_use/**
- `python-lint.py` - Ruff linting
- `python-format.py` - Ruff auto-formatting

**stop/**
- `notify.py` - Desktop + ntfy.sh notifications
- `docs-update.sh` - Remind to update documentation
- `completion-check.stdout.md` - Completion checklist context
- `completion-validator-cli.py` - Validate task completion

**notification/**
- `notify.py` - Desktop + ntfy.sh notifications

**user_prompt_submit/**
- `context-primer.stdout.md` - Prime context on prompt submit

### Example Prompts (Skills)

The `examples/prompts/` directory contains skill definitions for Claude Code:
- `commit.md` - Generate commit messages
- `prime-context.md` - Prime session with project context
- `code-audit.md` - Comprehensive code audits
- `gemini.md` / `codex.md` - Delegate to other AI tools
- And more...

### Example Agents

The `examples/agents/` directory contains Task tool agent definitions:
- `code-reviewer.md` - Code review agent
- `test-generator.md` - Test generation agent
- `security-auditor.md` - Security audit agent
- `refactor-assistant.md` - Refactoring suggestions
- `docs-writer.md` - Documentation writer

## CLI Reference

```bash
hawk                    # Interactive menu (wizard on first run)
hawk status             # Show installation status
hawk toggle             # Enable/disable hooks (interactive)
hawk enable <hook>      # Enable hooks by name
hawk disable <hook>     # Disable hooks by name
hawk list [--enabled]   # List hooks (scriptable)
hawk install            # Install to Claude settings
hawk uninstall          # Remove from Claude settings
hawk install-deps       # Install Python dependencies
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
| `permission_request` | When permission is requested | No |

### Blocking Hooks

Command hooks can block by outputting:
```json
{"decision": "block", "reason": "Why it was blocked"}
```

Or exit with code 2.

## License

MIT
