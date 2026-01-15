# CLI Redesign

**Date:** 2026-01-06
**Status:** Approved

## Overview

Redesign hawk-hooks CLI for better UX with simplified mental model.

## Key Changes

### Mental Model
- **Install** = one-time setup, registers all events in Claude settings
- **Toggle** = primary way to manage handlers, instant effect (no Claude restart)
- Project overrides via `.claude/hawk-hooks.json`

### Menu Structure
```
╭─────────────────────────────────────────╮
│  hawk-hooks v0.1.0                    │
│  A modular Claude Code hooks manager    │
╰─────────────────────────────────────────╯

? What would you like to do?

❯ Status      Show registered hooks + enabled handlers
  Install     Register hooks in Claude + enable handlers
  Uninstall   Remove hooks from Claude settings
  Toggle      Enable/disable handlers (config only)
  ─────────
  Exit

(↑↓ navigate • Enter select • ESC back)
```

### Navigation
- ESC to go back at every level
- No explicit "Back" options needed in submenus

### Install Flow
1. Select: User settings or Project settings
2. Registers ALL events (PreToolUse, PostToolUse, Stop, Notification)
3. Creates default config if not exists
4. Done — use Toggle to customize

### Toggle Flow
1. Select scope: Global or This Project
2. If Project, ask: Personal (.git/info/exclude) or Shared (committable)
3. Checkbox multi-select with handlers grouped by event
4. Space to toggle, Enter to save, ESC to cancel
5. Changes take effect immediately (no Claude restart)

### Status View
Shows:
- Claude settings status (user + project)
- Effective handlers for current directory
- Source indicator (global / global + project overrides)

## Config Format

### Global (`~/.config/hawk-hooks/config.json`)
```json
{
  "handlers": {
    "post_tool_use": {
      "python-lint": { "enabled": true, "tool": "ruff" },
      "python-format": { "enabled": true },
      "ts-lint": { "enabled": false },
      "ts-format": { "enabled": false }
    },
    "pre_tool_use": {
      "file-guard": { "enabled": true },
      "dangerous-cmd": { "enabled": true },
      "security-review": { "enabled": false }
    },
    "stop": {
      "notify": { "enabled": false },
      "completion-check": { "enabled": false }
    }
  },
  "notify": {
    "desktop": true,
    "ntfy": { "enabled": false, "server": "https://ntfy.sh", "topic": "" }
  }
}
```

### Project Override (`.claude/hawk-hooks.json`)
```json
{
  "handlers": {
    "post_tool_use": {
      "ts-lint": { "enabled": true }
    }
  }
}
```

Only includes overrides — merged with global at runtime.

## Performance

**Per hook overhead:** ~35-55ms (mostly Python startup)

Optimizations applied:
- JSON instead of YAML (stdlib, faster parsing)
- Single stat() check for project config
- Lazy imports for handlers

## Implementation Changes

1. Replace YAML with JSON in config.py
2. Rewrite cli.py with new menu structure + rich styling
3. Update dispatcher.py for lean config loading
4. Add project override support with .git/info/exclude option
