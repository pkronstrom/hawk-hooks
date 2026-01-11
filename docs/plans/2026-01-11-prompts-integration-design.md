# Unified Prompts & Agents Integration

**Date:** 2026-01-11
**Status:** Design Complete

## Overview

Integrate unified prompt/agent management into captain-hook, inspired by the `~/.prompts` system. Captain-hook becomes a one-stop shop for managing hooks, commands, and agents across multiple AI coding tools (Claude, Gemini, Codex).

## Goals

- Drop-in markdown files that sync to tool-specific directories
- Frontmatter-based configuration for multi-tool targeting
- Optional hook registration for prompts/agents
- Symlink-based syncing (no copying)
- Auto-format conversion (TOML for Gemini)

## Directory Structure

```
~/.config/captain-hook/
├── hooks/           # scripts (.py, .sh, .js, .ts) - existing
│   └── pre_tool_use/
│       └── my-guard.sh
├── prompts/         # markdown commands (NEW)
│   └── my-command.md
├── agents/          # markdown agents (NEW)
│   └── code-reviewer.md
├── runners/         # generated bash runners - existing
└── config.json
```

## Frontmatter Schema

```yaml
---
name: my-command
description: Short description for CLI display
tools: all  # or [claude, gemini, codex]
hooks:      # optional - registers as hook too
  - event: pre_tool
    matchers: [Bash, Edit]
  - session_start
---

Command/agent content here...
```

### Fields

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | Display name in CLI |
| `description` | Yes | Short description for help text |
| `tools` | Yes | `all` or array: `[claude, gemini, codex]` |
| `hooks` | No | Array of hook registrations |

### Hook Entry Format

Simple (no config):
```yaml
hooks:
  - session_start
```

With matchers:
```yaml
hooks:
  - event: pre_tool
    matchers: [Bash, Edit, Write]
```

## Canonical Event Mapping

Canonical names map to tool-specific events:

| Canonical | Claude | Gemini |
|-----------|--------|--------|
| `pre_tool` | `pre_tool_use` | `BeforeTool` |
| `post_tool` | `post_tool_use` | `AfterTool` |
| `stop` | `stop` | `AfterAgent` |
| `notification` | `notification` | `Notification` |
| `session_start` | `session_start` | `SessionStart` |
| `session_end` | `session_end` | `SessionEnd` |
| `pre_compact` | `pre_compact` | `PreCompress` |

Tool-specific events (e.g., `user_prompt_submit` for Claude, `BeforeModel` for Gemini) pass through as-is and are skipped for unsupported tools.

## Syncing Behavior

### Destinations (configurable with defaults)

| Tool | Commands | Agents |
|------|----------|--------|
| Claude | `~/.claude/commands/` | `~/.claude/agents/` |
| Gemini | `~/.gemini/commands/` | `~/.gemini/agents/` |
| Codex | `~/.codex/prompts/` | `~/.codex/agents/` |

### Sync Strategy

- **Claude**: Symlink `.md` files directly
- **Gemini**: Generate TOML wrapper in destination
- **Codex**: TBD based on format requirements

### Enable/Disable

- **Enabled** = symlink/generated file exists
- **Disabled** = symlink/generated file removed

## CLI Commands

```
captain-hook install    # registers hook handlers in settings.json
captain-hook uninstall  # removes handlers + all symlinks everywhere
captain-hook            # main menu (auto-syncs first)
```

## Menu Structure

### Main Menu

```
┌─────────────────────────────┐
│  Captain Hook               │
├─────────────────────────────┤
│  > Hooks                    │
│    Commands                 │
│    Agents                   │
│    Add...                   │
│    ──────────────           │
│    Install                  │
│    Uninstall                │
│    Install Deps             │
│    Config                   │
└─────────────────────────────┘
```

### Submenus

**Hooks**: Shows script hooks from `hooks/` + prompts/agents with `hooks:` frontmatter

**Commands**: Shows files from `prompts/`

**Agents**: Shows files from `agents/`

**Add...**: Scaffold new hook/command/agent from presets

**Config**: Edit destinations and settings

### Cross-Menu Items

Prompts/agents with `hooks:` frontmatter appear in **both**:
- Commands/Agents menu (toggle symlink)
- Hooks menu (toggle hook registration)

These are independent toggles.

## Config.json Structure

```json
{
  "destinations": {
    "claude": {
      "commands": "~/.claude/commands/",
      "agents": "~/.claude/agents/"
    },
    "gemini": {
      "commands": "~/.gemini/commands/",
      "agents": "~/.gemini/agents/"
    },
    "codex": {
      "commands": "~/.codex/prompts/",
      "agents": "~/.codex/agents/"
    }
  },
  "hooks": {
    "pre_tool_use": {
      "my-guard": { "enabled": true }
    }
  },
  "prompts": {
    "my-command": {
      "enabled": true,
      "hook_enabled": false
    }
  },
  "agents": {
    "code-reviewer": {
      "enabled": true,
      "hook_enabled": true
    }
  }
}
```

## Auto-Sync Behavior

On menu launch:
1. Scan `prompts/`, `hooks/`, `agents/` directories
2. New files → added to config (**disabled by default**)
3. Removed files → cleaned from config + symlinks removed
4. Show menu with current state

## Out of Scope

- Vibe CLI support (for now)
- File watcher daemon
- Real-time sync

## Implementation Notes

### New Modules Needed

- `prompts.py` - Frontmatter parsing, prompt/agent scanning
- `sync.py` - Symlink management, TOML generation
- `event_mapping.py` - Canonical event translation

### Modified Modules

- `cli.py` - New menu items, auto-sync on launch
- `config.py` - New config sections (destinations, prompts, agents)
- `installer.py` - Handle prompt-based hooks

### Presets/Templates

Store in `~/.config/captain-hook/templates/` or bundled with package:
- `hook-bash-guard.py` - Block dangerous bash commands
- `hook-session-context.md` - Session start context injection
- `agent-code-reviewer.md` - Code review persona
- `command-example.md` - Basic command template
