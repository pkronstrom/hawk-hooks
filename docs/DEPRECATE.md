# Deprecation Inventory

Tracks planned removals and migrations after prompts-canonical schema adoption.

| Module/Feature | Deprecation Status | Replacement | Target Removal | Notes/Blockers |
|---|---|---|---|---|
| `src/hawk_hooks/cli.py` (legacy v1 CLI entrypoints) | planned | `src/hawk_hooks/v2_cli.py` | v3.x | Keep only while v1 commands are still referenced in external scripts. |
| `src/hawk_hooks/interactive/*` (legacy interactive stack) | planned | `src/hawk_hooks/v2_interactive/*` | v3.x | Menu wording now prompts-canonical; remaining cleanup is structural deletion. |
| `src/hawk_hooks/config.py` legacy destination schema (`destinations.*.commands`) | warned | `destinations.*.prompts` | v3.x | Backward-compat fallback still reads old key. Remove fallback after migration window. |
| `commands` schema fields in v2 config and dir configs | warned | `prompts` fields (`global.prompts`, `prompts.enabled/disabled`) | v3.x | Migrated by `hawk migrate-prompts`. |
| `registry/commands/` legacy registry location | warned | `registry/prompts/` | v3.x | One-shot migration moves entries; runtime now syncs prompts only. |
| `command` package item type in `packages.yaml` | warned | `prompt` type | v3.x | One-shot migration rewrites item types. |
| `hawk migrate-prompts` one-shot upgrader | planned | N/A (temporary migration utility) | v4.0 | Remove once all active installs are expected to be prompts-canonical. |
