# Migration Guide: Commands -> Prompts (v3)

This release introduces a breaking schema change:

- Old canonical key: `commands`
- New canonical key: `prompts`

Use the built-in one-shot upgrader before normal usage on existing installs.

## 1. Preview Changes

```bash
hawk migrate-prompts --check
```

This reports what will be migrated:
- config keys
- registry entries
- package metadata

## 2. Apply Migration

```bash
hawk migrate-prompts --apply
```

By default, backup files are written next to migrated files using:
- `*.commands-to-prompts.bak`

If you explicitly want no backups:

```bash
hawk migrate-prompts --apply --no-backup
```

## 3. Re-sync and Validate

```bash
hawk status
hawk sync
```

Confirm:
- expected slash items appear under prompts in status/config views
- sync output shows prompt items linked as expected per tool

## 4. Update Local Scripts/Automation

If you have custom tooling around hawk config, update key usage:

- `global.commands` -> `global.prompts`
- `commands.enabled/disabled` -> `prompts.enabled/disabled`
- `tools.<tool>.commands.extra/exclude` -> `tools.<tool>.prompts.extra/exclude`

Registry and package conventions:

- `registry/commands/*` -> `registry/prompts/*`
- package item type `command` -> `prompt`

## 5. Collision Handling

If both `registry/commands/<name>` and `registry/prompts/<name>` exist:
- migration keeps `registry/prompts/<name>` as source of truth
- legacy `commands` copy is dropped

Review migration output for collision lines and manually reconcile if needed.

## 6. Rollback

If you used default backup mode, restore from generated `*.commands-to-prompts.bak` files and rerun migration later.
