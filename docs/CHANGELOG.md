# Changelog

## 2026-02-22 (v0.8.0)

### Added

- Cross-tool hook registration rollout:
  - Canonical event contract + support levels in `event_mapping.py`
  - Gemini native hook registration
  - Codex notify-style hook bridge
  - Explicit unsupported-hook warnings for OpenCode/Cursor/Antigravity
- Dashboard Registry browser:
  - New `Registry` action in TUI
  - Read-only grouped browse by component type
  - Per-item metadata: type, owning package, and file size
  - Enter opens selected item in `$EDITOR`

### Changed

- `hawk sync` output is compact by default (per-tool counts).
- `hawk sync -v/--verbose` restores per-item detailed output.
- Dashboard sync display now uses compact formatting.
- Continue prompts in dashboard flows now accept Enter, `q`, and Ctrl+C.
- Dashboard scope detection now resolves nearest registered ancestor directory.
- Dashboard component counts now reflect resolved chain output (global + parent layers + local overrides).

### Docs

- `CLAUDE.md` updated to describe v2 as the primary architecture.
- v2 completion plan reconciled with implemented Phase A/B/C/D/E status.

## 2026-02-21

### Breaking

- Canonical slash-item schema changed from `commands` to `prompts`.
- v2 runtime now resolves/syncs prompt entries as the primary slash concept.
- Legacy `commands` layout is no longer the long-term runtime model.

### Added

- `hawk migrate-prompts` one-shot upgrader:
  - `--check` to preview migration impact
  - `--apply` to perform migration
  - `--no-backup` to skip backup generation
- Migration coverage for:
  - global config fields (`global.commands -> global.prompts`)
  - directory config layers (`commands.enabled/disabled -> prompts.enabled/disabled`)
  - tool overrides (`commands.extra/exclude -> prompts.extra/exclude`)
  - registry move (`registry/commands/* -> registry/prompts/*`)
  - package metadata rewrite (`command -> prompt`)

### Changed

- v2 interactive dashboard labeling now uses **Prompts**.
- Downloader classification maps legacy `commands/` directories to prompt items.
- Legacy v1 destination key usage is aligned to `prompts` terminology (with compatibility fallback where needed).

### Docs

- Added deprecation inventory: `docs/DEPRECATE.md`
- Added migration guide: `docs/MIGRATION-v3-prompts.md`
