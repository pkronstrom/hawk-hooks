# owl-afk + hawk-hooks v2 Integration Design

## Context

owl-afk currently integrates with hawk-hooks v1 by writing shell wrapper scripts
directly into `~/.config/hawk-hooks/hooks/{event}/` and calling `hawk-hooks enable`
+ `hawk-hooks toggle`. This is tightly coupled to v1's directory structure and CLI.

hawk-hooks v2 uses a registry-based architecture where components are imported via
`hawk download`, `hawk scan`, or `hawk add`, stored in
`~/.config/hawk-hooks/registry/`, and synced to tools via adapters.

## Goal

Make owl-afk work with hawk-hooks v2 through two complementary paths:

1. **Registry-native**: owl-afk ships hawk-compatible hook files so users can
   `hawk download` or `hawk scan` the repo directly.
2. **Convenience command**: `owl hawk install` detects hawk v2 and delegates to it
   instead of managing files manually.

## Design

### Hook Files in owl-afk Repo

Add a `hooks/` directory to the owl-afk repo with v2-compatible thin wrappers:

```bash
# hooks/owl-pre-tool-use.sh
#!/usr/bin/env bash
# hawk-hook: events=pre_tool_use
# hawk-hook: description=OWL AFK pre-tool-use gate
# hawk-hook: timeout=3600
exec owl hook PreToolUse
```

```bash
# hooks/owl-post-tool-use.sh
#!/usr/bin/env bash
# hawk-hook: events=post_tool_use
# hawk-hook: description=OWL AFK post-tool-use handler
exec owl hook PostToolUse
```

```bash
# hooks/owl-stop.sh
#!/usr/bin/env bash
# hawk-hook: events=stop
# hawk-hook: description=OWL AFK stop handler
# hawk-hook: timeout=3600
exec owl hook Stop
```

```bash
# hooks/owl-subagent-stop.sh
#!/usr/bin/env bash
# hawk-hook: events=subagent_stop
# hawk-hook: description=OWL AFK subagent stop handler
# hawk-hook: timeout=3600
exec owl hook SubagentStop
```

Key properties:
- Flat directory (no `{event}/` subdirectories)
- `# hawk-hook:` metadata instead of v1's `# Timeout:` / `# Deps:` comments
- Event names declared in the file, not derived from directory path
- Scripts are thin wrappers: `exec owl hook <EventType>`

### Registry-Native Path (no changes to hawk-hooks)

Users with hawk v2 install owl-afk hooks via:

```bash
hawk download https://github.com/pkronstrom/owl-afk
# or, if already cloned locally:
hawk scan ~/Projects/owl-afk
```

hawk's `classify()` finds `hooks/*.sh` with `hawk-hook:` metadata, prompts for
selection, copies to registry, enables in config. User runs `hawk sync`.

Update via `hawk update owl-afk`.

### Updated `owl hawk install` Command

The convenience command detects what's available and picks the right path:

```
owl hawk install
  |-- hawk v2 detected?  -> hawk scan <owl-hooks-dir> --all && hawk sync
  |-- hawk v1 detected?  -> legacy v1 flow (with deprecation warning)
  |-- neither?           -> standalone (write directly to settings.json)
```

Detection:
- **v2**: `hawk` CLI exists AND `~/.config/hawk-hooks/registry/` exists
- **v1**: `hawk-hooks` CLI exists AND `~/.config/hawk-hooks/hooks/` exists (no registry)
- **standalone**: fallback, writes directly to `~/.claude/settings.json`

The hooks directory path is resolved from owl-afk's own package (via `__file__`
or `importlib.resources`), so `hawk scan` points at the installed package's
`hooks/` directory.

`owl hawk uninstall` similarly delegates to hawk CLI to remove components from
the registry.

### Updated Detection (`check_hooks_installed`)

```python
def check_hooks_installed():
    # v2: check registry
    registry_hook = Path.home() / ".config/hawk-hooks/registry/hooks/owl-pre-tool-use.sh"
    if registry_hook.exists():
        return "hawk-v2"

    # v1: check old path
    v1_hook = Path.home() / ".config/hawk-hooks/hooks/pre_tool_use/owl-pre_tool_use.sh"
    if v1_hook.exists():
        return "hawk-v1"

    # standalone: check settings.json
    # (existing logic)
    return "standalone" or None
```

### Setup Wizard

Same choice as before (standalone vs hawk-hooks), updated detection:

```python
hawk_v2 = shutil.which("hawk") and REGISTRY_DIR.exists()
hawk_v1 = shutil.which("hawk-hooks") and HAWK_V1_DIR.exists()
hawk_available = hawk_v2 or hawk_v1
```

## Changes by Repo

### owl-afk (all changes here)
- Add `hooks/` directory with 4 shell scripts
- Rewrite `cli/install.py` — delegate to `hawk scan` for v2
- Update `check_hooks_installed()` — check registry path
- Update setup wizard detection

### hawk-hooks
- No changes required. `hawk download`/`hawk scan`/`classify()` already handle
  this layout.

## User Experience

| Path | Command | Result |
|------|---------|--------|
| Registry-native | `hawk download https://github.com/pkronstrom/owl-afk` | Hooks in registry, enabled, synced |
| Convenience | `owl hawk install` | Detects hawk v2, delegates to `hawk scan` |
| Standalone | `owl hawk install` (no hawk) | Direct `settings.json` write (unchanged) |

Both hawk paths end up in the same place: hooks in registry, enabled in config,
synced to all configured tools.
