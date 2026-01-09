"""Script templates for captain-hook."""

import shutil
from pathlib import Path

# Python template
PYTHON_TEMPLATE = """#!/usr/bin/env python3
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
"""

# Shell template
SHELL_TEMPLATE = """#!/usr/bin/env bash
# Description: Your hook description
# Deps: jq
# Env:

set -euo pipefail
INPUT=$(cat)
# See: ~/.config/captain-hook/docs/hooks.md
# Exit 0 = ok, Exit 2 = block, other = error
exit 0
"""

# Node template
NODE_TEMPLATE = """#!/usr/bin/env node
// Description: Your hook description
// Deps:
// Env:

const data = JSON.parse(require('fs').readFileSync(0, 'utf8'));
// See: ~/.config/captain-hook/docs/hooks.md
// Exit 0 = ok, Exit 2 = block, other = error
process.exit(0);
"""

# TypeScript template (bun)
TS_BUN_TEMPLATE = """#!/usr/bin/env bun
// Description: Your hook description
// Deps:
// Env:

const data = await Bun.stdin.json();
// See: ~/.config/captain-hook/docs/hooks.md
// Exit 0 = ok, Exit 2 = block, other = error
process.exit(0);
"""

# TypeScript template (tsx via npx)
TS_TSX_TEMPLATE = """#!/usr/bin/env -S npx tsx
// Description: Your hook description
// Deps:
// Env:

import * as fs from 'fs';
const data = JSON.parse(fs.readFileSync(0, 'utf8'));
// See: ~/.config/captain-hook/docs/hooks.md
// Exit 0 = ok, Exit 2 = block, other = error
process.exit(0);
"""

# Stdout template
STDOUT_TEMPLATE = """# Context for Claude

Add your context here. This content is injected when the hook runs.
"""

# Prompt hook template
PROMPT_TEMPLATE = """{
  "prompt": "Evaluate if this action should proceed. Respond with {\\"decision\\": \\"approve\\"} or {\\"decision\\": \\"block\\", \\"reason\\": \\"why\\"}",
  "timeout": 30
}
"""

# Documentation file header (static content)
_HOOKS_DOC_HEADER = """# Captain-Hook Reference

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

"""


def get_hooks_doc() -> str:
    """Generate hooks documentation from event definitions.

    Returns full documentation including header and events section.
    Events are generated from the canonical EVENTS definitions.
    """
    from .events import generate_events_doc

    return _HOOKS_DOC_HEADER + generate_events_doc()


# Backwards compatibility - lazy property that generates on first access
HOOKS_DOC = get_hooks_doc()


# Static templates (no runtime detection needed)
_STATIC_TEMPLATES: dict[str, str] = {
    ".py": PYTHON_TEMPLATE,
    ".sh": SHELL_TEMPLATE,
    ".js": NODE_TEMPLATE,
}

# Dynamic templates (require runtime detection - lazy evaluation)
_DYNAMIC_TEMPLATES: dict[str, callable] = {
    ".ts": lambda: _get_ts_template(),  # Lazy - only called if .ts requested
}


def get_template(extension: str) -> str:
    """Get the template for a given extension.

    Static templates (.py, .sh, .js) are returned directly.
    Dynamic templates (.ts) are evaluated lazily to avoid unnecessary
    runtime detection when not needed.
    """
    if extension in _STATIC_TEMPLATES:
        return _STATIC_TEMPLATES[extension]
    if extension in _DYNAMIC_TEMPLATES:
        return _DYNAMIC_TEMPLATES[extension]()
    return ""


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
