# Auto-Sync UX Design (v2)

## Context

Today, hawk has two different concepts:

- Configured state: what is enabled in hawk config.
- Synced state: what has been applied to tool configs.

The current UX exposes this split explicitly via a manual `Sync` action. This creates friction and confusion:

- Users can have items enabled but not applied yet.
- `purge`/`uninstall` and cache behavior can make status feel inconsistent.
- Unsupported capabilities (for example tool-specific hook gaps) are reported as errors in places where they should be informative, not blocking.

## Goals

- Make `enabled` mean "hawk will apply this automatically".
- Remove sync as a required manual step in interactive flows.
- Preserve fast no-op behavior via cache.
- Treat unsupported capability as non-fatal (`skipped`) with explicit reason.
- Ensure future capability upgrades (for example codex hook support expansion) are picked up automatically on the next sync run.

## Non-Goals

- Continuous background syncing.
- Full asynchronous reconciliation daemon.
- Removing CLI `hawk sync` command (still useful for explicit runs and automation).

## Approaches Considered

### A) Apply-on-leave auto-sync (recommended)

Behavior:
- User edits toggles/settings.
- Hawk auto-runs sync when leaving the screen (and on dashboard exit based on existing preference).

Pros:
- Keeps UX simple.
- Avoids per-keystroke thrash.
- Lower implementation risk.

Cons:
- Changes are not instantly reflected after each toggle.

### B) Immediate per-toggle sync

Behavior:
- Every enable/disable triggers sync immediately.

Pros:
- Tightest coupling between toggle and effect.

Cons:
- Noisy and potentially expensive.
- More partial-state edge cases.

### C) Debounced live sync

Behavior:
- Queue changes; sync after short idle window.

Pros:
- Near-live feel with fewer operations than B.

Cons:
- More complexity (timers, cancellation, lifecycle handling) without strong user value for CLI/TUI use.

## Recommended Design

### 1) Source of Truth and State Model

- Desired state: global/local hawk config (`enabled` lists).
- Applied state: per-scope + per-tool sync cache.
- Capability state: per-tool capability fingerprint included in cache identity.

If desired state hash OR capability fingerprint changes, that target is considered unsynced and will be re-applied on next sync run.

### 2) Trigger Policy

- Interactive UI: auto-sync on leaving editing screens and on exit policy.
- CLI: `hawk sync` remains explicit.
- No background polling.
- Capability recheck happens when sync runs.

### 3) Unsupported Features Semantics

Unsupported = `skipped`, not `error`.

Examples:
- `hooks: pre_tool_use not supported on codex`
- `hooks: prompt hooks unsupported by gemini`

Behavior:
- Sync is successful if only skipped diagnostics occur.
- Cache updates on successful sync (including skipped-only outcomes).
- Real operational failures remain errors and block cache update.

### 4) Future Capability Upgrades

When tool capability changes (detected by fingerprint delta), sync re-runs and attempts previously skipped features again automatically.

No separate pending ledger is required initially; desired config + capability-aware cache provides this behavior with lower complexity.

### 5) UX and Output

- Dashboard counts remain `configured`.
- Header shows unsynced targets when non-zero.
- Sync summaries include skipped count:
  - Compact: `+9 linked, -2 unlinked, ~3 skipped`
  - Verbose: per-item skip reasons.

### 6) Backward Compatibility

- Existing configs remain valid.
- Existing adapters continue to work; diagnostic channels are refined.
- Manual `hawk sync` continues to function.

## Error Handling Rules

- Unsupported capability -> skipped diagnostic.
- User-managed conflict that prevents hawk-managed write (for example manual codex notify key conflict) -> error.
- IO/parse/write failures -> error.

## Testing Strategy

- Unit tests for capability-aware cache invalidation.
- Unit tests for skipped vs error classification.
- Unit tests for formatter output (`~N skipped` + reasons in verbose).
- Integration-style tests for TUI auto-sync trigger points.
- Regression tests for uninstall/purge + unsynced status consistency.

## Rollout

1. Introduce typed sync diagnostics (linked/unlinked/skipped/errors).
2. Update adapters to classify unsupported as skipped.
3. Add capability fingerprint to sync cache identity.
4. Replace interactive manual sync dependency with apply-on-leave auto-sync.
5. Keep CLI `hawk sync` unchanged for explicit use.
