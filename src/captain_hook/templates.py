"""Script templates for captain-hook."""

import shutil
from pathlib import Path

# Python template
PYTHON_TEMPLATE = '''#!/usr/bin/env python3
# Description: Your hook description
# Deps:
# Env:

import json
import sys


def main():
    data = json.load(sys.stdin)
    # See: ~/.config/captain-hook/docs/hooks.md
    # Exit 0 = ok, Exit 2 = block, other = error
    sys.exit(0)


if __name__ == "__main__":
    main()
'''

# Shell template
SHELL_TEMPLATE = '''#!/usr/bin/env bash
# Description: Your hook description
# Deps: jq
# Env:

set -euo pipefail
INPUT=$(cat)
# See: ~/.config/captain-hook/docs/hooks.md
# Exit 0 = ok, Exit 2 = block, other = error
exit 0
'''

# Node template
NODE_TEMPLATE = '''#!/usr/bin/env node
// Description: Your hook description
// Deps:
// Env:

const data = JSON.parse(require('fs').readFileSync(0, 'utf8'));
// See: ~/.config/captain-hook/docs/hooks.md
// Exit 0 = ok, Exit 2 = block, other = error
process.exit(0);
'''

# TypeScript template (bun)
TS_BUN_TEMPLATE = '''#!/usr/bin/env bun
// Description: Your hook description
// Deps:
// Env:

const data = await Bun.stdin.json();
// See: ~/.config/captain-hook/docs/hooks.md
// Exit 0 = ok, Exit 2 = block, other = error
process.exit(0);
'''

# TypeScript template (tsx via npx)
TS_TSX_TEMPLATE = '''#!/usr/bin/env -S npx tsx
// Description: Your hook description
// Deps:
// Env:

import * as fs from 'fs';
const data = JSON.parse(fs.readFileSync(0, 'utf8'));
// See: ~/.config/captain-hook/docs/hooks.md
// Exit 0 = ok, Exit 2 = block, other = error
process.exit(0);
'''

# Stdout template
STDOUT_TEMPLATE = '''# Context for Claude

Add your context here. This content is injected when the hook runs.
'''

# Prompt hook template
PROMPT_TEMPLATE = '''{
  "prompt": "Evaluate if this action should proceed. Respond with {\\"decision\\": \\"approve\\"} or {\\"decision\\": \\"block\\", \\"reason\\": \\"why\\"}",
  "timeout": 30
}
'''

# Documentation file content
HOOKS_DOC = '''# Captain-Hook Reference

Official Claude Code hooks documentation:
https://docs.anthropic.com/en/docs/claude-code/hooks

## Script Comments

- `# Description: ...` - Shown in status/toggle menus
- `# Deps: pkg1, pkg2` - Python packages (auto-installed)
- `# Env: VAR=default` - Config menu option, baked into runner

## Exit Codes

- `0` = success (stdout shown in verbose mode)
- `2` = block operation (stderr shown to Claude)
- `other` = error (shown to user, non-blocking)

## Events

### pre_tool_use
Runs before tool execution. Can block.
Fields: session_id, cwd, tool_name, tool_input, tool_use_id

### post_tool_use
Runs after tool completes. Can provide feedback.
Fields: session_id, cwd, tool_name, tool_input, tool_response

### stop
Runs when agent finishes. Can request continuation.
Fields: session_id, cwd, stop_reason

### user_prompt_submit
Runs when user submits prompt. Can block or add context.
Fields: session_id, cwd, prompt

### notification
Runs when Claude sends notifications.
Fields: session_id, cwd, message

### subagent_stop
Runs when subagent/Task tool finishes.
Fields: session_id, cwd, stop_reason

### session_start
Runs at session start/resume/clear.
Fields: session_id, cwd, source (startup|resume|clear|compact)

### session_end
Runs when session ends.
Fields: session_id, cwd, reason

### pre_compact
Runs before context compaction.
Fields: session_id, cwd, source (manual|auto)
'''


def get_template(extension: str) -> str:
    """Get the template for a given extension."""
    templates = {
        ".py": PYTHON_TEMPLATE,
        ".sh": SHELL_TEMPLATE,
        ".js": NODE_TEMPLATE,
        ".ts": _get_ts_template(),
    }
    return templates.get(extension, "")


def _get_ts_template() -> str:
    """Get TypeScript template based on available runtime."""
    if shutil.which("bun"):
        return TS_BUN_TEMPLATE
    return TS_TSX_TEMPLATE


def get_ts_runtime() -> str | None:
    """Detect available TypeScript runtime."""
    if shutil.which("bun"):
        return "bun"
    if shutil.which("npx"):
        return "tsx"
    return None


def ensure_docs(docs_dir: Path) -> Path:
    """Ensure hooks.md documentation exists. Returns path to docs file."""
    docs_dir.mkdir(parents=True, exist_ok=True)
    docs_path = docs_dir / "hooks.md"
    if not docs_path.exists():
        docs_path.write_text(HOOKS_DOC)
    return docs_path
