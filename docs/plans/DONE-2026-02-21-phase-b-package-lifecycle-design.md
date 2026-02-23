# Phase B Package Lifecycle Design

## Context

`v2-completion-plan.md` Phase B identifies two package lifecycle gaps:

1. Local `hawk scan` imports do not persist enough source metadata for deterministic `hawk update`.
2. `migrate_config()` does not produce a config shape fully aligned with `DEFAULT_GLOBAL_CONFIG`.

This design defines canonical source semantics for package entries and closes migration schema drift.

## Goals

1. Make package source explicit and actionable across `scan`, `packages`, and `update`.
2. Make update behavior deterministic for git, local, and manual package sources.
3. Preserve batch behavior: fail individual packages, continue processing others.
4. Ensure v1 -> v2 migration output matches `DEFAULT_GLOBAL_CONFIG` shape exactly.

## Non-Goals

1. No new source-adoption flag on scan (explicit remove + re-import required).
2. No interactive conflict prompts in non-interactive CLI paths.
3. No changes to non-package registry semantics.

## Source Model

Package source is inferred from metadata fields in `packages.yaml`:

1. `url` present: source is `[git]` (authoritative even if `path` also exists).
2. `url` empty and `path` present: source is `[local]`.
3. neither present: source is `[manual]`.

For local scans, store `path` as normalized absolute path.

## CLI Behavior

### `hawk scan <path>`

1. When package items are recorded from local scanning, write `path=<absolute path>` in package entry.
2. If package name already exists with conflicting source type, error and refuse to overwrite source metadata.
3. Conflict remediation is explicit:
   - remove then re-import via `hawk remove-package <name>` + `hawk scan ...`
   - or remove then re-import via `hawk remove-package <name>` + `hawk download ...`

### `hawk packages`

1. Show source marker per package: `[git]`, `[local]`, `[manual]`.
2. If both `url` and `path` exist, display `[git]` and continue using git semantics.

### `hawk update [package]`

Per package decision tree:

1. `[git]`: existing clone/classify/update flow.
2. `[local]`: re-scan from stored absolute `path`, then apply replace-or-add item updates.
3. `[manual]`: print "local-only/manual package, cannot update" and treat as skipped.

Local path failure behavior:

1. If stored `path` does not exist: package failure, continue processing others.
2. Print actionable fix suggestions:
   - re-import from moved path
   - remove package if intentional
   - restore/mount path and retry
3. If path exists but scan returns zero components: package failure with guidance to verify path/depth/re-import.

Exit status:

1. Any package failure => non-zero command exit.
2. Successful and skipped packages may still occur in the same run; summary includes failed count.

### `hawk update --check`

1. Uses same source routing as `hawk update`.
2. For `[local]`, performs re-scan and computes would-change status/counts.
3. Applies same failure policy as full update (missing path or zero components => failure, overall non-zero if any failure).

## Migration Schema (B2)

`migrate_config()` output must align with `DEFAULT_GLOBAL_CONFIG`:

1. Include `"prompts": []` in generated global component section.
2. Seed tool map with `cursor` and `antigravity` alongside existing tools.
3. Ensure migrated data structure contains all default top-level and nested keys required by the default schema.

## Error Handling

1. Source conflicts are explicit errors with remediation commands.
2. Per-package update errors are isolated; batch execution continues.
3. Command-level non-zero exit communicates partial failure to scripts/CI.

## Testing Strategy

### B1 Tests

1. `scan` records absolute `path` for local package entries.
2. `packages` renders correct source labels and precedence (`url` over `path`).
3. `update` re-scans `[local]` sources and updates package item metadata.
4. `update --check` reports local would-change output.
5. Missing local path triggers package failure, continues batch, and returns non-zero.
6. Zero-component local re-scan triggers package failure and non-zero.
7. Source-conflict on scan is rejected with clear error messaging.

### B2 Tests

1. Migrated config includes `prompts` key in global section.
2. Migrated tool map includes `cursor` and `antigravity`.
3. Migrated output key set matches `DEFAULT_GLOBAL_CONFIG` shape (top-level and nested sections used by runtime).

## Rollout Notes

1. Existing packages with only `url` remain unchanged.
2. Existing packages with neither source field are treated as `[manual]` until re-imported.
3. Local package paths are machine-specific by design (absolute-path decision).
