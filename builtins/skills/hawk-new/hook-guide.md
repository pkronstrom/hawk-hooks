# Hook Guide

Hooks are scripts that run in response to tool events (e.g., before a tool executes, after a session ends). They can block actions, log activity, or enforce policies.

## Format

- Script file (`.py`, `.sh`, `.js`, `.ts`)
- Comment headers declare metadata: events, description, dependencies
- Receives JSON on stdin, optionally outputs JSON on stdout
- Must be executable (`chmod +x`)

## Comment Headers

Place these after the shebang line:

```
# hawk-hook: events=<event_name>
# hawk-hook: description=<what this hook does>
# hawk-hook: deps=<comma-separated dependencies>
```

For JS/TS, use `//` comment syntax instead of `#`.

## Events

| Event | When it fires | Can block? |
|-------|--------------|------------|
| `pre_tool_use` | Before a tool executes | yes |
| `post_tool_use` | After a tool executes | no |
| `post_tool_use_failure` | After a tool fails | no |
| `notification` | Agent sends a notification | no |
| `stop` | Agent is about to stop | no |
| `subagent_start` | Subagent spawned | no |
| `subagent_stop` | Subagent finished | no |
| `user_prompt_submit` | User submits a prompt | yes |
| `session_start` | Session begins | no |
| `session_end` | Session ends | no |
| `pre_compact` | Before context compaction | no |
| `permission_request` | Permission dialog shown | no |

Not all events are supported by all tools. `pre_tool_use` and `post_tool_use` have the broadest support (Claude, Gemini, OpenCode). Codex only supports `stop` and `notification` via bridge mode.

## Stdin JSON

For `pre_tool_use` / `post_tool_use`:

```json
{
  "tool_name": "Edit",
  "tool_input": {
    "file_path": "/path/to/file.py",
    "old_string": "...",
    "new_string": "..."
  }
}
```

## Stdout JSON (pre-hooks only)

To block an action:

```json
{"decision": "block", "reason": "Why this was blocked"}
```

To allow (or simply exit 0 with no output):

```json
{"decision": "allow"}
```

## Python Template

```python
#!/usr/bin/env python3
# hawk-hook: events=pre_tool_use
# hawk-hook: description=Describe what this hook does

import json
import sys


def main():
    data = json.load(sys.stdin)
    tool_name = data.get("tool_name", "")
    tool_input = data.get("tool_input", {})

    # Your logic here
    # To block: print(json.dumps({"decision": "block", "reason": "..."}))
    # To allow: just exit 0


if __name__ == "__main__":
    main()
```

## Bash Template

```bash
#!/usr/bin/env bash
# hawk-hook: events=pre_tool_use
# hawk-hook: description=Describe what this hook does
# hawk-hook: deps=jq

set -euo pipefail

INPUT=$(cat)
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // ""')
TOOL_INPUT=$(echo "$INPUT" | jq -r '.tool_input // {}')

# Your logic here
# To block: echo '{"decision": "block", "reason": "..."}'
# To allow: just exit 0
```
