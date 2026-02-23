# Hawk Hook Format

## Problem

Hooks in v2 are stored in event-named directories (`registry/hooks/pre_tool_use/file-guard.py`), mirroring Claude Code's native layout. This creates problems:

1. **No cross-tool portability** — event names are Claude-specific (`PreToolUse`), other tools use different names or conventions
2. **No multi-event hooks** — a notification script that should fire on both `stop` and `notification` must be duplicated into two directories
3. **No hook metadata** — no way to describe what a hook does, what events it targets, or what deps it needs without reading the code
4. **Scanner can't classify** — `hawk scan` / `hawk download` can't distinguish hooks from regular scripts without the event-directory convention
5. **Sharing is fragile** — shipping hooks requires preserving the exact directory structure

## Design

### Flat files with inline metadata

Hooks are flat files stored in `registry/hooks/` (no event subdirectories). Each hook declares its target events via a `hawk-hook:` metadata header.

**Scripts** (`.py`, `.sh`, `.js`, `.ts`) use comment headers:

```python
#!/usr/bin/env python3
# hawk-hook: events=pre_tool_use
# hawk-hook: description=Block modifications to sensitive files
# hawk-hook: deps=requests

import json, sys
# ... hook logic
```

Multi-event:

```python
#!/usr/bin/env python3
# hawk-hook: events=stop,notification
# hawk-hook: description=Send desktop notification when done

import json, sys
# ...
```

**Content files** (`.md`, `.txt`, `.stdout.md`, `.stdout.txt`) use YAML frontmatter:

```markdown
---
hawk-hook:
  events: [stop]
  description: Verify task completion before stopping
---

Before stopping, please verify:
1. All requested changes are complete
2. Tests pass
...
```

### Metadata fields

| Field | Required | Type | Description |
|-------|----------|------|-------------|
| `events` | Yes | `list[str]` | Target event names (from `events.py`) |
| `description` | No | `str` | Human-readable description |
| `deps` | No | `str` | Python/npm dependencies hint |
| `env` | No | `list[str]` | Environment variable hints (e.g., `DESKTOP=true`) |

Minimal valid header: `# hawk-hook: events=pre_tool_use`

### Hook types by extension

| Extension | Type | Behavior |
|-----------|------|----------|
| `.py` | Command | Receives JSON on stdin, exit code controls flow |
| `.sh` | Command | Receives JSON on stdin, exit code controls flow |
| `.js`, `.ts` | Command | Receives JSON on stdin, exit code controls flow |
| `.stdout.md`, `.stdout.txt` | Content | Cat'd to stdout (context injection). Recognized without hawk-hook header (backward compat). |
| `.md`, `.txt` | Content | Cat'd to stdout — **only if hawk-hook frontmatter is present**. Without it, ignored (could be README, docs). |

### Hook recognition logic

A file is recognized as a hook through this cascade:

1. Has `hawk-hook:` header (comment or frontmatter) → hook, any extension
2. Extension is `.stdout.md` or `.stdout.txt` → content hook (backward compat, no header needed)
3. Extension is `.py`/`.sh`/`.js`/`.ts` with no header → check parent dir fallback (below)
4. Plain `.md`/`.txt` without header → **ignored** (could be README, docs)

### Backward compatibility — directory fallback

If a script file has **no** `hawk-hook:` header, the parser checks the parent directory name:

1. Parse `hawk-hook:` header from file → use declared events
2. No header, parent dir is a known event name (e.g., `pre_tool_use/`) → infer `events=[parent_dir_name]`
3. No header, unknown parent → hook is inert (no events, won't fire)

This means existing `builtins/hooks/pre_tool_use/file-guard.py` works as-is during migration, without requiring immediate header additions.

### Config format

Config uses plain filenames, not `event/filename`:

```yaml
global:
  hooks:
    - file-guard.py
    - notify.py
    - completion-check.md
    - dangerous-cmd.sh
```

The adapter reads each hook's metadata at runner-generation time to group by event.

## Pipeline Flow

```
Config lists hook names
        │
        ▼
Resolver collects hook names from config chain
        │
        ▼
Adapter.register_hooks() called with names + registry_path
        │
        ▼
For each hook name, parse metadata → get events list
        │
        ▼
Group hooks by event: {pre_tool_use: [file-guard.py, ...], stop: [...]}
        │
        ▼
Generate one bash runner per event (base._generate_runners)
        │
        ▼
Register runners in tool settings (adapter-specific)
```

## Implementation

### New file: `hook_meta.py`

```python
@dataclass
class HookMeta:
    events: list[str]
    description: str = ""
    deps: str = ""
    env: list[str] = field(default_factory=list)

def parse_hook_meta(path: Path) -> HookMeta:
    """Parse hawk-hook metadata from a file.

    Tries in order:
    1. hawk-hook: comment headers (scripts)
    2. YAML frontmatter (markdown/text)
    3. Parent directory fallback
    """
```

### Changes to existing files

**`downloader.py`** — `classify()` and `scan_directory()`:
- Recognize hook files by `hawk-hook:` header (via `hook_meta.parse_hook_meta`)
- Flat hooks dir: files at `hooks/` level are hooks, not just files in event subdirs
- `_classify_file()` checks for hawk-hook header as additional signal

**`adapters/base.py`** — `_generate_runners()`:
- Replace `event/filename` splitting with `hook_meta.parse_hook_meta()` lookup
- Group by parsed events instead of directory structure
- One hook can appear in multiple event runners

**`adapters/claude.py`** — `register_hooks()`:
- Calls `_generate_runners()` with parsed metadata
- Registers runners in `settings.json` using `events.EVENTS[event].claude_name`

**`builtins/hooks/`** — Restructure:
- Move files from `event/` subdirs to flat `hooks/`
- Add `hawk-hook:` headers to each file
- Rename `.stdout.md` → `.md` (frontmatter replaces extension convention)
- Remove empty event directories and `.keep` files

**`wizard.py`** — Enable logic:
- Appends plain filenames to config (`file-guard.py`), not `event/filename` format

**Other adapters** (`gemini.py`, `codex.py`, `opencode.py`):
- No changes needed — `register_hooks()` remains a stub

### No-change notes

- `registry.list()` already returns filenames — works as-is with flat layout
- `_scan_typed_dir()` in `downloader.py` handles both flat files (with metadata) and legacy event subdirs (dual-mode)

### Builtins migration example

Before:
```
builtins/hooks/
  pre_tool_use/
    file-guard.py
    dangerous-cmd.sh
  stop/
    completion-check.stdout.md
    notify.py
  notification/
    notify.py          # duplicate of stop/notify.py
```

After:
```
builtins/hooks/
  file-guard.py          # hawk-hook: events=pre_tool_use
  dangerous-cmd.sh       # hawk-hook: events=pre_tool_use
  completion-check.md    # frontmatter: events: [stop]  (renamed from .stdout.md)
  notify.py              # hawk-hook: events=stop,notification  (single file!)
```

## Scanning & Sharing

**`hawk scan <path>`**: Walks directory, uses `hook_meta.parse_hook_meta()` to identify hooks. Files with `hawk-hook:` headers are classified as hooks regardless of location.

**`hawk download <url>`**: Clones repo, scans with `classify()`. Hooks go to `registry/hooks/`. No event subdirectory needed.

**Sharing**: Ship a flat directory of hook files. Each file is self-describing via its header. No structural convention required beyond having the `hawk-hook:` header.

## Follow-ups

- **Per-event enable/disable** — if a hook targets 3 events, currently it fires on all 3 or none. Allow granular event selection per hook.
- **Execution order/priority** — hooks fire in config list order. Add explicit priority field if ordering needs arise.
- **Hook-level timeouts** — per-hook timeout configuration for long-running hooks.
- **Other adapter hook registration** — Gemini, Codex, OpenCode adapters remain stubs. Implement as those tools add hook support.
- **Hook dependency auto-install** — use `deps` field to auto-install Python/npm packages.
