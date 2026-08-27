# Prompts-Canonical Schema (v3) Design

## Goal

Make `prompts` the single canonical concept for slash-style items across hawk, remove runtime `commands` as a first-class schema concept, and ship a one-shot upgrader that safely migrates existing installs.

## Scope

- In scope:
  - v2 config, resolver, sync, CLI, TUI, adapters, downloader, package metadata
  - legacy v1 config + interactive/prompt flows
  - one-shot migration command
  - deprecation inventory doc (`docs/DEPRECATE.md`)
- Out of scope:
  - long-term dual-schema compatibility layer
  - unrelated feature work from other phases

## Architecture

### Canonical Data Model

Canonical component families become:
- `skills`
- `hooks`
- `prompts`
- `agents`
- `mcp`

`commands` is treated as legacy input only during migration.

### Runtime Contract

- Normal runtime paths consume prompts-only schema.
- Tool adapters remain free to map canonical prompts to tool-native locations:
  - Example: Claude may still materialize prompts into `commands/`.

### One-Shot Upgrader

New command: `hawk migrate-prompts`

Modes:
- `--check`: read-only report of required changes
- `--apply`: perform migration
- backup enabled by default, `--no-backup` optional

Idempotent by design: re-running after success reports no changes required.

## Data Flow

### Config Migration

- Global:
  - `global.commands -> global.prompts`
- Directory configs:
  - `commands.enabled/disabled -> prompts.enabled/disabled`
- Per-tool overrides:
  - `tools.<tool>.commands.extra/exclude -> tools.<tool>.prompts.extra/exclude`
- Legacy v1 destinations:
  - `destinations.<tool>.commands -> destinations.<tool>.prompts`

### Registry and Package Migration

- Registry files:
  - move `registry/commands/* -> registry/prompts/*`
- Packages index:
  - rewrite item type `command -> prompt`

### Cache Invalidation

- Clear resolved-set cache after migration to prevent stale no-op sync decisions.

## Conflict and Safety Semantics

- Backup first (unless `--no-backup`).
- Stable merge and dedupe when both legacy and canonical keys exist.
- Registry collisions:
  - if both `commands/name` and `prompts/name` exist, keep `prompts/name` and log conflict (no overwrite).
- Partial failure handling:
  - fail fast with explicit summary of completed/remaining steps.

## Testing Strategy

- TDD for all migration behaviors.
- Add dedicated tests for:
  - check/apply/idempotency
  - config field rewrites (global/dir/tool overrides)
  - registry move behavior + collisions
  - package metadata rewrites
  - runtime prompts-only behavior in resolver/sync/CLI/TUI
  - legacy v1 paths now using prompts terminology

## Rollout

1. Ship `migrate-prompts` with prompts-only runtime.
2. Require users to run migration for pre-v3 state.
3. Keep upgrader isolated so it can be removed in a later cleanup release.

## Deprecation Documentation

Create `docs/DEPRECATE.md` to track planned removals with:
- module/feature
- status
- replacement
- target removal
- notes/blockers
