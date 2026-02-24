# Deprecation Inventory

Tracks planned removals and migrations after prompts-canonical schema adoption.

| Module/Feature | Deprecation Status | Replacement | Target Removal | Notes/Blockers |
|---|---|---|---|---|
| `v2_cli.py` module name | completed | `src/hawk_hooks/cli.py` | 2026-02-23 | v2 CLI is now the primary CLI module; entrypoints point to `hawk_hooks.cli:main`. |
| `src/hawk_hooks/interactive/*` (legacy interactive stack) | completed | `src/hawk_hooks/v2_interactive/*` | 2026-02-23 | Legacy stack removed from repository. |
| `src/hawk_hooks/config.py` legacy destination schema (`destinations.*.commands`) | completed | `destinations.*.prompts` | 2026-02-23 | Legacy v1 config/runtime modules removed. |
| `commands` schema fields in v2 config and dir configs | warned | `prompts` fields (`global.prompts`, `prompts.enabled/disabled`) | v3.x | Migrated by `hawk migrate-prompts`. |
| `registry/commands/` legacy registry location | warned | `registry/prompts/` | v3.x | One-shot migration moves entries; runtime now syncs prompts only. |
| `command` package item type in `packages.yaml` | warned | `prompt` type | v3.x | One-shot migration rewrites item types. |
| `hawk migrate-prompts` one-shot upgrader | planned | N/A (temporary migration utility) | v4.0 | Remove once all active installs are expected to be prompts-canonical. |
