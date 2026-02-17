# Hawk v2 Interactive TUI Design

## Overview

Replace the v1 Claude-only interactive menu with a v2 TUI that operates entirely on the v2 backend (registry, resolver, multi-tool adapters). One TUI, fully v2. The v1 interactive menu is retired.

## Decisions

- **Audience**: Both first-time and power users. Guided wizard on first run, fast dashboard for returning users.
- **V1 fate**: Replace entirely. `hawk` shows v2 TUI. `hawk-hooks` CLI remains for backwards compat but the v1 TUI is removed.
- **Main view**: Dashboard header + action menu. Component types (skills, hooks, etc.) are menu entries that open toggle sublists.
- **Scope model**: Global + per-directory. No profiles in TUI MVP (profiles exist in config layer but aren't exposed in TUI yet).
- **Scope UX**: Context-aware. In a hawk-initialized dir, default to local. Otherwise default to global. Scope clearly indicated at all times. Tab to switch views, plus a menu item for discoverability.
- **Sync timing**: Prompt on exit. Config saved immediately on toggle, sync deferred until user exits or chooses "Sync" from menu.

## Menu Structure

### Main Menu

```
hawk v0.7.0 — 12 components, 3 tools
<scope indicator>
────────────────────────────────────────
  Skills          5 enabled
  Hooks           2 enabled
  Commands        3 enabled
  Agents          1 enabled
  MCP Servers     1 enabled
  ─────────
  Download        Fetch from git URL
  Registry        Browse all installed items
  Tools           Enable/disable AI tools
  ─────────
  Sync            Apply changes now
  Exit
```

### Scope Indicator

Always visible in the main menu header and every submenu header.

In a hawk-initialized directory:
```
Local: /Users/me/my-project
```

Outside a hawk directory:
```
Global
```

Each component entry in the main menu shows count of enabled items for the current scope context. When local, counts reflect the resolved set (global + local overrides).

### Toggle List (submenu for each component type)

```
Skills — Local: my-project              [Tab: switch to Global]
─────────────────────────────
  [x] tdd
  [x] react-patterns
  [ ] django-patterns
  [ ] typescript-strict
  [ ] legacy-jquery
  ─────────
  Select All
  Select None
  ─────────
  Switch to Global
  Done
```

**Behavior:**
- Items shown: everything in registry for this type
- Pre-checked: items enabled in the current scope
- Space: toggle individual item
- Tab: switch between Global and Local views (inline swap — header, checkmarks, and scope all change)
- "Select All" / "Select None": action items that check/uncheck all and return to list
- "Switch to Global/Local": same as Tab, for discoverability
- "Done": save config, return to main menu, set dirty flag if changed
- Cursor position preserved when switching scope

When switching from Local to Global:
```
Skills — Global                         [Tab: switch to Local]
─────────────────────────────
  [x] tdd
  [x] react-patterns
  [x] typescript-strict
  [ ] django-patterns
  [ ] legacy-jquery
  ─────────
  Select All
  Select None
  ─────────
  Switch to Local: my-project
  Done
```

### Empty State

When registry has no items for a type:
```
Skills — Global
─────────────────────
  (none in registry)

  Run 'hawk download <url>' to add skills.
  Done
```

### Registry Browser

```
Registry — 12 components
─────────────────────────
  skills/
    tdd
    react-patterns
    django-patterns
    typescript-strict
    legacy-jquery
  hooks/
    block-secrets
    lint-on-save
  commands/
    deploy.md
  agents/
    code-reviewer.md
  mcp/
    github.yaml
  ─────────
  Done
```

Read-only browse view. Shows everything installed in the registry, grouped by type. For managing individual items, use `hawk add` / `hawk remove` CLI.

### Tools View

```
Tools
─────────────────────
  [x] claude       ~/.claude (installed)
  [x] gemini       ~/.gemini (installed)
  [ ] codex        ~/.codex (not found)
  [ ] opencode     ~/.config/opencode (not found)
  ─────────
  Done
```

Toggle which tools hawk syncs to. Disabled tools are skipped during sync. Shows install status for each.

## First-Run Wizard

When no `~/.config/hawk-hooks/config.yaml` exists:

1. **Welcome**: "First time? Let's set up hawk."
2. **Detect tools**: Scan for Claude, Gemini, Codex, OpenCode. Show which are found, auto-enable found ones.
3. **Create config**: Write `config.yaml` with detected tools, empty component lists.
4. **Bootstrap**: "Your registry is empty. Download starter components? [Y/n]"
   - Yes: prompt for git URL (or offer default starter repo)
   - No: skip, print `hawk download <url>` hint
5. **Done**: Drop into normal TUI menu.

3-4 screens, no walls of text.

## Sync Flow

The TUI tracks a `dirty` flag (set when any toggle changes are made).

Config YAML is written immediately on toggle (crash safety). Tool configs are NOT updated yet.

On exit from TUI (or selecting "Sync" from menu), if dirty:
```
Changes made. Sync to tools now? [Y/n]
```
- Y: run `sync_all()` or scoped sync, show summary, exit/return
- N: exit, changes saved in config but not synced

The "Sync" main menu entry is always available for manual sync.

## Implementation Notes

### Library

Use `simple-term-menu` (already a dependency) for all menus:
- `TerminalMenu` with `multi_select=True` for toggle lists
- `accept_keys=("tab",)` to capture Tab for scope switching
- Regular `TerminalMenu` for single-select menus (main menu, wizard steps)

### Module Structure

```
src/hawk_hooks/v2_interactive.py    # New v2 TUI (single module)
```

Or if it grows:
```
src/hawk_hooks/v2_interactive/
  __init__.py          # v2_interactive_menu() entry point
  dashboard.py         # Main menu + header rendering
  toggle.py            # Generic toggle list with scope switching
  wizard.py            # First-run wizard
  tools.py             # Tools enable/disable view
```

### Entry Point

`v2_cli.py:main_v2()` calls `v2_interactive_menu()` when no subcommand given. Falls back to `parser.print_help()` if import fails (e.g. simple-term-menu not installed).

### Config Integration

Toggle lists read/write via `v2_config`:
- `load_global_config()` / `save_global_config()` for global scope
- `load_dir_config()` / `save_dir_config()` for local scope

Scope detection: check if `cwd` has `.hawk/config.yaml` (or is registered in global directory index).

### Dirty Tracking

Simple approach: snapshot the config dict on TUI entry, compare on exit. If different, prompt for sync.

## Out of Scope (for now)

- Profile management in TUI (profiles work in config layer, just not exposed in TUI)
- Per-tool overrides in TUI (use config.yaml directly)
- Editing/viewing individual component contents
- Creating new components from TUI (use `hawk add` CLI)
- Download TUI beyond the existing `hawk download` interactive picker
