# Add Hook Feature Design

## Overview

Add a top-level "Add hook" menu item to captain-hook for quickly creating or linking new hooks.

## Menu Position

```
Status       Show hooks + enabled state
Toggle       Enable/disable hooks + regenerate
Add hook     Create or link a new hook       ← NEW
Config       Debug mode, notifications
─────────
Install      Register hooks in Claude settings
...
```

## User Flow

```
Add hook
├── 1. Select event (pre_tool_use, post_tool_use, stop, etc.)
├── 2. Select hook type:
│   ├── Link existing script (updates with original)
│   ├── Copy existing script (independent snapshot)
│   ├── Create command script → Python/Shell/Node/TypeScript
│   ├── Create stdout hook (.stdout.md)
│   └── Create prompt hook (.prompt.json)
├── 3. Enter path or filename (validated)
│   ├── Link/copy: validate exists, extension, offer chmod +x
│   └── Create: validate suffix, check no overwrite
├── 4. "Open in editor? (Y/n)" (for create only)
└── 5. "Enable this hook now? (Y/n)" → regenerate runners
```

## Script Templates

### Python (.py)
```python
#!/usr/bin/env python3
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
```

### Shell (.sh)
```bash
#!/usr/bin/env bash
# Description: Your hook description
# Deps: jq
# Env:

set -euo pipefail
INPUT=$(cat)
# See: ~/.config/captain-hook/docs/hooks.md
# Exit 0 = ok, Exit 2 = block, other = error
exit 0
```

### Node (.js)
```javascript
#!/usr/bin/env node
// Description: Your hook description
// Deps:
// Env:

const data = JSON.parse(require('fs').readFileSync(0, 'utf8'));
// See: ~/.config/captain-hook/docs/hooks.md
// Exit 0 = ok, Exit 2 = block, other = error
process.exit(0);
```

### TypeScript (.ts)
```typescript
#!/usr/bin/env bun
// Description: Your hook description
// Deps:
// Env:

const data = await Bun.stdin.json();
// See: ~/.config/captain-hook/docs/hooks.md
// Exit 0 = ok, Exit 2 = block, other = error
process.exit(0);
```

**TypeScript runtime detection:**
1. Check if `bun` is in PATH → use bun shebang
2. Else check if `npx` is in PATH → use `#!/usr/bin/env -S npx tsx`
3. Else → warn "No TypeScript runtime found. Install bun or npm to run .ts hooks"

Always show .ts option in menu regardless of runtime availability.

### Stdout Hook (.stdout.md)
```markdown
# Context for Claude

Add your context here. This content is injected when the hook runs.
```

### Prompt Hook (.prompt.json)
```json
{
  "prompt": "Evaluate if this action should proceed. Respond with {\"decision\": \"approve\"} or {\"decision\": \"block\", \"reason\": \"why\"}",
  "timeout": 30
}
```

## Documentation File

Create `~/.config/captain-hook/docs/hooks.md` on first install or when missing:

```markdown
# Captain-Hook Reference

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
```

## Validation & Error Handling

### Path validation (link/copy)
- File doesn't exist → "File not found: {path}"
- Wrong extension → "Unsupported extension. Use: .py, .sh, .js, .ts"
- Not executable → "Make executable? (Y/n)" → `chmod +x`

### Filename validation (create)
- Missing/wrong suffix → "Filename must end with .py, .sh, .js, or .ts"
- For stdout → "Filename must end with .stdout.md or .stdout.txt"
- For prompt → "Filename must end with .prompt.json"
- Already exists → "Hook already exists. Overwrite? (Y/n)"

### Editor launch
- Use $EDITOR env var
- Fallback to `nano`, then `vi`
- None found → "No editor found. Edit manually: {path}"

### Runtime warnings
- TypeScript with no bun/npx → "No TypeScript runtime found. Install bun or npm to run .ts hooks" (non-blocking, still create file)

## Implementation Notes

### Files to modify
- `cli.py`: Add `interactive_add_hook()` function and menu item
- `config.py`: Add docs directory path helper

### Files to create
- `templates.py`: Script template strings and generation logic
- `~/.config/captain-hook/docs/hooks.md`: Generated on install

### Menu choices use inline hints
```
Link existing script (updates with original)
Copy existing script (independent snapshot)
```

No extra explanation prompts needed.
